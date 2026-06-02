# -*- coding: utf-8 -*-
"""
Voice poller — polls the Xiaomi speaker conversation every 5 seconds,
parses "我做完了XX" patterns, and triggers the points engine.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, List, Set
from sqlmodel import Session, select

from database import Child, ScheduleItem, Completion, engine
from points_engine import settle_completion
from xiaomi_client import xiaomi_client
from ws_manager import ws_manager

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5  # seconds
MATCH_WINDOW_MINUTES = 30  # look for tasks within ±30 min of now

PATTERNS = [
    re.compile(r"我做完了(.+)"),
    re.compile(r"做完(.+)了"),
    re.compile(r"(.+)做完了"),
    re.compile(r"完成了(.+)"),
    re.compile(r"(.+)完成了"),
    re.compile(r"我完成了(.+)"),
]

BADGE_EMOJI = {
    "streak_7": "🔥",
    "reader": "📚",
    "athlete": "🏃",
    "musician": "🎵",
    "perfect_day": "⭐",
    "overachiever": "🚀",
}

BADGE_NAME = {
    "streak_7": "坚持7天",
    "reader": "阅读达人",
    "athlete": "运动健将",
    "musician": "音乐达人",
    "perfect_day": "全勤王",
    "overachiever": "超额完成",
}


def _extract_task_hint(text: str) -> Optional[str]:
    """Return the task-name fragment from a voice utterance, or None if no match."""
    for pattern in PATTERNS:
        m = pattern.search(text)
        if m:
            hint = m.group(1).strip().rstrip("。！？~")
            return hint
    return None


def _match_item(hint: str, items: List[ScheduleItem]) -> Optional[ScheduleItem]:
    """Find the best matching schedule item for the extracted hint."""
    import jieba

    hint_words = set(jieba.cut(hint))
    best_item = None
    best_score = 0

    for item in items:
        # Direct substring match first
        if hint in item.title or item.title in hint:
            return item

        # Keyword match
        kws = item.get_keywords()
        for kw in kws:
            if kw in hint or hint in kw:
                return item

        # Jieba token overlap
        title_words = set(jieba.cut(item.title))
        overlap = len(hint_words & title_words)
        if overlap > best_score:
            best_score = overlap
            best_item = item

    return best_item if best_score > 0 else None


def _build_encouragement(result: dict) -> str:
    child = result["child_name"]
    task = result["task_title"]
    pts = result["points_awarded"]
    total = result["available_points"]
    msg = f"太棒了！{child}完成了{task}，获得{pts}积分！当前积分{total}分。"

    if result["leveled_up"]:
        msg += f"哇！{child}升级了！现在是{result['level_title']}，继续加油！"

    for badge_type in result.get("new_badges", []):
        emoji = BADGE_EMOJI.get(badge_type, "🏅")
        name = BADGE_NAME.get(badge_type, badge_type)
        msg += f"还解锁了新徽章{emoji}{name}！"

    next_xp = result.get("next_level_xp")
    if next_xp and not result["leveled_up"]:
        remaining = next_xp - result["total_xp"]
        msg += f"再获得{remaining}经验就能升级啦~"

    return msg


async def voice_poller_loop(device_id: str):
    """Runs forever, polling conversation every POLL_INTERVAL seconds."""
    logger.info("Voice poller started, device_id=%s", device_id)
    while True:
        try:
            await _poll(device_id)
        except Exception as e:
            logger.error("Voice poller error: %s", e)
        await asyncio.sleep(POLL_INTERVAL)


async def _poll(device_id: str):
    text = await xiaomi_client.get_latest_conversation(device_id)
    if not text:
        return

    hint = _extract_task_hint(text)
    if not hint:
        return

    logger.info("Voice match candidate: %r → hint=%r", text, hint)

    now = datetime.now()
    window_start = now - timedelta(minutes=MATCH_WINDOW_MINUTES)
    window_end = now + timedelta(minutes=MATCH_WINDOW_MINUTES)

    with Session(engine) as session:
        # Candidate items in the time window
        candidates = session.exec(
            select(ScheduleItem).where(
                ScheduleItem.start_time >= window_start,
                ScheduleItem.end_time <= window_end + timedelta(hours=1),
            )
        ).all()

        # Filter out already-completed items
        candidate_ids = [i.id for i in candidates]
        completed_ids: Set[int] = set()
        if candidate_ids:
            comps = session.exec(
                select(Completion).where(Completion.schedule_item_id.in_(candidate_ids))
            ).all()
            completed_ids = {c.schedule_item_id for c in comps}

        active = [i for i in candidates if i.id not in completed_ids]
        if not active:
            return

        # Try to find child name in the utterance to disambiguate
        children = session.exec(select(Child)).all()
        named_child: Child | None = None
        for child in children:
            if child.name in text:
                named_child = child
                break

        if named_child:
            active = [i for i in active if i.child_id == named_child.id]

        matched = _match_item(hint, active)
        if not matched:
            logger.debug("No schedule item matched hint=%r", hint)
            return

        # If multiple children could own this (no named child), complete for all matching
        if named_child:
            targets = [(named_child.id, matched)]
        else:
            targets = []
            for item in active:
                if item.id == matched.id:
                    targets.append((item.child_id, item))
            # Deduplicate by child_id
            seen = set()
            targets = [(cid, itm) for cid, itm in targets if cid not in seen and not seen.add(cid)]

        for child_id, item in targets:
            result = await settle_completion(session, item, child_id, voice_raw=text)
            if not result["ok"]:
                continue

            # TTS encouragement
            encouragement = _build_encouragement(result)
            await xiaomi_client.tts(device_id, encouragement)

            # WebSocket push for real-time frontend update
            await ws_manager.broadcast({
                "type": "completion",
                "child_id": child_id,
                "task_title": item.title,
                "points_awarded": item.points_reward,
                "leveled_up": result["leveled_up"],
                "new_badges": result["new_badges"],
            })

            logger.info(
                "Completion settled: child_id=%s item=%s pts=%s",
                child_id, item.title, item.points_reward,
            )
