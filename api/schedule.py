from __future__ import annotations
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Set
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
import json

from database import ScheduleItem, Completion, get_session

router = APIRouter(prefix="/api/schedule", tags=["schedule"])

TASK_TYPE_DEFAULTS = {
    "rest":         {"color": "#64748b", "title": "休息时间", "points_reward": 5,  "keywords": ["休息"]},
    "eye_exercise": {"color": "#0ea5e9", "title": "眼保健操", "points_reward": 10, "keywords": ["眼保健操", "眼操"]},
    "exercise":     {"color": "#10b981", "title": "运动",     "points_reward": 20, "keywords": ["运动", "锻炼"]},
    "study":        {"color": "#3b82f6", "title": "",         "points_reward": 10, "keywords": []},
    "custom":       {"color": "#8b5cf6", "title": "",         "points_reward": 10, "keywords": []},
}


class ScheduleItemCreate(BaseModel):
    child_id: int
    title: str
    task_type: str = "study"
    start_time: datetime
    end_time: datetime
    color: str = "#3b82f6"
    points_reward: int = 10
    xp_reward: int = 10
    keywords: List[str] = []
    notes: str = ""
    recurrence_type: str = "none"
    recurrence_days: List[int] = []


class ScheduleItemUpdate(BaseModel):
    title: Optional[str] = None
    task_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    color: Optional[str] = None
    points_reward: Optional[int] = None
    xp_reward: Optional[int] = None
    keywords: Optional[List[str]] = None
    notes: Optional[str] = None
    recurrence_type: Optional[str] = None
    recurrence_days: Optional[List[int]] = None


def _item_to_dict(item: ScheduleItem, for_date: str, completed_dates: Dict[int, Set[str]]) -> dict:
    completed = for_date in completed_dates.get(item.id, set())
    recur_icon = " ↻" if item.recurrence_type != "none" else ""
    return {
        "id": item.id,
        "child_id": item.child_id,
        "title": item.title + recur_icon,
        "task_type": item.task_type,
        "start_time": item.start_time.isoformat(),
        "end_time": item.end_time.isoformat(),
        "color": item.color,
        "points_reward": item.points_reward,
        "xp_reward": item.xp_reward,
        "keywords": item.get_keywords(),
        "notes": item.notes,
        "recurrence_type": item.recurrence_type,
        "recurrence_days": item.get_recurrence_days(),
        "completed": completed,
        "completion_date": for_date,
    }


def _adjust_to_date(item: ScheduleItem, target: date) -> ScheduleItem:
    """Return a copy-like dict with start/end times moved to target date."""
    orig_start = item.start_time
    orig_end = item.end_time
    new_start = orig_start.replace(year=target.year, month=target.month, day=target.day)
    duration = orig_end - orig_start
    new_end = new_start + duration
    # Mutate a shallow copy via dict trick
    item.start_time = new_start
    item.end_time = new_end
    return item


def _get_completed_dates(session: Session, item_ids: List[int]) -> Dict[int, Set[str]]:
    """Map item_id -> set of completion_date strings."""
    if not item_ids:
        return {}
    comps = session.exec(
        select(Completion).where(Completion.schedule_item_id.in_(item_ids))
    ).all()
    result: Dict[int, Set[str]] = {}
    for c in comps:
        result.setdefault(c.schedule_item_id, set()).add(c.completion_date or c.completed_at.strftime("%Y-%m-%d"))
    return result


@router.get("")
def list_schedule(
    child_id: Optional[int] = None,
    date: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: Session = Depends(get_session),
):
    if date:
        return _list_for_date(session, datetime.fromisoformat(date).date(), child_id)

    if start and end:
        s = datetime.fromisoformat(start).date()
        e = datetime.fromisoformat(end).date()
        results = []
        cur = s
        while cur <= e:
            results.extend(_list_for_date(session, cur, child_id))
            cur += timedelta(days=1)
        # Deduplicate by (id, start_time)
        seen = set()
        deduped = []
        for item in results:
            key = (item["id"], item["start_time"])
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        return deduped

    # Fallback: all items
    stmt = select(ScheduleItem)
    if child_id:
        stmt = stmt.where(ScheduleItem.child_id == child_id)
    items = session.exec(stmt.order_by(ScheduleItem.start_time)).all()
    ids = [i.id for i in items]
    completed_dates = _get_completed_dates(session, ids)
    return [_item_to_dict(i, i.start_time.strftime("%Y-%m-%d"), completed_dates) for i in items]


def _list_for_date(session: Session, target: date, child_id: Optional[int]) -> List[dict]:
    stmt = select(ScheduleItem)
    if child_id:
        stmt = stmt.where(ScheduleItem.child_id == child_id)
    all_items = session.exec(stmt).all()

    target_weekday = target.weekday()  # 0=Mon..6=Sun
    matched = []

    for item in all_items:
        item_date = item.start_time.date()
        rt = item.recurrence_type

        if rt == "none":
            if item_date == target:
                matched.append(item)
        elif rt == "daily":
            if item_date <= target:
                import copy
                cloned = copy.copy(item)
                _adjust_to_date(cloned, target)
                matched.append(cloned)
        elif rt == "weekly":
            days = item.get_recurrence_days()
            if item_date <= target and target_weekday in days:
                import copy
                cloned = copy.copy(item)
                _adjust_to_date(cloned, target)
                matched.append(cloned)

    matched.sort(key=lambda x: x.start_time)
    ids = [i.id for i in matched]
    completed_dates = _get_completed_dates(session, ids)
    date_str = target.isoformat()
    return [_item_to_dict(i, date_str, completed_dates) for i in matched]


@router.post("/check-conflict")
def check_conflict(
    body: ScheduleItemCreate,
    exclude_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    """
    Check if a proposed time slot conflicts with existing items for the same child.
    Returns list of conflicting items.
    """
    target_date = body.start_time.date()
    conflicts = _find_conflicts(
        session, body.child_id, body.start_time, body.end_time,
        target_date, exclude_id
    )
    return {"has_conflict": len(conflicts) > 0, "conflicts": conflicts}


def _find_conflicts(
    session: Session,
    child_id: int,
    start_time: datetime,
    end_time: datetime,
    target_date,
    exclude_id: Optional[int] = None,
) -> List[dict]:
    """Return items that overlap with [start_time, end_time] for the given child on target_date."""
    # Fetch all items for this child
    stmt = select(ScheduleItem).where(ScheduleItem.child_id == child_id)
    if exclude_id:
        stmt = stmt.where(ScheduleItem.id != exclude_id)
    all_items = session.exec(stmt).all()

    conflicts = []
    for item in all_items:
        # Determine effective time on target_date
        rt = item.recurrence_type
        item_date = item.start_time.date()
        active = False
        if rt == "none":
            active = (item_date == target_date)
        elif rt == "daily":
            active = (item_date <= target_date)
        elif rt == "weekly":
            days = item.get_recurrence_days()
            active = (item_date <= target_date and target_date.weekday() in days)

        if not active:
            continue

        # Compute effective start/end on target_date
        eff_start = item.start_time.replace(
            year=target_date.year, month=target_date.month, day=target_date.day
        )
        duration = item.end_time - item.start_time
        eff_end = eff_start + duration

        # Overlap: start_time < eff_end AND eff_start < end_time
        if start_time < eff_end and eff_start < end_time:
            conflicts.append({
                "id": item.id,
                "title": item.title,
                "start_time": eff_start.isoformat(),
                "end_time": eff_end.isoformat(),
            })

    return conflicts


@router.post("")
def create_schedule_item(body: ScheduleItemCreate, session: Session = Depends(get_session)):
    kws = body.keywords or _extract_keywords(body.title)
    item = ScheduleItem(
        child_id=body.child_id,
        title=body.title,
        task_type=body.task_type,
        start_time=body.start_time,
        end_time=body.end_time,
        color=body.color,
        points_reward=body.points_reward,
        xp_reward=body.xp_reward,
        keywords=json.dumps(kws, ensure_ascii=False),
        notes=body.notes,
        recurrence_type=body.recurrence_type,
        recurrence_days=json.dumps(body.recurrence_days),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return _item_to_dict(item, item.start_time.strftime("%Y-%m-%d"), {})


@router.put("/{item_id}")
def update_schedule_item(item_id: int, body: ScheduleItemUpdate, session: Session = Depends(get_session)):
    item = session.get(ScheduleItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    if body.title is not None:
        item.title = body.title
    if body.task_type is not None:
        item.task_type = body.task_type
    if body.start_time is not None:
        item.start_time = body.start_time
    if body.end_time is not None:
        item.end_time = body.end_time
    if body.color is not None:
        item.color = body.color
    if body.points_reward is not None:
        item.points_reward = body.points_reward
    if body.xp_reward is not None:
        item.xp_reward = body.xp_reward
    if body.keywords is not None:
        item.set_keywords(body.keywords)
    if body.notes is not None:
        item.notes = body.notes
    if body.recurrence_type is not None:
        item.recurrence_type = body.recurrence_type
    if body.recurrence_days is not None:
        item.recurrence_days = json.dumps(body.recurrence_days)
    session.add(item)
    session.commit()
    session.refresh(item)
    return _item_to_dict(item, item.start_time.strftime("%Y-%m-%d"), {})


class BatchDeleteBody(BaseModel):
    start_date: str           # YYYY-MM-DD inclusive
    end_date: str             # YYYY-MM-DD inclusive
    child_id: Optional[int] = None
    include_recurring: bool = True


@router.post("/batch-delete")
def batch_delete(body: BatchDeleteBody, session: Session = Depends(get_session)):
    start_dt = datetime.fromisoformat(body.start_date)
    end_dt = datetime.fromisoformat(body.end_date).replace(hour=23, minute=59, second=59)

    stmt = select(ScheduleItem).where(
        ScheduleItem.start_time >= start_dt,
        ScheduleItem.start_time <= end_dt,
    )
    if body.child_id:
        stmt = stmt.where(ScheduleItem.child_id == body.child_id)
    items = list(session.exec(stmt).all())

    if body.include_recurring:
        recurring_stmt = select(ScheduleItem).where(
            ScheduleItem.recurrence_type != "none",
            ScheduleItem.start_time < start_dt,
        )
        if body.child_id:
            recurring_stmt = recurring_stmt.where(ScheduleItem.child_id == body.child_id)
        recurring = session.exec(recurring_stmt).all()
        s_date = start_dt.date()
        e_date = end_dt.date()
        existing_ids = {i.id for i in items}
        for item in recurring:
            if item.id in existing_ids:
                continue
            rt = item.recurrence_type
            days = item.get_recurrence_days()
            appears = False
            if rt == "daily":
                appears = item.start_time.date() <= e_date
            elif rt == "weekly":
                cur = s_date
                while cur <= e_date:
                    if cur.weekday() in days:
                        appears = True
                        break
                    cur += timedelta(days=1)
            if appears:
                items.append(item)

    deleted_one_time = deleted_recurring = 0
    for item in items:
        if item.recurrence_type == "none":
            deleted_one_time += 1
        else:
            deleted_recurring += 1
        session.delete(item)
    session.commit()
    return {"ok": True, "deleted_one_time": deleted_one_time, "deleted_recurring": deleted_recurring, "total": deleted_one_time + deleted_recurring}


@router.delete("/{item_id}")
def delete_schedule_item(item_id: int, session: Session = Depends(get_session)):
    item = session.get(ScheduleItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    session.delete(item)
    session.commit()
    return {"ok": True}
    """
    Delete all schedule items whose start_time falls within [start_date, end_date].
    For recurring items, deletes the template (removes all occurrences).
    Returns counts of deleted items split by type.
    """
    start_dt = datetime.fromisoformat(body.start_date)
    end_dt = datetime.fromisoformat(body.end_date).replace(hour=23, minute=59, second=59)

    stmt = select(ScheduleItem).where(
        ScheduleItem.start_time >= start_dt,
        ScheduleItem.start_time <= end_dt,
    )
    if body.child_id:
        stmt = stmt.where(ScheduleItem.child_id == body.child_id)

    items = session.exec(stmt).all()

    # Also pick up recurring items whose template starts before the range
    # (they would still show up within the range)
    if body.include_recurring:
        recurring_stmt = select(ScheduleItem).where(
            ScheduleItem.recurrence_type != "none",
            ScheduleItem.start_time < start_dt,
        )
        if body.child_id:
            recurring_stmt = recurring_stmt.where(ScheduleItem.child_id == body.child_id)
        recurring = session.exec(recurring_stmt).all()

        # Filter to those that actually appear in the range
        s_date = start_dt.date()
        e_date = end_dt.date()
        for item in recurring:
            item_date = item.start_time.date()
            rt = item.recurrence_type
            days = item.get_recurrence_days()
            appears = False
            if rt == "daily":
                appears = item_date <= e_date
            elif rt == "weekly":
                cur = s_date
                while cur <= e_date:
                    if cur.weekday() in days:
                        appears = True
                        break
                    cur += timedelta(days=1)
            if appears and item not in items:
                items.append(item)

    deleted_one_time = 0
    deleted_recurring = 0
    for item in items:
        if item.recurrence_type == "none":
            deleted_one_time += 1
        else:
            deleted_recurring += 1
        session.delete(item)

    session.commit()
    return {
        "ok": True,
        "deleted_one_time": deleted_one_time,
        "deleted_recurring": deleted_recurring,
        "total": deleted_one_time + deleted_recurring,
    }


def _extract_keywords(title: str) -> List[str]:
    try:
        import jieba.analyse
        return jieba.analyse.extract_tags(title, topK=3)
    except Exception:
        return [title]
