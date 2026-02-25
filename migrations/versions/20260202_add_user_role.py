"""Add user.role column for profile page

Revision ID: 20260202_role
Revises: 20260201_use_count
Create Date: 2026-02-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260202_role"
down_revision = ("1b20fa51cb8b", "a6144e4faf30")
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    if not inspector.has_table("user"):
        return
    cols = {c["name"] for c in inspector.get_columns("user")}
    if "role" in cols:
        return
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("role", sa.String(length=40), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    if not inspector.has_table("user"):
        return
    cols = {c["name"] for c in inspector.get_columns("user")}
    if "role" not in cols:
        return
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("role")
