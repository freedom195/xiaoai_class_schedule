# -*- coding: utf-8 -*-
"""
Scheduler — checks every minute for tasks that should be announced now.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from sqlmodel import Session, select

from database import Child, ScheduleItem, Completion, engine
from xiaomi_client import xiaomi_client
from ws_manager import ws_manager

logger = logging.getLogger(__name__)

# How many minutes before start_time to broadcast the opening announcement
ADVANCE_MINUTES = 1


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
    )


def _build_end_tts(child_name: str, item: ScheduleItem) -> str:
    return f"{child_name}，{item.title}时间到啦！完成了吗？"


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
