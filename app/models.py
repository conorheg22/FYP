"""
Database models for the application.

Defines the core data entities used by the system:
- Household: a shared group for chores and expenses
- User: an individual registered account
- Chore: a task belonging to a household
- Expense: a shared household cost
- ExpenseShare: the per-user share of an expense
"""

from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from . import db


# ---------------------------------------------------------
# Household
# ---------------------------------------------------------
class Household(db.Model):
    """
    Represents a household that users belong to.

    A household acts as the main boundary for data access:
    - All chores belong to one household
    - All expenses belong to one household
    - Users are members of a household
    """
    __tablename__ = "household"

    # Primary identifier for the household
    id = db.Column(db.Integer, primary_key=True)

    # Display name for the household
    name = db.Column(db.String(120), nullable=False)

    # Optional address information
    address = db.Column(db.String(255))

    # Short unique code used to join a household
    invite_code = db.Column(db.String(10), unique=True, nullable=False)

    # Timestamp of household creation
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships:
    # - chores: all chores associated with this household
    # - expenses: all expenses associated with this household
    chores = db.relationship("Chore", backref="household", lazy=True)
    expenses = db.relationship("Expense", backref="household", lazy=True)

    # Relationship to users who are members of this household.
    # Explicit foreign_keys is required because User has two references to household.
    users = db.relationship(
        "User",
        backref="household",
        lazy=True,
        foreign_keys="User.household_id"
    )


# ---------------------------------------------------------
# User
# ---------------------------------------------------------
class User(db.Model):
    """
    Represents a registered user account.

    Users belong to one household and can:
    - Be assigned chores
    - Pay expenses
    - Owe or be owed money through expense shares
    """
    __tablename__ = "user"

    # Primary identifier for the user
    id = db.Column(db.Integer, primary_key=True)

    # User's display name
    name = db.Column(db.String(80), nullable=False)

    # Email address used for login (unique and indexed)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)

    # Hashed password (never stores plain text passwords)
    password_hash = db.Column(db.String(255), nullable=False)

    # Account creation timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Household membership:
    # - household_id defines which household the user belongs to
    # - active_household_id stores the last selected household for UI convenience
    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=True,
        index=True,
    )

    active_household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=True,
    )

    # Relationships:
    # - assigned_chores: chores assigned to this user
    # - paid_expenses: expenses paid by this user
    # - expense_shares: expense portions owed by this user
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

    # -----------------------------------------------------
    # Password helpers
    # -----------------------------------------------------
    # Encapsulates password hashing logic to keep routes clean.
    def set_password(self, password: str) -> None:
        """Hash and store the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verify a plain-text password against the stored hash."""
        return check_password_hash(self.password_hash, password)


# ---------------------------------------------------------
# Chore
# ---------------------------------------------------------
class Chore(db.Model):
    """
    Represents a single chore within a household.

    Chores may:
    - Be assigned to a user
    - Have an optional due date
    - Be marked as completed
    """
    __tablename__ = "chore"

    # Primary identifier for the chore
    id = db.Column(db.Integer, primary_key=True)

    # Short description of the chore
    title = db.Column(db.String(200), nullable=False)

    # Completion status flag
    completed = db.Column(db.Boolean, default=False)

    # Creation timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Foreign key linking the chore to its household
    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=False,
    )

    # Optional assignment to a user
    assigned_to_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    # Optional due date used for sorting and status display
    due_date = db.Column(db.Date, nullable=True)


# ---------------------------------------------------------
# Expense
# ---------------------------------------------------------
class Expense(db.Model):
    """
    Represents a shared expense within a household.

    Each expense:
    - Belongs to one household
    - Is paid by one user
    - Is split into multiple ExpenseShare records
    """
    __tablename__ = "expense"

    # Primary identifier for the expense
    id = db.Column(db.Integer, primary_key=True)

    # Short description of the expense
    title = db.Column(db.String(120), nullable=False)

    # Total amount paid for the expense
    total_amount = db.Column(db.Float, nullable=False)

    # Foreign key linking the expense to a household
    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=False,
    )

    # Foreign key identifying which user paid the expense
    paid_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    # Timestamp of expense creation
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to per-user expense shares.
    # Cascade delete ensures shares are removed if the expense is deleted.
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
    """
    Represents the amount a specific user owes for an expense.
    """
    __tablename__ = "expense_share"

    # Primary identifier for the expense share
    id = db.Column(db.Integer, primary_key=True)

    # Foreign key linking to the expense
    expense_id = db.Column(
        db.Integer,
        db.ForeignKey("expense.id"),
        nullable=False,
    )

    # Foreign key linking to the user who owes this amount
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    # Monetary amount owed by the user
    amount_owed = db.Column(db.Float, nullable=False)
