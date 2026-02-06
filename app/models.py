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

from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from . import db


# ---------------------------------------------------------
# Household
# ---------------------------------------------------------
class Household(db.Model):
    """I use this model to represent a household that shares chores, expenses, and inventory."""
    __tablename__ = "household"

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

    # I keep swap requests linked to the household for cleanup and navigation.
    swap_requests = db.relationship(
        "ChoreSwapRequest",
        backref="household",
        lazy=True,
        cascade="all, delete-orphan",
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
class User(db.Model):
    """I use this model to represent a registered user account."""
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
class Chore(db.Model):
    """I use this model to represent a single chore inside a household."""
    __tablename__ = "chore"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # This links the chore to its household.
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


# ---------------------------------------------------------
# Expense
# ---------------------------------------------------------
class Expense(db.Model):
    """I use this model to represent a shared household expense."""
    __tablename__ = "expense"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)

    # This links the expense to the correct household.
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
class ExpenseShare(db.Model):
    """I use this model to store how much one user owes for a specific expense."""
    __tablename__ = "expense_share"

    id = db.Column(db.Integer, primary_key=True)

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
class ChoreSwapRequest(db.Model):
    """I use this model to represent a request to swap chores between two users."""
    __tablename__ = "chore_swap_request"

    id = db.Column(db.Integer, primary_key=True)

    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=True,
        index=True,
    )

    # This is the user asking for the swap.
    from_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )

    # This is the user who must accept or decline.
    to_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )

    # This is the chore offered by the requester.
    offered_chore_id = db.Column(
        db.Integer,
        db.ForeignKey("chore.id"),
        nullable=False,
        index=True,
    )

    # This is the chore owned by the recipient (v1 logic still allows None).
    requested_chore_id = db.Column(
        db.Integer,
        db.ForeignKey("chore.id"),
        nullable=False,
        index=True,
    )

    # I track the state so requests can be accepted or declined.
    status = db.Column(db.String(20), nullable=False, default="pending")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)

    # These relationships make template access easier (e.g. swap.offered_chore.title).
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
class InventoryItem(db.Model):
    """I use this model to represent shared household inventory items."""
    __tablename__ = "inventory_item"

    id = db.Column(db.Integer, primary_key=True)

    # This links the item to its household.
    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=False,
        index=True,
    )

    name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit = db.Column(db.String(40), nullable=True)
    notes = db.Column(db.String(255), nullable=True)

    category = db.Column(db.String(40), nullable=True)
    sub_category = db.Column(db.String(60), nullable=True)
    location = db.Column(db.String(40), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # use_count tracks how often an item is used or edited.
    # Logic informed by AI-assisted guidance for inventory usage tracking.
    # Source: ChatGPT – Inventory low-stock & frequent-items prompt (Feb 2026)- https://chatgpt.com/share/69865b3d-3e40-8007-b7fd-0ff594971ab5

    # I increment this to track which items are used most often.
    use_count = db.Column(db.Integer, nullable=False, default=0)

    # I store expiry info so the app can warn users before items go bad.
    expiry_type = db.Column(db.String(20), nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)


# ---------------------------------------------------------
# Notification (NEW)
# ---------------------------------------------------------
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

    # If this is None, the notification is visible to everyone in the household.
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        index=True,
    )

    # This helps the app know what kind of notification it is.
    type = db.Column(db.String(40), nullable=False)

    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(255), nullable=False)

    # I use this link so clicking the notification takes the user to the right page.
    link_url = db.Column(db.String(255), nullable=True)

    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)