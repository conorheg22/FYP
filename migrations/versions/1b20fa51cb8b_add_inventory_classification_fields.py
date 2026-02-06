"""Add inventory classification fields

Revision ID: REPLACE_WITH_YOURS
Revises: REPLACE_WITH_YOURS
Create Date: REPLACE_WITH_YOURS
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "REPLACE_WITH_YOURS"
down_revision = "REPLACE_WITH_YOURS"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    # Safety: only run if the table exists
    if not inspector.has_table("inventory_item"):
        return

    cols = {c["name"] for c in inspector.get_columns("inventory_item")}

    with op.batch_alter_table("inventory_item", schema=None) as batch_op:
        if "category" not in cols:
            batch_op.add_column(sa.Column("category", sa.String(length=40), nullable=True))
        if "sub_category" not in cols:
            batch_op.add_column(sa.Column("sub_category", sa.String(length=60), nullable=True))
        if "location" not in cols:
            batch_op.add_column(sa.Column("location", sa.String(length=40), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    if not inspector.has_table("inventory_item"):
        return

    cols = {c["name"] for c in inspector.get_columns("inventory_item")}

    with op.batch_alter_table("inventory_item", schema=None) as batch_op:
        if "location" in cols:
            batch_op.drop_column("location")
        if "sub_category" in cols:
            batch_op.drop_column("sub_category")
        if "category" in cols:
            batch_op.drop_column("category")
