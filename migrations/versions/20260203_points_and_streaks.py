"""Add points, streaks, and chore completion tracking

Revision ID: 20260203_pts
Revises: 20260202_role
Create Date: 2026-02-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260203_pts"
down_revision = "20260202_role"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    if inspector.has_table("user"):
        cols = {c["name"] for c in inspector.get_columns("user")}
        with op.batch_alter_table("user", schema=None) as batch_op:
            if "points" not in cols:
                batch_op.add_column(sa.Column("points", sa.Integer(), server_default=sa.text("0")))
            if "streak_count" not in cols:
                batch_op.add_column(sa.Column("streak_count", sa.Integer(), server_default=sa.text("0")))
            if "last_streak_date" not in cols:
                batch_op.add_column(sa.Column("last_streak_date", sa.Date(), nullable=True))

    if inspector.has_table("chore"):
        cols = {c["name"] for c in inspector.get_columns("chore")}
        with op.batch_alter_table("chore", schema=None) as batch_op:
            if "completed_at" not in cols:
                batch_op.add_column(sa.Column("completed_at", sa.DateTime(), nullable=True))
            if "completed_by_id" not in cols:
                batch_op.add_column(sa.Column("completed_by_id", sa.Integer(), nullable=True))
            if "points_awarded" not in cols:
                batch_op.add_column(sa.Column("points_awarded", sa.Integer(), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    if inspector.has_table("chore"):
        cols = {c["name"] for c in inspector.get_columns("chore")}
        with op.batch_alter_table("chore", schema=None) as batch_op:
            if "points_awarded" in cols:
                batch_op.drop_column("points_awarded")
            if "completed_by_id" in cols:
                batch_op.drop_column("completed_by_id")
            if "completed_at" in cols:
                batch_op.drop_column("completed_at")

    if inspector.has_table("user"):
        cols = {c["name"] for c in inspector.get_columns("user")}
        with op.batch_alter_table("user", schema=None) as batch_op:
            if "last_streak_date" in cols:
                batch_op.drop_column("last_streak_date")
            if "streak_count" in cols:
                batch_op.drop_column("streak_count")
            if "points" in cols:
                batch_op.drop_column("points")
