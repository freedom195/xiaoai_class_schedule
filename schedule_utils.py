# -*- coding: utf-8 -*-
"""
Shared helpers for querying schedule items with recurrence support.
"""
from datetime import datetime
from typing import List
from sqlmodel import Session, select

from database import ScheduleItem


def _is_recurrence_active_on(item: ScheduleItem, target_date) -> bool:
    """Check if a recurring item is active on target_date, respecting end_date."""
    item_date = item.start_time.date()
    rt = item.recurrence_type
    weekday = target_date.weekday()

    if rt == "daily":
        if item_date > target_date:
            return False
    elif rt == "weekly":
        days = item.get_recurrence_days()
        if item_date > target_date or weekday not in days:
            return False
    else:
        return False

    # Check recurrence_end_date cap
    end_str = getattr(item, "recurrence_end_date", None)
    if end_str:
        try:
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            if target_date > end_date:
                return False
        except (ValueError, TypeError):
            pass

    # Check cancelled dates
    if target_date.isoformat() in item.get_cancelled_dates():
        return False

    return True


def get_items_active_in_window(
    session: Session,
    window_start: datetime,
    window_end: datetime,
    child_id: int | None = None,
) -> List[ScheduleItem]:
    """Return items whose *effective* time overlaps [window_start, window_end].

    For non-recurring items, the raw start_time/end_time are used directly.
    For recurring (daily/weekly) items, effective times are computed for
    the date of window_start, since recurring items store their original
    creation date.
    """
    today = window_start.date()
    today_end = datetime.combine(today, datetime.max.time())

    # Non-recurring items overlapping the window
    stmt = select(ScheduleItem).where(
        ScheduleItem.recurrence_type == "none",
        ScheduleItem.start_time < window_end,
        ScheduleItem.end_time > window_start,
    )
    if child_id:
        stmt = stmt.where(ScheduleItem.child_id == child_id)
    non_recurring = session.exec(stmt).all()

    # Recurring items whose original date is on or before today
    stmt = select(ScheduleItem).where(
        ScheduleItem.recurrence_type != "none",
        ScheduleItem.start_time <= today_end,
    )
    if child_id:
        stmt = stmt.where(ScheduleItem.child_id == child_id)
    recurring = session.exec(stmt).all()

    result = list(non_recurring)

    for item in recurring:
        if not _is_recurrence_active_on(item, today):
            continue

        eff_start = item.start_time.replace(
            year=today.year, month=today.month, day=today.day
        )
        duration = item.end_time - item.start_time
        eff_end = eff_start + duration

        if eff_start < window_end and eff_end > window_start:
            result.append(item)

    return result


def get_items_starting_in_window(
    session: Session,
    window_start: datetime,
    window_end: datetime,
) -> List[ScheduleItem]:
    """Return items whose effective start_time falls in [window_start, window_end]."""
    today = window_start.date()
    today_end = datetime.combine(today, datetime.max.time())

    # Non-recurring
    stmt = select(ScheduleItem).where(
        ScheduleItem.recurrence_type == "none",
        ScheduleItem.start_time >= window_start,
        ScheduleItem.start_time <= window_end,
    )
    non_recurring = session.exec(stmt).all()

    # Recurring
    stmt = select(ScheduleItem).where(
        ScheduleItem.recurrence_type != "none",
        ScheduleItem.start_time <= today_end,
    )
    recurring = session.exec(stmt).all()

    result = list(non_recurring)

    for item in recurring:
        if not _is_recurrence_active_on(item, today):
            continue

        eff_start = item.start_time.replace(
            year=today.year, month=today.month, day=today.day
        )
        if window_start <= eff_start <= window_end:
            result.append(item)

    return result


def get_items_ending_in_window(
    session: Session,
    window_start: datetime,
    window_end: datetime,
) -> List[ScheduleItem]:
    """Return items whose effective end_time falls in [window_start, window_end]."""
    today = window_start.date()
    today_end = datetime.combine(today, datetime.max.time())

    # Non-recurring
    stmt = select(ScheduleItem).where(
        ScheduleItem.recurrence_type == "none",
        ScheduleItem.end_time >= window_start,
        ScheduleItem.end_time <= window_end,
    )
    non_recurring = session.exec(stmt).all()

    # Recurring
    stmt = select(ScheduleItem).where(
        ScheduleItem.recurrence_type != "none",
        ScheduleItem.start_time <= today_end,
    )
    recurring = session.exec(stmt).all()

    result = list(non_recurring)

    for item in recurring:
        if not _is_recurrence_active_on(item, today):
            continue

        eff_start = item.start_time.replace(
            year=today.year, month=today.month, day=today.day
        )
        duration = item.end_time - item.start_time
        eff_end = eff_start + duration

        if window_start <= eff_end <= window_end:
            result.append(item)

    return result
