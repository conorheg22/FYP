import sqlite3

DB_PATH = r"C:\Users\joanne\Projects\FYP\instance\app.db"

def column_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in cur.fetchall())

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if not column_exists(cur, "inventory_item", "category"):
        cur.execute("ALTER TABLE inventory_item ADD COLUMN category VARCHAR(60);")

    if not column_exists(cur, "inventory_item", "sub_category"):
        cur.execute("ALTER TABLE inventory_item ADD COLUMN sub_category VARCHAR(80);")

    if not column_exists(cur, "inventory_item", "location"):
        cur.execute("ALTER TABLE inventory_item ADD COLUMN location VARCHAR(60);")

    conn.commit()
    conn.close()
    print("Done. Inventory columns ensured.")

if __name__ == "__main__":
    main()
