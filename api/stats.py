from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional, Dict
from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func

from database import Child, ScheduleItem, Completion, get_session

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def get_stats(
    child_id: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: Session = Depends(get_session),
):
    # Default: last 30 days
    end_dt = datetime.fromisoformat(end) if end else datetime.now()
    start_dt = datetime.fromisoformat(start) if start else end_dt - timedelta(days=30)

    children_q = select(Child)
    if child_id:
        children_q = children_q.where(Child.id == child_id)
    children = session.exec(children_q).all()

    results = []
    for child in children:
        # All scheduled items in range
        scheduled = session.exec(
            select(ScheduleItem).where(
                ScheduleItem.child_id == child.id,
                ScheduleItem.start_time >= start_dt,
                ScheduleItem.start_time <= end_dt,
            )
        ).all()
        scheduled_ids = [s.id for s in scheduled]

        completions = []
        if scheduled_ids:
            completions = session.exec(
                select(Completion).where(Completion.schedule_item_id.in_(scheduled_ids))
            ).all()

        # Daily breakdown
        daily: Dict[str, Dict] = {}
        for item in scheduled:
            day_key = item.start_time.strftime("%Y-%m-%d")
            if day_key not in daily:
                daily[day_key] = {"scheduled": 0, "completed": 0}
            daily[day_key]["scheduled"] += 1

        completed_item_ids = {c.schedule_item_id for c in completions}
        for item in scheduled:
            if item.id in completed_item_ids:
                day_key = item.start_time.strftime("%Y-%m-%d")
                daily[day_key]["completed"] += 1

        # Longest streak
        streak = _calc_streak(daily)

        results.append({
            "child_id": child.id,
            "child_name": child.name,
            "avatar_emoji": child.avatar_emoji,
            "total_scheduled": len(scheduled),
            "total_completed": len(completions),
            "total_points_earned": sum(c.points_awarded for c in completions),
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
