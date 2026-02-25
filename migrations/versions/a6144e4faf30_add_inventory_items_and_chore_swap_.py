"""Add inventory items (and chore swap requests if missing)

Revision ID: a6144e4faf30
Revises: 992af69e95a9
Create Date: 2026-01-29 17:51:48.812736
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "a6144e4faf30"
down_revision = "992af69e95a9"
branch_labels = None
depends_on = None


def _index_exists(conn, index_name: str) -> bool:
    inspector = inspect(conn)
    for table_name in inspector.get_table_names():
        for idx in inspector.get_indexes(table_name):
            if idx.get("name") == index_name:
                return True
    return False


def _table_exists(conn, table_name):
    from sqlalchemy import inspect
    inspector = inspect(conn)
    return table_name in inspector.get_table_names()


def upgrade():
    conn = op.get_bind()

    # ---------------------------------------------------------
    # CLEANUP: if a previous batch alter failed, SQLite temp tables can be left behind
    # ---------------------------------------------------------
    conn.exec_driver_sql("DROP TABLE IF EXISTS _alembic_tmp_chore_swap_request;")

    # ---------------------------------------------------------
    # inventory_item (create only if missing)
    # ---------------------------------------------------------
    if not _table_exists(conn, "inventory_item"):
        op.create_table(
            "inventory_item",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("household_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit", sa.String(length=40), nullable=True),
            sa.Column("notes", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["household_id"], ["household.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _index_exists(conn, "ix_inventory_item_household_id"):
        with op.batch_alter_table("inventory_item", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_inventory_item_household_id"),
                ["household_id"],
                unique=False,
            )

    # ---------------------------------------------------------
    # chore indexes (create only if missing)
    # ---------------------------------------------------------
    if not _index_exists(conn, "ix_chore_assigned_to_user_id"):
        with op.batch_alter_table("chore", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_chore_assigned_to_user_id"),
                ["assigned_to_user_id"],
                unique=False,
            )

    if not _index_exists(conn, "ix_chore_household_id"):
        with op.batch_alter_table("chore", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_chore_household_id"),
                ["household_id"],
                unique=False,
            )

    # ---------------------------------------------------------
    # chore_swap_request: make requested_chore_id nullable
    # ---------------------------------------------------------
    if _table_exists(conn, "chore_swap_request"):
        inspector = inspect(conn)
        cols = {c["name"] for c in inspector.get_columns("chore_swap_request")}
        if "requested_chore_id" in cols:
            # (Extra safety) drop temp table again before batch alter runs
            conn.exec_driver_sql("DROP TABLE IF EXISTS _alembic_tmp_chore_swap_request;")

            with op.batch_alter_table("chore_swap_request", schema=None) as batch_op:
                batch_op.alter_column(
                    "requested_chore_id",
                    existing_type=sa.INTEGER(),
                    nullable=True,
                )

    # ---------------------------------------------------------
    # expense indexes (create only if missing)
    # ---------------------------------------------------------
    if not _index_exists(conn, "ix_expense_household_id"):
        with op.batch_alter_table("expense", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_expense_household_id"),
                ["household_id"],
                unique=False,
            )

    if not _index_exists(conn, "ix_expense_paid_by_user_id"):
        with op.batch_alter_table("expense", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_expense_paid_by_user_id"),
                ["paid_by_user_id"],
                unique=False,
            )

    # ---------------------------------------------------------
    # expense_share indexes (create only if missing)
    # ---------------------------------------------------------
    if not _index_exists(conn, "ix_expense_share_expense_id"):
        with op.batch_alter_table("expense_share", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_expense_share_expense_id"),
                ["expense_id"],
                unique=False,
            )

    if not _index_exists(conn, "ix_expense_share_user_id"):
        with op.batch_alter_table("expense_share", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_expense_share_user_id"),
                ["user_id"],
                unique=False,
            )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    # Drop indexes/tables only if they exist (safe rollback)
    if inspector.has_table("expense_share"):
        share_indexes = {ix["name"] for ix in inspector.get_indexes("expense_share")}
        with op.batch_alter_table("expense_share", schema=None) as batch_op:
            if "ix_expense_share_user_id" in share_indexes:
                batch_op.drop_index(batch_op.f("ix_expense_share_user_id"))
            if "ix_expense_share_expense_id" in share_indexes:
                batch_op.drop_index(batch_op.f("ix_expense_share_expense_id"))

    if inspector.has_table("expense"):
        exp_indexes = {ix["name"] for ix in inspector.get_indexes("expense")}
        with op.batch_alter_table("expense", schema=None) as batch_op:
            if "ix_expense_paid_by_user_id" in exp_indexes:
                batch_op.drop_index(batch_op.f("ix_expense_paid_by_user_id"))
            if "ix_expense_household_id" in exp_indexes:
                batch_op.drop_index(batch_op.f("ix_expense_household_id"))

    if inspector.has_table("chore_swap_request"):
        cols = {c["name"] for c in inspector.get_columns("chore_swap_request")}
        if "requested_chore_id" in cols:
            # NOTE: only revert if you truly want it NOT NULL again
            with op.batch_alter_table("chore_swap_request", schema=None) as batch_op:
                batch_op.alter_column(
                    "requested_chore_id",
                    existing_type=sa.INTEGER(),
                    nullable=False,
                )

    if inspector.has_table("chore"):
        chore_indexes = {ix["name"] for ix in inspector.get_indexes("chore")}
        with op.batch_alter_table("chore", schema=None) as batch_op:
            if "ix_chore_household_id" in chore_indexes:
                batch_op.drop_index(batch_op.f("ix_chore_household_id"))
            if "ix_chore_assigned_to_user_id" in chore_indexes:
                batch_op.drop_index(batch_op.f("ix_chore_assigned_to_user_id"))

    if inspector.has_table("inventory_item"):
        inv_indexes = {ix["name"] for ix in inspector.get_indexes("inventory_item")}
        with op.batch_alter_table("inventory_item", schema=None) as batch_op:
            if "ix_inventory_item_household_id" in inv_indexes:
                batch_op.drop_index(batch_op.f("ix_inventory_item_household_id"))
        op.drop_table("inventory_item")
