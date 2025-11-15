# Standard SQLAlchemy models structure; adapted from Flask-SQLAlchemy documentation (Pallets, 2024)
from datetime import datetime    # Lets us store the date/time a record is created
from . import db                 # Imports the database connection from __init__.py

class Chore(db.Model):           # Defines a 'Chore' table
    __tablename__ = "chore"
    id = db.Column(db.Integer, primary_key=True)         # Unique ID number
    title = db.Column(db.String(140), nullable=False)    # Chore name
    completed = db.Column(db.Boolean, nullable=False, default=False)  # Done or not
    created_at = db.Column(db.DateTime, default=datetime.utcnow)      # Time created

class Household(db.Model):       # Defines a 'Household' table
    __tablename__ = "household"
    id = db.Column(db.Integer, primary_key=True)         # Unique ID
    name = db.Column(db.String(120), nullable=False)     # Household name
    address = db.Column(db.String(255))                  # Optional address
    invite_code = db.Column(db.String(10), unique=True, nullable=False)  # Code to join
    created_at = db.Column(db.DateTime, default=datetime.utcnow)        # Time created
