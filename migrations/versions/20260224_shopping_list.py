"""Add shopping list and min_stock on inventory

Revision ID: 20260224_shopping
Revises: 20260224_rewards
Create Date: 2026-02-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260224_shopping"
down_revision = "20260224_rewards"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    # Add min_stock to inventory_item (optional threshold for "Add to Shopping List").
    if inspector.has_table("inventory_item"):
        cols = {c["name"] for c in inspector.get_columns("inventory_item")}
        if "min_stock" not in cols:
            with op.batch_alter_table("inventory_item", schema=None) as batch_op:
                batch_op.add_column(sa.Column("min_stock", sa.Integer(), nullable=True))

    # Create shopping_list_item table (shared household shopping list).
    if not inspector.has_table("shopping_list_item"):
        op.create_table(
            "shopping_list_item",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("household_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("unit", sa.String(40), nullable=True),
            sa.Column("category", sa.String(40), nullable=True),
            sa.Column("picked_up", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("inventory_item_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["household_id"], ["household.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_item.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_shopping_list_item_household_id"), "shopping_list_item", ["household_id"])
        op.create_index(op.f("ix_shopping_list_item_inventory_item_id"), "shopping_list_item", ["inventory_item_id"])


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    if inspector.has_table("shopping_list_item"):
        op.drop_index(op.f("ix_shopping_list_item_inventory_item_id"), table_name="shopping_list_item")
        op.drop_index(op.f("ix_shopping_list_item_household_id"), table_name="shopping_list_item")
        op.drop_table("shopping_list_item")

    if inspector.has_table("inventory_item"):
        cols = {c["name"] for c in inspector.get_columns("inventory_item")}
        if "min_stock" in cols:
            with op.batch_alter_table("inventory_item", schema=None) as batch_op:
                batch_op.drop_column("min_stock")
