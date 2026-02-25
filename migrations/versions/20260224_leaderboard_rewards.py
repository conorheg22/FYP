"""Add leaderboard rewards (pre-made + custom) and household selection

Revision ID: 20260224_rewards
Revises: 20260213_chore
Create Date: 2026-02-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260224_rewards"
down_revision = "20260213_chore"
branch_labels = None
depends_on = None


PREMADE_REWARDS = [
    ("Buy the leader a pint", "The rest of the household buys the leader a pint (or drink of choice)."),
    ("Leader chooses the movie night", "This week the leader picks the film for movie night."),
    ("Leader gets a lie-in", "Others make breakfast – leader gets a lie-in."),
    ("Losers do the leader's washing", "Bottom of the board does the leader's washing for one week."),
    ("Leader picks the takeaway", "Leader chooses what's for takeaway night."),
    ("Control of the remote", "Leader gets control of the TV remote for the week."),
    ("Treat the leader to a coffee", "Household treats the leader to a coffee (or hot drink)."),
    ("Free pass on one chore", "Leader gets a free pass on one chore next week."),
    ("Cook the leader dinner", "Someone else cooks dinner for the leader one night."),
    ("Leader chooses weekend activity", "Leader picks what the household does this weekend."),
    ("No washing-up for the leader", "Leader is off washing-up duty for the week."),
    ("Leader gets the best seat", "Leader has dibs on the best spot on the sofa all week."),
]


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    if not inspector.has_table("leaderboard_reward"):
        op.create_table(
            "leaderboard_reward",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("household_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["household_id"], ["household.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_leaderboard_reward_household_id"), "leaderboard_reward", ["household_id"])
        op.create_index(op.f("ix_leaderboard_reward_created_by_user_id"), "leaderboard_reward", ["created_by_user_id"])

    if inspector.has_table("household"):
        cols = {c["name"] for c in inspector.get_columns("household")}
        if "selected_leader_reward_id" not in cols:
            with op.batch_alter_table("household", schema=None) as batch_op:
                batch_op.add_column(sa.Column("selected_leader_reward_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_household_selected_leader_reward",
                    "leaderboard_reward",
                    ["selected_leader_reward_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
                batch_op.create_index("ix_household_selected_leader_reward_id", ["selected_leader_reward_id"])

    # Seed pre-made rewards (household_id NULL).
    table = sa.table(
        "leaderboard_reward",
        sa.column("id", sa.Integer),
        sa.column("household_id", sa.Integer),
        sa.column("title", sa.String(200)),
        sa.column("description", sa.Text),
        sa.column("created_at", sa.DateTime),
        sa.column("created_by_user_id", sa.Integer),
    )
    # Get next id(s). Use a simple approach: insert with explicit ids.
    result = conn.execute(sa.text("SELECT COALESCE(MAX(id), 0) FROM leaderboard_reward"))
    start_id = (result.scalar() or 0) + 1
    for i, (title, desc) in enumerate(PREMADE_REWARDS):
        conn.execute(
            sa.text(
                "INSERT INTO leaderboard_reward (id, household_id, title, description, created_at, created_by_user_id) "
                "VALUES (:id, NULL, :title, :description, CURRENT_TIMESTAMP, NULL)"
            ),
            {"id": start_id + i, "title": title, "description": desc or None},
        )


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    if inspector.has_table("household"):
        cols = {c["name"] for c in inspector.get_columns("household")}
        if "selected_leader_reward_id" in cols:
            with op.batch_alter_table("household", schema=None) as batch_op:
                batch_op.drop_constraint("fk_household_selected_leader_reward", type_="foreignkey")
                batch_op.drop_index("ix_household_selected_leader_reward_id")
                batch_op.drop_column("selected_leader_reward_id")

    if inspector.has_table("leaderboard_reward"):
        op.drop_index(op.f("ix_leaderboard_reward_created_by_user_id"), table_name="leaderboard_reward")
        op.drop_index(op.f("ix_leaderboard_reward_household_id"), table_name="leaderboard_reward")
        op.drop_table("leaderboard_reward")
