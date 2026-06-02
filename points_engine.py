# -*- coding: utf-8 -*-
"""
Points engine — settles completions, handles leveling and badge awards.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from sqlmodel import Session, select

from database import (
    Badge, Child, Completion, PointsTransaction, ScheduleItem,
)

# Level thresholds: (min_xp, level, title)
LEVELS = [
    (0,    1, "暑假新星"),
    (200,  2, "学习小达人"),
    (500,  3, "知识探索者"),
    (1000, 4, "暑期冠军"),
    (2000, 5, "传奇学霸"),
]

# Badge definitions: (badge_type, check_fn)
TASK_KEYWORD_BADGES = [
    ("reader",   ["阅读", "读书", "看书"]),
    ("athlete",  ["运动", "跑步", "游泳", "锻炼"]),
    ("musician", ["钢琴", "音乐", "乐器", "唱歌"]),
]


def level_for_xp(xp: int) -> tuple[int, str]:
    level, title = LEVELS[0][1], LEVELS[0][2]
    for min_xp, lvl, ttl in LEVELS:
        if xp >= min_xp:
            level, title = lvl, ttl
    return level, title


def next_level_xp(current_xp: int) -> Optional[int]:
    """XP needed for next level, or None if already max."""
    for min_xp, _, _ in LEVELS[1:]:
        if current_xp < min_xp:
            return min_xp
    return None


async def settle_completion(
    session: Session,
    item: ScheduleItem,
    child_id: int,
    voice_raw: Optional[str] = None,
    completion_date: Optional[str] = None,
) -> dict:
    """
    Record a completion, award points + XP, check level up and badges.
    Returns a result dict used by both voice_poller and the API endpoint.
    """
    today = completion_date or datetime.now().strftime("%Y-%m-%d")

    child = session.get(Child, child_id)
    if not child:
        return {"ok": False, "error": "child not found"}

    # Prevent duplicate completion for same item on same date
    existing = session.exec(
        select(Completion).where(
            Completion.schedule_item_id == item.id,
            Completion.child_id == child_id,
            Completion.completion_date == today,
        )
    ).first()
    if existing:
        return {"ok": False, "error": "already completed today"}

    # Record completion
    comp = Completion(
        schedule_item_id=item.id,
        child_id=child_id,
        completion_date=today,
        voice_raw=voice_raw,
        points_awarded=item.points_reward,
        xp_awarded=item.xp_reward,
    )
    session.add(comp)

    # Update child totals
    old_level = child.level
    child.available_points += item.points_reward
    child.total_xp += item.xp_reward
    new_level, new_title = level_for_xp(child.total_xp)
    child.level = new_level
    session.add(child)

    # Points transaction record
    txn = PointsTransaction(
        child_id=child_id,
        delta=item.points_reward,
        reason=f"完成：{item.title}",
    )
    session.add(txn)
    session.commit()
    session.refresh(child)

    leveled_up = new_level > old_level
    new_badges = _check_badges(session, child, item)

    return {
        "ok": True,
        "child_name": child.name,
        "task_title": item.title,
        "points_awarded": item.points_reward,
        "xp_awarded": item.xp_reward,
        "available_points": child.available_points,
        "total_xp": child.total_xp,
        "level": new_level,
        "level_title": new_title,
        "leveled_up": leveled_up,
        "new_badges": new_badges,
        "next_level_xp": next_level_xp(child.total_xp),
    }


def _check_badges(session: Session, child: Child, item: ScheduleItem) -> List[str]:
    """Check and award any newly earned badges. Returns list of new badge_types."""
    awarded = []

    existing = {b.badge_type for b in session.exec(
        select(Badge).where(Badge.child_id == child.id)
    ).all()}

    # 1. Keyword-based task badges (reader / athlete / musician)
    title_lower = item.title.lower()
    for badge_type, keywords in TASK_KEYWORD_BADGES:
        if badge_type in existing:
            continue
        if not any(kw in item.title for kw in keywords):
            continue
        # Count how many times this category has been completed
        all_items = session.exec(select(ScheduleItem).where(ScheduleItem.child_id == child.id)).all()
        category_ids = [
            i.id for i in all_items
            if any(kw in i.title for kw in keywords)
        ]
        if category_ids:
            count = len(session.exec(
                select(Completion).where(
                    Completion.child_id == child.id,
                    Completion.schedule_item_id.in_(category_ids),
                )
            ).all())
            if count >= 10:
                _award_badge(session, child.id, badge_type)
                existing.add(badge_type)
                awarded.append(badge_type)

    # 2. Streak badge (7 consecutive days)
    if "streak_7" not in existing:
        if _calc_current_streak(session, child.id) >= 7:
            _award_badge(session, child.id, "streak_7")
            awarded.append("streak_7")

    # 3. Perfect day badge
    if "perfect_day" not in existing:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        today_items = session.exec(
            select(ScheduleItem).where(
                ScheduleItem.child_id == child.id,
                ScheduleItem.start_time >= today,
                ScheduleItem.start_time < tomorrow,
            )
        ).all()
        today_ids = [i.id for i in today_items]
        if today_ids:
            completed_today = session.exec(
                select(Completion).where(
                    Completion.child_id == child.id,
                    Completion.schedule_item_id.in_(today_ids),
                )
            ).all()
            if len(completed_today) >= len(today_ids):
                _award_badge(session, child.id, "perfect_day")
                awarded.append("perfect_day")

    return awarded


def _award_badge(session: Session, child_id: int, badge_type: str):
    badge = Badge(child_id=child_id, badge_type=badge_type)
    session.add(badge)
    session.commit()


def _calc_current_streak(session: Session, child_id: int) -> int:
    """Count consecutive days ending today that have at least one completion."""
    completions = session.exec(
        select(Completion).where(Completion.child_id == child_id)
    ).all()
    days_with_completion = {c.completed_at.date() for c in completions}

    streak = 0
    day = datetime.now().date()
    while day in days_with_completion:
        streak += 1
        day -= timedelta(days=1)
    return streak
