# One-off script to add assigned_to_user_id column to inventory_item. Run from project root: python add_inventory_assigned_to_column.py
import os
import sqlite3

# Path to the SQLite database file (instance/app.db relative to project root).
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance", "app.db")


def column_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in cur.fetchall())


def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}. Create the app and run it once, then run this script.")
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if not column_exists(cur, "inventory_item", "assigned_to_user_id"):
        cur.execute(
            "ALTER TABLE inventory_item ADD COLUMN assigned_to_user_id INTEGER REFERENCES user(id);"
        )
        conn.commit()
        print("Added assigned_to_user_id to inventory_item.")
    else:
        print("Column assigned_to_user_id already exists.")

    conn.close()


if __name__ == "__main__":
    main()
