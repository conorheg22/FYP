"""
One-off script to add the user.role column to the database.

Run from project root with: python add_user_role_column.py

Use this if you hit "no such column: user.role" and prefer not to fix the
migration history right now. Safe to run multiple times (skips if column exists).
"""
import os
import sys

# Project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text, inspect


def main():
    app = create_app()
    with app.app_context():
        conn = db.engine.connect()
        inspector = inspect(conn)
        if not inspector.has_table("user"):
            print("Table 'user' not found. Exiting.")
            return
        cols = {c["name"] for c in inspector.get_columns("user")}
        if "role" in cols:
            print("Column user.role already exists. Nothing to do.")
            return
        conn.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR(40)"))
        conn.commit()
        conn.close()
        print("Added column user.role successfully.")


if __name__ == "__main__":
    main()
