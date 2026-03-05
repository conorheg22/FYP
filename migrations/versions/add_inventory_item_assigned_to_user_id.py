"""Add assigned_to_user_id to inventory_item

Revision ID: add_inv_assigned
Revises:
Create Date: Adds column inventory_item.assigned_to_user_id for optional assignment to a household member.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_inv_assigned"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add assigned_to_user_id to inventory_item (nullable FK to user.id).
    # Safe to run if column already exists on SQLite (we use try/except for SQLite).
    op.add_column(
        "inventory_item",
        sa.Column("assigned_to_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_inventory_item_assigned_to_user_id_user",
        "inventory_item",
        "user",
        ["assigned_to_user_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_inventory_item_assigned_to_user_id"),
        "inventory_item",
        ["assigned_to_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_inventory_item_assigned_to_user_id"),
        table_name="inventory_item",
    )
    op.drop_constraint(
        "fk_inventory_item_assigned_to_user_id_user",
        "inventory_item",
        type_="foreignkey",
    )
    op.drop_column("inventory_item", "assigned_to_user_id")
