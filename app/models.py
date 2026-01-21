"""
Database models for the application.

Defines the main entities:
- Household: a group of users sharing chores and expenses
- User: registered user account
- Chore: individual tasks linked to a household (and optionally a user)
- Expense: shared household expense
- ExpenseShare: per-user share of an expense
"""

from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from . import db


# ---------------------------------------------------------
# Household
# ---------------------------------------------------------
class Household(db.Model):
    """Represents a household / family / group that shares chores and expenses."""
    __tablename__ = "household"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255))
    invite_code = db.Column(db.String(10), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    chores = db.relationship("Chore", backref="household", lazy=True)
    expenses = db.relationship("Expense", backref="household", lazy=True)

    # IMPORTANT:
    # User has TWO FKs pointing at Household (household_id + active_household_id).
    # This relationship MUST specify which FK is used for membership.
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
    """Represents a registered user of the system."""
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # user belongs to one household (simple membership model)
    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=True,
        index=True,
    )

    # persisted "active household" for restoring after logout/login
    active_household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=True,
        index=True,
    )

    # Relationship for active household must specify FK to avoid ambiguity
    active_household = db.relationship(
        "Household",
        foreign_keys=[active_household_id],
        uselist=False,
    )

    # Relationships
    assigned_chores = db.relationship(
        "Chore",
        backref="assignee",
        lazy=True,
        foreign_keys="Chore.assigned_to_user_id",
    )

    paid_expenses = db.relationship(
        "Expense",
        backref="payer",
        lazy=True,
        foreign_keys="Expense.paid_by_user_id",
    )

    expense_shares = db.relationship(
        "ExpenseShare",
        backref="user",
        lazy=True,
    )

    # ---- Password helpers ----
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


# ---------------------------------------------------------
# Chore
# ---------------------------------------------------------
class Chore(db.Model):
    """Represents a single chore/task in a household."""
    __tablename__ = "chore"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=False,
    )

    assigned_to_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    due_date = db.Column(db.Date, nullable=True)


# ---------------------------------------------------------
# Expense
# ---------------------------------------------------------
class Expense(db.Model):
    """Represents a shared household expense."""
    __tablename__ = "expense"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)

    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=False,
    )

    paid_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
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
    """Represents how much a specific user owes for an expense."""
    __tablename__ = "expense_share"

    id = db.Column(db.Integer, primary_key=True)

    expense_id = db.Column(
        db.Integer,
        db.ForeignKey("expense.id"),
        nullable=False,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    amount_owed = db.Column(db.Float, nullable=False)
