"""Database models for the application.

Defines the main entities:
- Household: a group of users sharing chores
- User: registered user account
- Chore: individual tasks linked to a household (and optionally a user)
"""

from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from . import db


class Household(db.Model):
    """Represents a household / family / group that shares chores.

    Each household can have many chores.
    """
    __tablename__ = "household"

    id = db.Column(db.Integer, primary_key=True)          # Unique ID for the household
    name = db.Column(db.String(120), nullable=False)      # Household name (e.g. "Hegarty Home")
    address = db.Column(db.String(255))                   # Optional address field
    invite_code = db.Column(
        db.String(10), unique=True, nullable=False
    )  # Code used so others can join the household
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow
    )  # Timestamp when household was created

    # One-to-many relationship: Household -> Chore
    chores = db.relationship("Chore", backref="household", lazy=True)


class User(db.Model):
    """Represents a registered user of the system.

    Handles login, password hashing, and links to chores assigned to the user.
    """
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)          # Unique user ID
    name = db.Column(db.String(80), nullable=False)       # Display name
    email = db.Column(
        db.String(120), unique=True, nullable=False, index=True
    )  # Login email (unique + indexed for faster lookups)
    password_hash = db.Column(
        db.String(255), nullable=False
    )  # Hashed password, never stored in plain text
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow
    )  # Account creation time

    # Relationship to chores that have been assigned to this user
    assigned_chores = db.relationship(
        "Chore",
        backref="assignee",
        lazy=True,
        foreign_keys="Chore.assigned_to_user_id",
    )

    # ---- Password helper methods ----
    def set_password(self, password: str) -> None:
        """Hash and store the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check a plain text password against the stored hash."""
        return check_password_hash(self.password_hash, password)


class Chore(db.Model):
    """Represents a single chore/task in a household.

    Each chore:
    - Belongs to exactly one household
    - May be assigned to a specific user
    - May have an optional due date
    """
    __tablename__ = "chore"

    id = db.Column(db.Integer, primary_key=True)          # Unique chore ID
    title = db.Column(db.String(200), nullable=False)     # Short description (e.g. "Mop floors")
    completed = db.Column(
        db.Boolean, default=False
    )  # Whether the chore has been marked done
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow
    )  # When the chore was created

    # Foreign key linking the chore to a household (required)
    household_id = db.Column(
        db.Integer,
        db.ForeignKey("household.id"),
        nullable=False,
    )

    # Optional foreign key linking the chore to a specific user (assignee)
    assigned_to_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    # Optional due date for reminders and sorting
    due_date = db.Column(db.Date, nullable=True)
