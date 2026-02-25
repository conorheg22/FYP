"""Add chore repeat_type, estimated_minutes, was_overdue

Revision ID: 20260213_chore
Revises: 20260203_pts
Create Date: 2026-02-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260213_chore"
down_revision = "20260203_pts"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    if inspector.has_table("chore"):
        cols = {c["name"] for c in inspector.get_columns("chore")}
        with op.batch_alter_table("chore", schema=None) as batch_op:
            if "repeat_type" not in cols:
                batch_op.add_column(
                    sa.Column("repeat_type", sa.String(20), nullable=False, server_default="none")
                )
            if "estimated_minutes" not in cols:
                batch_op.add_column(sa.Column("estimated_minutes", sa.Integer(), nullable=True))
            if "was_overdue" not in cols:
                batch_op.add_column(
                    sa.Column("was_overdue", sa.Boolean(), nullable=False, server_default=sa.text("0"))
                )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    if inspector.has_table("chore"):
        cols = {c["name"] for c in inspector.get_columns("chore")}
        with op.batch_alter_table("chore", schema=None) as batch_op:
            if "was_overdue" in cols:
                batch_op.drop_column("was_overdue")
            if "estimated_minutes" in cols:
                batch_op.drop_column("estimated_minutes")
            if "repeat_type" in cols:
                batch_op.drop_column("repeat_type")
