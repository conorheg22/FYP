"""Add inventory Step 2 fields (category, sub_category, location) safely for SQLite

Revision ID: 20260129_inv_step2
Revises: 992af69e95a9
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = "20260129_inv_step2"
down_revision = "992af69e95a9"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name):
    from sqlalchemy import inspect
    inspector = inspect(conn)
    return table_name in inspector.get_table_names()


def _column_exists(conn, table_name, column_name):
    from sqlalchemy import inspect
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def _index_exists(conn, index_name: str) -> bool:
    from sqlalchemy import inspect
    inspector = inspect(conn)
    for table_name in inspector.get_table_names():
        for idx in inspector.get_indexes(table_name):
            if idx.get("name") == index_name:
                return True
    return False


def upgrade():
    conn = op.get_bind()

    # 1) Ensure inventory_item table exists (safe for your messy state)
    if not _table_exists(conn, "inventory_item"):
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory_item (
                id INTEGER NOT NULL PRIMARY KEY,
                household_id INTEGER NOT NULL,
                name VARCHAR(120) NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit VARCHAR(40),
                notes VARCHAR(255),
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY(household_id) REFERENCES household (id)
            );
            """
        )

    # 2) Add Step 2 columns only if missing
    # SQLite supports ALTER TABLE ADD COLUMN
    if not _column_exists(conn, "inventory_item", "category"):
        op.execute("ALTER TABLE inventory_item ADD COLUMN category VARCHAR(60);")

    if not _column_exists(conn, "inventory_item", "sub_category"):
        op.execute("ALTER TABLE inventory_item ADD COLUMN sub_category VARCHAR(80);")

    if not _column_exists(conn, "inventory_item", "location"):
        op.execute("ALTER TABLE inventory_item ADD COLUMN location VARCHAR(60);")

    # 3) Add index for household_id if missing (helps queries)
    # Use a stable index name; IF NOT EXISTS not supported everywhere, so we check first.
    if not _index_exists(conn, "ix_inventory_item_household_id"):
        op.execute("CREATE INDEX ix_inventory_item_household_id ON inventory_item (household_id);")


def downgrade():
    # SQLite cannot DROP COLUMN reliably without table rebuild.
    # Keep downgrade as a no-op to avoid breaking local dev DB.
    pass
