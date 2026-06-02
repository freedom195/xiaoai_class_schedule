from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from sqlmodel import Field, SQLModel, create_engine, Session, select
import json
import os

# DATA_DIR: 存放数据库和认证文件的目录，Docker 挂载时指向 volume
DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR / 'class_schedule.db'}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


class Child(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    avatar_emoji: str = "👦"
    level: int = 1
    total_xp: int = 0
    available_points: int = 0
    created_at: datetime = Field(default_factory=datetime.now)


class ScheduleItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    child_id: int = Field(foreign_key="child.id")
    title: str
    task_type: str = "study"          # study | rest | eye_exercise | exercise | custom
    start_time: datetime
    end_time: datetime
    color: str = "#3b82f6"
    points_reward: int = 10
    xp_reward: int = 10
    keywords: str = "[]"              # JSON array stored as text
    notes: str = ""
    voice_modified: bool = False     # True if title was changed via voice command
    original_title: str = ""         # Previous title before voice modification
    cancelled_dates: str = "[]"       # JSON array of date strings (YYYY-MM-DD) that are cancelled
    recurrence_type: str = "none"     # none | daily | weekly
    recurrence_days: str = "[]"       # JSON array of weekday ints (0=Mon..6=Sun), weekly only

    def get_keywords(self) -> List[str]:
        return json.loads(self.keywords)

    def set_keywords(self, kws: List[str]):
        self.keywords = json.dumps(kws, ensure_ascii=False)

    def get_recurrence_days(self) -> List[int]:
        return json.loads(self.recurrence_days)

    def get_cancelled_dates(self) -> List[str]:
        return json.loads(self.cancelled_dates)

    def cancel_date(self, date_str: str):
        dates = self.get_cancelled_dates()
        if date_str not in dates:
            dates.append(date_str)
        self.cancelled_dates = json.dumps(dates)


class Completion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    schedule_item_id: int = Field(foreign_key="scheduleitem.id")
    child_id: int = Field(foreign_key="child.id")
    completion_date: str = ""         # YYYY-MM-DD, for recurring items
    completed_at: datetime = Field(default_factory=datetime.now)
    voice_raw: Optional[str] = None
    points_awarded: int = 0
    xp_awarded: int = 0


class PointsTransaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    child_id: int = Field(foreign_key="child.id")
    delta: int
    reason: str
    created_at: datetime = Field(default_factory=datetime.now)


class RedemptionRequest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    child_id: int = Field(foreign_key="child.id")
    reward_name: str
    points_cost: int
    status: str = "pending"   # pending / approved / rejected
    parent_note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None


class Badge(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    child_id: int = Field(foreign_key="child.id")
    badge_type: str
    awarded_at: datetime = Field(default_factory=datetime.now)


class AppConfig(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = ""


def init_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


def get_config(session: Session, key: str) -> Optional[str]:
    row = session.get(AppConfig, key)
    return row.value if row else None


def set_config(session: Session, key: str, value: str):
    row = session.get(AppConfig, key)
    if row:
        row.value = value
    else:
        row = AppConfig(key=key, value=value)
        session.add(row)
    session.commit()
