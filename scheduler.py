# -*- coding: utf-8 -*-
"""
Scheduler — checks every minute for tasks that should be announced now.
Also listens for voice "modify" commands from the speaker.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from sqlmodel import Session, select

from database import Child, ScheduleItem, Completion, engine
from xiaomi_client import xiaomi_client
from ws_manager import ws_manager

logger = logging.getLogger(__name__)

# How many minutes before start_time to broadcast the opening announcement
ADVANCE_MINUTES = 1

# Pattern: "课程修改，为xxx" / "课表修改，为xxx"
_MODIFY_RE = re.compile(r'(?:课程修改|课表修改)[，,]?为(.+)', re.IGNORECASE)


def _format_time(dt: datetime) -> str:
    h, m = dt.hour, dt.minute
    return f"{h}点{m}分" if m != 0 else f"{h}点"


def _build_start_tts(child_name: str, item: ScheduleItem) -> str:
    kws = item.get_keywords()
    keyword = kws[0] if kws else item.title
    time_str = _format_time(item.start_time)
    end_str = _format_time(item.end_time)
    notes = ("，" + item.notes) if item.notes else ""
    say_done = "小爱小爱，我做完了" + keyword
    return (
        child_name + "，现在" + time_str + "，" + item.title + "开始啦！"
        + "记得" + end_str + "之前完成哦" + notes + "。"
        + "完成后说'" + say_done + "'就可以记录啦~"
        + "如果想修改课程，可以对小爱说：课程修改，为新课程名"
    )


def _build_end_tts(child_name: str, item: ScheduleItem) -> str:
    base = f"{child_name}，{item.title}时间到啦！完成了吗？"
    if item.task_type == "screen":
        base += "刚刚看了电子屏幕，现在请往远处看看，休息二十秒哦~"
    return base


async def _process_voice_modify(device_id: str, session: Session, now: datetime):
    """Check the speaker for a '课程修改/课表修改，为XX' voice command and apply it."""
    query = await xiaomi_client.get_latest_conversation(device_id)
    if not query:
        return
    logger.info("Voice query received: %s", query)
    m = _MODIFY_RE.search(query)
    if not m:
        return

    new_title = m.group(1).strip()
    # Strip trailing punctuation that ASR often appends
    for ch in ["，", "。", "、", "！", "？", "～", "~", ",", "."]:
        if new_title.endswith(ch):
            new_title = new_title[:-1]
    if not new_title:
        return

    # Find the ongoing item(s) for the child whose name appears in the query,
    # or fall back to the first ongoing item.
    ongoing = session.exec(
        select(ScheduleItem).where(
            ScheduleItem.start_time <= now,
            ScheduleItem.end_time > now,
        )
    ).all()
    if not ongoing:
        logger.info("Voice modify: no ongoing item to modify")
        return

    # Try to match a child name mentioned in the query
    children = session.exec(select(Child)).all()
    target_item = ongoing[0]
    for child in children:
        if child.name in query:
            for item in ongoing:
                if item.child_id == child.id:
                    target_item = item
                    break
            break

    old_title = target_item.title
    target_item.title = new_title
    target_item.voice_modified = True
    target_item.original_title = old_title
    session.add(target_item)
    session.commit()
    logger.info("Voice modify: changed '%s' → '%s'", old_title, new_title)

    child = session.get(Child, target_item.child_id)
    if child:
        confirm = f"{child.name}，好的，已经把课程改成{new_title}啦"
        await xiaomi_client.tts(device_id, confirm)


async def scheduler_loop(device_id: str):
    """Runs forever, checking every 60 seconds."""
    logger.info("Scheduler started, device_id=%s", device_id)
    while True:
        try:
            await _tick(device_id)
        except Exception as e:
            logger.error("Scheduler tick error: %s", e)
        await asyncio.sleep(60)


async def _tick(device_id: str):
    now = datetime.now()
    window_start = now - timedelta(seconds=30)
    window_end = now + timedelta(seconds=30)

    with Session(engine) as session:
        # Voice modify: check for "修改/变更，为XX" command first
        await _process_voice_modify(device_id, session, now)

        # Tasks starting now (±30s window after subtracting advance)
        announce_start_from = window_start + timedelta(minutes=ADVANCE_MINUTES)
        announce_start_to = window_end + timedelta(minutes=ADVANCE_MINUTES)

        starting = session.exec(
            select(ScheduleItem).where(
                ScheduleItem.start_time >= announce_start_from,
                ScheduleItem.start_time <= announce_start_to,
            )
        ).all()

        for item in starting:
            child = session.get(Child, item.child_id)
            if not child:
                continue
            text = _build_start_tts(child.name, item)
            await xiaomi_client.tts(device_id, text)
            logger.info("Start TTS: [%s] %s", child.name, item.title)

        # Tasks ending now
        ending = session.exec(
            select(ScheduleItem).where(
                ScheduleItem.end_time >= window_start,
                ScheduleItem.end_time <= window_end,
            )
        ).all()

        for item in ending:
            # Only remind if not already completed
            comp = session.exec(
                select(Completion).where(Completion.schedule_item_id == item.id)
            ).first()
            if comp:
                continue
            child = session.get(Child, item.child_id)
            if not child:
                continue
            text = _build_end_tts(child.name, item)
            await xiaomi_client.tts(device_id, text)
            logger.info("End reminder TTS: [%s] %s", child.name, item.title)
