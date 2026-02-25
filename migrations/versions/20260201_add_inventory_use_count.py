"""Add inventory use_count for frequently used items

Revision ID: 20260201_use_count
Revises: 20260129_inv_step2
Create Date: 2026-02-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "20260201_use_count"
down_revision = "20260129_inv_step2"
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


def upgrade():
    conn = op.get_bind()
    if not _table_exists(conn, "inventory_item"):
        return
    if not _column_exists(conn, "inventory_item", "use_count"):
        op.execute(
            "ALTER TABLE inventory_item ADD COLUMN use_count INTEGER NOT NULL DEFAULT 0;"
        )


def downgrade():
    # SQLite: dropping columns requires table rebuild; leave column in place or no-op
    pass
