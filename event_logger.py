# -*- coding: utf-8 -*-
"""
Event logger — records interaction events to date-based log files.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(os.environ.get("DATA_DIR", ".")) / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_event_logger = logging.getLogger("events")
_event_logger.setLevel(logging.INFO)
_event_logger.propagate = False

_current_date = datetime.now().strftime("%Y-%m-%d")


def _make_handler():
    log_file = LOG_DIR / f"{_current_date}.log"
    h = logging.FileHandler(str(log_file), encoding="utf-8")
    h.setFormatter(logging.Formatter(
        "%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    return h


_handler = _make_handler()
_event_logger.addHandler(_handler)


def _rotate_if_needed():
    global _current_date, _handler
    today = datetime.now().strftime("%Y-%m-%d")
    if today != _current_date:
        _event_logger.removeHandler(_handler)
        _handler.close()
        _current_date = today
        _handler = _make_handler()
        _event_logger.addHandler(_handler)


def log_event(category: str, detail: str):
    """Record an interaction event.

    category: COMPLETION | VOICE | SCHEDULE | CHILD | REDEMPTION | TTS | SYSTEM
    """
    _rotate_if_needed()
    _event_logger.info("%-12s | %s", category, detail)


def read_logs(date_str: str | None = None) -> list[str]:
    """Read log lines for a given date (default today)."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"{date_str}.log"
    if not log_file.exists():
        return []
    return log_file.read_text(encoding="utf-8").strip().split("\n")


def list_log_dates() -> list[str]:
    """Return sorted list of dates that have log files."""
    dates = [f.stem for f in LOG_DIR.glob("*.log")]
    return sorted(dates, reverse=True)
