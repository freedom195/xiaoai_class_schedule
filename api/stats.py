from __future__ import annotations
from datetime import datetime, timedelta, date
from typing import Optional, Dict, List
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from database import Child, ScheduleItem, Completion, get_session

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _item_active_on_date(item: ScheduleItem, target: date) -> bool:
    """Check if a recurring item is active on target_date."""
    item_date = item.start_time.date()
    rt = item.recurrence_type
    if rt == "none":
        return item_date == target
    if item_date > target:
        return False
    if rt == "daily":
        pass
    elif rt == "weekly":
        days = item.get_recurrence_days()
        if target.weekday() not in days:
            return False
    else:
        return False
    # Check recurrence_end_date
    end_str = getattr(item, "recurrence_end_date", None)
    if end_str:
        try:
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            if target > end_date:
                return False
        except (ValueError, TypeError):
            pass
    # Check cancelled dates
    if target.isoformat() in item.get_cancelled_dates():
        return False
    return True


@router.get("")
def get_stats(
    child_id: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: Session = Depends(get_session),
):
    # Default: last 30 days
    end_dt = datetime.fromisoformat(end).replace(hour=23, minute=59, second=59) if end else datetime.now().replace(hour=23, minute=59, second=59)
    start_dt = datetime.fromisoformat(start) if start else end_dt - timedelta(days=30)
    start_date = start_dt.date()
    end_date = end_dt.date()

    children_q = select(Child)
    if child_id:
        children_q = children_q.where(Child.id == child_id)
    children = session.exec(children_q).all()

    results = []
    for child in children:
        # Get all items for this child
        all_items = session.exec(
            select(ScheduleItem).where(ScheduleItem.child_id == child.id)
        ).all()

        # Get all completions for this child
        all_completions = session.exec(
            select(Completion).where(Completion.child_id == child.id)
        ).all()
        # Map: item_id -> set of completion_date strings
        comp_dates: Dict[int, set] = {}
        for c in all_completions:
            comp_dates.setdefault(c.schedule_item_id, set()).add(c.completion_date)

        # Daily breakdown + totals
        daily: Dict[str, Dict] = {}
        total_scheduled = 0
        total_completed = 0
        total_points = 0

        cur = start_date
        while cur <= end_date:
            day_key = cur.isoformat()
            daily[day_key] = {"scheduled": 0, "completed": 0}

            for item in all_items:
                if not _item_active_on_date(item, cur):
                    continue
                total_scheduled += 1
                daily[day_key]["scheduled"] += 1

                if day_key in comp_dates.get(item.id, set()):
                    total_completed += 1
                    daily[day_key]["completed"] += 1
                    # Find the actual completion to get points
                    for c in all_completions:
                        if c.schedule_item_id == item.id and c.completion_date == day_key:
                            total_points += c.points_awarded
                            break

            cur += timedelta(days=1)

        streak = _calc_streak(daily)

        results.append({
            "child_id": child.id,
            "child_name": child.name,
            "avatar_emoji": child.avatar_emoji,
            "total_scheduled": total_scheduled,
            "total_completed": total_completed,
            "total_points_earned": total_points,
            "longest_streak": streak,
            "daily": [
                {"date": k, **v, "rate": v["completed"] / v["scheduled"] if v["scheduled"] else 0}
                for k, v in sorted(daily.items())
            ],
        })

    return results


def _calc_streak(daily: Dict[str, Dict]) -> int:
    """Calculate the longest consecutive days with at least one completion."""
    days = sorted(daily.keys())
    max_streak = cur = 0
    for day in days:
        if daily[day]["completed"] > 0:
            cur += 1
            max_streak = max(max_streak, cur)
        else:
            cur = 0
    return max_streak
