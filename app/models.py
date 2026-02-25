"""
Database models for the application.

Defines the main entities:
- Household: a group of users sharing chores, expenses, and inventory
- User: registered user account
- Chore: individual tasks linked to a household (and optionally a user)
- Expense: shared household expense
- ExpenseShare: per-user share of an expense
- ChoreSwapRequest: request to swap chores between two users in a household
- InventoryItem: shared supplies / inventory items for a household
"""

# We need datetime for default timestamps and Werkzeug for safe password hashing.
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
# db is the SQLAlchemy instance from __init__.py; we use it to define tables and columns.
from . import db


# ---------------------------------------------------------
# Household
# ---------------------------------------------------------
# A household is one group (e.g. a flat or family) that shares chores, expenses, and inventory.
class Household(db.Model):
    """I use this model to represent a household that shares chores, expenses, and inventory."""
    __tablename__ = "household"

    # Each household has a unique id, a name, an optional address, and a unique code so others can join.
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255))
    invite_code = db.Column(db.String(10), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # I link chores to a household so everything stays grouped correctly.
    chores = db.relationship("Chore", backref="household", lazy=True)

    # I link expenses here so I can easily fetch all household spending.
    expenses = db.relationship("Expense", backref="household", lazy=True)

    # Inventory items belong to a household and should be deleted if the household is removed.
    inventory_items = db.relationship(
        "InventoryItem",
        backref="household",
        lazy=True,
        cascade="all, delete-orphan",
    )

    # Shared shopping list for the household (all members see the same list).
    shopping_list_items = db.relationship(
        "ShoppingListItem",
        backref="household",
        lazy=True,
        cascade="all, delete-orphan",
    )

    # I keep swap requests linked to the household for cleanup and navigation.
    swap_requests = db.relationship(
        "ChoreSwapRequest",
        backref="household",
        lazy=True,
        cascade="all, delete-orphan",
    )

    # Leaderboard: optional reward for the weekly leader (pre-made or custom).
    selected_leader_reward_id = db.Column(
        db.Integer,
        db.ForeignKey("leaderboard_reward.id"),
        nullable=True,
        index=True,
    )
    selected_leader_reward = db.relationship(
        "LeaderboardReward",
        foreign_keys=[selected_leader_reward_id],
        uselist=False,
    )

    # Custom rewards created by this household (pre-made rewards have household_id=None).
    leaderboard_rewards = db.relationship(
        "LeaderboardReward",
        backref="household",
        lazy=True,
        foreign_keys="LeaderboardReward.household_id",
    )

    # IMPORTANT:
    # A user has two household references, so I explicitly choose which one defines membership.
    users = db.relationship(
        "User",
        backref="household",
        lazy=True,
        foreign_keys="User.household_id",
    )


# ---------------------------------------------------------
# User
# ---------------------------------------------------------
# A user is one person with an account. They can belong to one household and have points and streaks from doing chores.
class User(db.Model):
    """I use this model to represent a registered user account."""
    __tablename__ = "user"

    # Basic account info: id, name, email (unique), and a hashed password so we never store the real password.
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Optional role shown on profile (e.g. "Member", "Admin"); not used for permissions in this app.
    role = db.Column(db.String(40), nullable=True)
    # Points and streak are used for the leaderboard; they increase when the user completes chores.
    points = db.Column(db.Integer, default=0)
    streak_count = db.Column(db.Integer, default=0)
    last_streak_date = db.Column(db.Date, nullable=True)
    # Profile extras: avatar image filename, exam mode flag, dietary/cleaning/availability notes, and whether notifications are on.
    avatar_filename = db.Column(db.String(255))
    exam_mode = db.Column(db.Boolean, default=False)
    dietary_restrictions = db.Column(db.Text)
    cleaning_preferences = db.Column(db.Text)
    availability_notes = db.Column(db.Text)
    notifications_enabled = db.Column(db.Boolean, default=True)

    # This links the user to the household they belong to.
    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=True,
        index=True,
    )

    # I store the last active household so it can be restored on login.
    active_household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=True,
        index=True,
    )

    # I define this separately to avoid ambiguity between the two household links.
    active_household = db.relationship(
        "Household",
        foreign_keys=[active_household_id],
        uselist=False,
    )

    # These are the chores currently assigned to this user.
    assigned_chores = db.relationship(
        "Chore",
        backref="assignee",
        lazy=True,
        foreign_keys="Chore.assigned_to_user_id",
    )

    # These are the expenses this user paid for.
    paid_expenses = db.relationship(
        "Expense",
        backref="payer",
        lazy=True,
        foreign_keys="Expense.paid_by_user_id",
    )

    # This lets me see how much the user owes across all expenses.
    expense_shares = db.relationship(
        "ExpenseShare",
        backref="user",
        lazy=True,
    )

    # Swap requests this user has sent to others.
    swap_requests_sent = db.relationship(
        "ChoreSwapRequest",
        backref="from_user",
        lazy=True,
        foreign_keys="ChoreSwapRequest.from_user_id",
    )

    # Swap requests this user has received.
    swap_requests_received = db.relationship(
        "ChoreSwapRequest",
        backref="to_user",
        lazy=True,
        foreign_keys="ChoreSwapRequest.to_user_id",
    )

    # ---- Password helpers ----
    # I hash passwords before saving them for security.
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    # I use this to check login passwords safely.
    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


# ---------------------------------------------------------
# Chore
# ---------------------------------------------------------
# Allowed values for repeat_type so we can validate and create the next due date when a chore is completed.
CHORE_REPEAT_TYPES = ("none", "daily", "weekly", "monthly")


# A chore is one task in a household. It can be assigned to a user, have a due date, and repeat daily, weekly, or monthly.
class Chore(db.Model):
    """I use this model to represent a single chore inside a household."""
    __tablename__ = "chore"

    # Core fields: id, title, whether it is done, and when it was created.
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Which household this chore belongs to.
    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=False,
        index=True,
    )

    # This is optional because chores can be unassigned.
    assigned_to_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        index=True,
    )

    # I use this date to track deadlines and calendar events.
    due_date = db.Column(db.Date, nullable=True)
    # When and who completed this chore (for points, streaks, and "completed by" display).
    completed_at = db.Column(db.DateTime, nullable=True)
    completed_by_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        index=True,
    )
    # Points awarded for this completion (so we can show "earned +10" and deduct on undo).
    points_awarded = db.Column(db.Integer, nullable=True)

    # Recurring: "none" (default), "daily", "weekly", "monthly". When completed, a new chore is created with next due date.
    repeat_type = db.Column(db.String(20), nullable=False, default="none")
    # Estimated time in minutes (for workload/fairness view).
    estimated_minutes = db.Column(db.Integer, nullable=True)
    # True if the chore was completed after its due_date (for overdue stats).
    was_overdue = db.Column(db.Boolean, default=False, nullable=False)

    completed_by = db.relationship(
        "User",
        foreign_keys=[completed_by_id],
        backref="chores_completed",
    )


# ---------------------------------------------------------
# Expense
# ---------------------------------------------------------
# An expense is one shared cost (e.g. groceries) paid by one person and split between household members.
class Expense(db.Model):
    """I use this model to represent a shared household expense."""
    __tablename__ = "expense"

    # Expense has an id, title, total amount, and is linked to a household and the user who paid.
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)

    # Which household this expense belongs to.
    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=False,
        index=True,
    )

    # This stores who actually paid for the expense.
    paid_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # These rows define how the expense is split between users.
    shares = db.relationship(
        "ExpenseShare",
        backref="expense",
        cascade="all, delete-orphan",
        lazy=True,
    )


# ---------------------------------------------------------
# ExpenseShare
# ---------------------------------------------------------
# Each row is one person’s share of one expense (how much they owe for that expense).
class ExpenseShare(db.Model):
    """I use this model to store how much one user owes for a specific expense."""
    __tablename__ = "expense_share"

    id = db.Column(db.Integer, primary_key=True)

    # Which expense this share is for.
    expense_id = db.Column(
        db.Integer,
        db.ForeignKey("expense.id"),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )

    # I store this as a float because it represents money.
    amount_owed = db.Column(db.Float, nullable=False)


# ---------------------------------------------------------
# ChoreSwapRequest
# ---------------------------------------------------------
# A swap request is when one user asks another to take over a chore. It stays pending until the other user accepts or declines.
class ChoreSwapRequest(db.Model):
    """I use this model to represent a request to swap chores between two users."""
    __tablename__ = "chore_swap_request"

    id = db.Column(db.Integer, primary_key=True)

    # Which household the swap is in (so we can filter and clean up).
    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=True,
        index=True,
    )

    # The user who wants to give away their chore.
    from_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )

    # The user who can accept or decline the swap.
    to_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )

    # The chore that the requester wants to give away.
    offered_chore_id = db.Column(
        db.Integer,
        db.ForeignKey("chore.id"),
        nullable=False,
        index=True,
    )

    # The chore from the recipient that could be swapped (in the current logic this can be unused/placeholder).
    requested_chore_id = db.Column(
        db.Integer,
        db.ForeignKey("chore.id"),
        nullable=False,
        index=True,
    )

    # Status is "pending", "accepted", or "declined" so we know what happened to the request.
    status = db.Column(db.String(20), nullable=False, default="pending")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)

    # Relationships so we can do things like swap.offered_chore.title in templates and code.
    offered_chore = db.relationship(
        "Chore",
        foreign_keys=[offered_chore_id],
        lazy=True,
    )
    requested_chore = db.relationship(
        "Chore",
        foreign_keys=[requested_chore_id],
        lazy=True,
    )


# ---------------------------------------------------------
# InventoryItem (NEW - backlog item 12)
# ---------------------------------------------------------
# Reference: SQLAlchemy ORM relationships and patterns
# https://docs.sqlalchemy.org/en/21/orm/basic_relationships.html
# https://docs.sqlalchemy.org/en/13/orm/tutorial.html
# An inventory item is something the household tracks (e.g. milk, soap) with quantity, location, and optional expiry.
class InventoryItem(db.Model):
    """I use this model to represent shared household inventory items."""
    __tablename__ = "inventory_item"

    id = db.Column(db.Integer, primary_key=True)

    # Which household this item belongs to.
    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=False,
        index=True,
    )

    # Item name, how many we have, optional unit (e.g. "bottle"), and notes.
    name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit = db.Column(db.String(40), nullable=True)
    notes = db.Column(db.String(255), nullable=True)

    # Optional grouping: category (e.g. Food), sub_category, and where it is stored (e.g. Fridge).
    category = db.Column(db.String(40), nullable=True)
    sub_category = db.Column(db.String(60), nullable=True)
    location = db.Column(db.String(40), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # How many times this item was used or edited; used to show "frequently used" items.
    # Logic informed by AI-assisted guidance for inventory usage tracking.
    # Source: ChatGPT – Inventory low-stock & frequent-items prompt (Feb 2026)- https://chatgpt.com/share/69865b3d-3e40-8007-b7fd-0ff594971ab5

    # I increment this to track which items are used most often.
    use_count = db.Column(db.Integer, nullable=False, default=0)

    # I store expiry info so the app can warn users before items go bad.
    expiry_type = db.Column(db.String(20), nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)

    # Optional minimum stock threshold: when quantity <= min_stock, "Add to Shopping List" is shown.
    # Default 0 means the button appears when quantity hits zero.
    min_stock = db.Column(db.Integer, nullable=True, default=0)


# ---------------------------------------------------------
# ShoppingListItem
# ---------------------------------------------------------
# A shared household shopping list. Items can be added manually or from inventory when low/out of stock.
# When an item is marked "picked up", the user can be prompted to update the linked inventory item.
class ShoppingListItem(db.Model):
    """I use this model to represent one item on the household's shared shopping list."""
    __tablename__ = "shopping_list_item"

    id = db.Column(db.Integer, primary_key=True)

    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=False,
        index=True,
    )

    name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit = db.Column(db.String(40), nullable=True)
    category = db.Column(db.String(40), nullable=True)

    # True when someone has picked up the item while shopping (checkbox on the list).
    picked_up = db.Column(db.Boolean, default=False, nullable=False)

    # Optional link to an inventory item: used when added from inventory and for "update stock?" prompt.
    inventory_item_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_item.id"),
        nullable=True,
        index=True,
    )
    inventory_item = db.relationship(
        "InventoryItem",
        foreign_keys=[inventory_item_id],
        backref=db.backref("shopping_list_entries", lazy="dynamic"),
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------------------------------------------------------
# Notification (NEW)
# ---------------------------------------------------------
# A notification is a message shown in the app (e.g. as a toast). It can be for the whole household or for one user.
# Notification model design (household-scoped + optional user-scoped).
# Implemented with AI-assisted guidance for in-app notifications storage and fields.
# Source: ChatGPT conversation – Notifications feature prompt (Feb 2026) - https://chatgpt.com/share/69865e70-4154-8007-b020-98259faaf812

class Notification(db.Model):
    """
    I use this model to store in-app notifications that appear as toast messages.
    Notifications are saved so users don’t see the same message repeatedly.
    """
    __tablename__ = "notification"

    id = db.Column(db.Integer, primary_key=True)

    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=False,
        index=True,
    )

    # If user_id is None, the notification is for the whole household; otherwise it is for that user only.
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        index=True,
    )

    # Type tells us the kind of notification (e.g. chore_due, expense_new) for styling or filtering.
    type = db.Column(db.String(40), nullable=False)

    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(255), nullable=False)

    # Optional URL so when the user clicks the notification they go to the right page (e.g. chores or expenses).
    link_url = db.Column(db.String(255), nullable=True)

    # Once the user has seen it, we mark it read so we do not show it again.
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships so we can load notifications for a household or for a user.
    household = db.relationship("Household", backref=db.backref("notifications", lazy="dynamic"))
    user = db.relationship("User", backref=db.backref("notifications", lazy="dynamic"))


# ---------------------------------------------------------
# LeaderboardReward
# ---------------------------------------------------------
# Rewards for the weekly leader: pre-made (household_id NULL) or custom per household.
# The household selects one reward as "the prize" for the current leader.
class LeaderboardReward(db.Model):
    """Reward option for the leaderboard winner (e.g. 'Buy the leader a pint')."""
    __tablename__ = "leaderboard_reward"

    id = db.Column(db.Integer, primary_key=True)

    # NULL = pre-made reward; set = custom reward for this household.
    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=True,
        index=True,
    )

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # For custom rewards, who added it (optional).
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        index=True,
    )
    created_by = db.relationship("User", backref="created_rewards", foreign_keys=[created_by_user_id])