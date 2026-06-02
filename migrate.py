"""Add recurrence and task_type fields to existing database."""
import sqlite3

conn = sqlite3.connect("class_schedule.db")
cur = conn.cursor()

existing = {row[1] for row in cur.execute("PRAGMA table_info(scheduleitem)")}

migrations = [
    ("task_type",        "ALTER TABLE scheduleitem ADD COLUMN task_type TEXT NOT NULL DEFAULT 'study'"),
    ("recurrence_type",  "ALTER TABLE scheduleitem ADD COLUMN recurrence_type TEXT NOT NULL DEFAULT 'none'"),
    ("recurrence_days",  "ALTER TABLE scheduleitem ADD COLUMN recurrence_days TEXT NOT NULL DEFAULT '[]'"),
]
for col, sql in migrations:
    if col not in existing:
        cur.execute(sql)
        print(f"Added column: {col}")
    else:
        print(f"Already exists: {col}")

existing_comp = {row[1] for row in cur.execute("PRAGMA table_info(completion)")}
if "completion_date" not in existing_comp:
    cur.execute("ALTER TABLE completion ADD COLUMN completion_date TEXT NOT NULL DEFAULT ''")
    print("Added column: completion_date")
else:
    print("Already exists: completion_date")

conn.commit()
conn.close()
print("Migration done.")
