"""
One-off migration: make chore_swap_request.requested_chore_id nullable in SQLite.
The model already has nullable=True; the DB table was created with NOT NULL.
Run once: python fix_swap_requested_chore_nullable.py
"""
# We need the app and database; the upgrade uses raw SQLite to recreate the table.
import os
import sys

# Run from project root so app can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db


def upgrade():
    """Recreate chore_swap_request so requested_chore_id allows NULL."""
    conn = db.engine.raw_connection()
    try:
        cur = conn.cursor()
        # SQLite doesn't support ALTER COLUMN; recreate table.
        cur.execute("""
            CREATE TABLE chore_swap_request_new (
                id INTEGER NOT NULL PRIMARY KEY,
                household_id INTEGER,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                offered_chore_id INTEGER NOT NULL,
                requested_chore_id INTEGER,
                status VARCHAR(20) NOT NULL,
                created_at DATETIME,
                responded_at DATETIME,
                FOREIGN KEY(household_id) REFERENCES household (id),
                FOREIGN KEY(from_user_id) REFERENCES user (id),
                FOREIGN KEY(to_user_id) REFERENCES user (id),
                FOREIGN KEY(offered_chore_id) REFERENCES chore (id),
                FOREIGN KEY(requested_chore_id) REFERENCES chore (id)
            )
        """)
        cur.execute("""
            INSERT INTO chore_swap_request_new
            (id, household_id, from_user_id, to_user_id, offered_chore_id,
             requested_chore_id, status, created_at, responded_at)
            SELECT id, household_id, from_user_id, to_user_id, offered_chore_id,
                   requested_chore_id, status, created_at, responded_at
            FROM chore_swap_request
        """)
        cur.execute("DROP TABLE chore_swap_request")
        cur.execute("ALTER TABLE chore_swap_request_new RENAME TO chore_swap_request")
        # Recreate indexes used by the model
        cur.execute("CREATE INDEX ix_chore_swap_request_household_id ON chore_swap_request (household_id)")
        cur.execute("CREATE INDEX ix_chore_swap_request_from_user_id ON chore_swap_request (from_user_id)")
        cur.execute("CREATE INDEX ix_chore_swap_request_to_user_id ON chore_swap_request (to_user_id)")
        cur.execute("CREATE INDEX ix_chore_swap_request_offered_chore_id ON chore_swap_request (offered_chore_id)")
        cur.execute("CREATE INDEX ix_chore_swap_request_requested_chore_id ON chore_swap_request (requested_chore_id)")
        conn.commit()
        print("chore_swap_request.requested_chore_id is now nullable.")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


# When run directly, create the app and run the upgrade inside an app context.
if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        upgrade()
