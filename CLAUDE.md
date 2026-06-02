# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**暑假课表系统 (Summer Schedule System)** — a Chinese-language web app for managing children's summer schedules, integrated with Xiaomi (Xiaoai) smart speakers for voice announcements and task completion recognition. Features a gamified points/level/badge system.

## Tech Stack

- **Backend**: Python 3.8+, FastAPI 0.111.0, uvicorn 0.29.0
- **ORM**: SQLModel 0.0.19 (SQLAlchemy + Pydantic) with SQLite
- **Xiaomi Integration**: miservice-fork 2.3.4 (TTS + conversation polling)
- **Real-time**: websockets 12.0 for WebSocket broadcast
- **Frontend**: Vue 3 + FullCalendar 6 + Chart.js 4 (all via CDN, no build step)

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server (listens on 0.0.0.0:8080)
python main.py

# Enable hot reload during development: change reload=False to reload=True in main.py line ~133

# Run database migration (only needed for pre-existing DBs missing new columns)
python migrate.py

# Docker
docker compose up -d --build    # start
docker compose logs -f          # view logs
docker compose down             # stop
```

There are **no tests** in this project currently.

## Architecture

### Concurrency Model

Single-process asyncio event loop. FastAPI handles HTTP/WebSocket while two background `asyncio.create_task()` loops run concurrently:

- `scheduler_loop(device_id)` — runs every 60s, checks for tasks starting/ending, sends TTS announcements
- `voice_poller_loop(device_id)` — runs every 5s, polls Xiaomi conversation history, parses completion utterances via jieba keyword matching

### Data Model (7 SQLModel tables)

- **Child** — id, name, avatar_emoji, level, total_xp, available_points
- **ScheduleItem** — child_id, title, task_type, start_time, end_time, color, points_reward, xp_reward, keywords (JSON), notes, recurrence_type, recurrence_days (JSON)
- **Completion** — schedule_item_id, child_id, completion_date (YYYY-MM-DD), completed_at, voice_raw, points_awarded, xp_awarded
- **PointsTransaction** — child_id, delta, reason, created_at
- **RedemptionRequest** — child_id, reward_name, points_cost, status (pending/approved/rejected), parent_note
- **Badge** — child_id, badge_type, awarded_at
- **AppConfig** — key/value store (holds encrypted Xiaomi credentials)

### Key Modules

| File | Purpose |
|---|---|
| `main.py` | FastAPI entry point, route mounting, lifespan, uvicorn startup |
| `database.py` | SQLModel ORM models, SQLite engine, session helpers |
| `config.py` | Fernet symmetric encryption for Xiaomi password |
| `xiaomi_client.py` | miservice-fork wrapper (TTS + conversation polling) |
| `scheduler.py` | Background loop: checks every 60s for task start/end announcements |
| `voice_poller.py` | Background loop: polls every 5s for voice completion utterances |
| `points_engine.py` | Points/XP settlement, level-up logic, badge awarding |
| `ws_manager.py` | WebSocket broadcast manager for real-time frontend updates |
| `api/children.py` | Child CRUD REST endpoints |
| `api/schedule.py` | Schedule CRUD + conflict detection + batch delete |
| `api/points.py` | Completions, points ledger, redemption requests + approval |
| `api/stats.py` | Statistics with daily completion rate + streak calc |

### Security

- Xiaomi passwords encrypted with Fernet (symmetric)
- Key derived via PBKDF2HMAC from `APP_SECRET` env var or machine-specific ID (Windows MachineGuid or `/etc/machine-id`)

## Environment Variables

- `DATA_DIR` — directory for SQLite DB and auth files (default: `.`)
- `APP_SECRET` — optional override for encryption key derivation

## Notes for Development

- **No build step** — frontend is served as static files directly from `static/`. Changes are visible on page refresh.
- **Database** — SQLite file at `./class_schedule.db` (or `./data/class_schedule.db` in Docker). Open with any SQLite client.
- **Adding API endpoints** — create functions in the appropriate `api/*.py` file; routers are already registered in `main.py`.
- **Adding frontend pages** — create a component in `static/components/`, load it in `index.html`, and add a nav entry in the sidebar.
- **APScheduler** is listed in `requirements.txt` but not currently used; the app uses raw `asyncio.sleep()` loops instead.
- **No pyproject.toml** — dependencies managed purely via `requirements.txt`.
