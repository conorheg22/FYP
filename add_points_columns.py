"""
One-off script to add points and streak columns (user + chore).

Run from project root: python add_points_columns.py

Use if you get "no such column" for points, streak_count, last_streak_date,
completed_at, completed_by_id, or points_awarded. Safe to run multiple times.
"""
# We need the app and database, plus SQLAlchemy to run SQL and inspect tables.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text, inspect


# Add points and streak columns to user, and completion columns to chore, if they are missing.
def main():
    app = create_app()
    with app.app_context():
        conn = db.engine.connect()
        inspector = inspect(conn)

        if inspector.has_table("user"):
            cols = {c["name"] for c in inspector.get_columns("user")}
            for col, sql in [
                ("points", "ALTER TABLE user ADD COLUMN points INTEGER DEFAULT 0"),
                ("streak_count", "ALTER TABLE user ADD COLUMN streak_count INTEGER DEFAULT 0"),
                ("last_streak_date", "ALTER TABLE user ADD COLUMN last_streak_date DATE"),
            ]:
                if col not in cols:
                    conn.execute(text(sql))
                    conn.commit()
                    print(f"Added user.{col}")

        if inspector.has_table("chore"):
            cols = {c["name"] for c in inspector.get_columns("chore")}
            for col, sql in [
                ("completed_at", "ALTER TABLE chore ADD COLUMN completed_at DATETIME"),
                ("completed_by_id", "ALTER TABLE chore ADD COLUMN completed_by_id INTEGER"),
                ("points_awarded", "ALTER TABLE chore ADD COLUMN points_awarded INTEGER"),
            ]:
                if col not in cols:
                    conn.execute(text(sql))
                    conn.commit()
                    print(f"Added chore.{col}")

        conn.close()
        print("Done.")


if __name__ == "__main__":
    main()
