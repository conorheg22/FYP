from flask import Blueprint, render_template, redirect, url_for, request, abort, flash
from .models import Chore, Household    # Imports database models
from . import db                        # Imports database connection
import random, string                   # Used for creating invite codes

# Reference: ChatGPT (2025) Help with chore routing.
# Conversation available at: https://chatgpt.com/share/690e52e9-fc0c-8007-8140-00c1baa0f87e
# ChatGPT provided guidance on structuring Flask routes for CRUD operations
# (add, edit, delete, and mark done) and connecting them to SQLAlchemy models.


main_bp = Blueprint("main", __name__)   # Creates a blueprint for routes

# ChatGPT (2025) assisted with this route structure
@main_bp.route("/")                     # Home page route
def index():
    return render_template("index.html")  # Shows homepage template

# ---------- Chores ----------
@main_bp.route("/db-test")
def db_test_list():
    chores = Chore.query.order_by(Chore.created_at.desc()).all()  # Get all chores
    return render_template("db_test.html", chores=chores)          # Show them in template

# ChatGPT (2025) assisted with toggle route logic and redirect handling
@main_bp.route("/db-test/add", methods=["POST"])
def db_test_add():
    title = (request.form.get("title") or "").strip()  # Get new chore title
    if not title:                                      # Ignore if empty
        return redirect(url_for("main.db_test_list"))
    c = Chore(title=title)                             # Create new chore
    db.session.add(c)                                  # Add to database
    db.session.commit()                                # Save
    return redirect(url_for("main.db_test_list"))      # Reload page

# ChatGPT (2025) assisted with toggle route logic and redirect handling
@main_bp.route("/db-test/<int:chore_id>/toggle", methods=["POST"])
def db_test_toggle(chore_id: int):
    chore = Chore.query.get_or_404(chore_id)           # Find chore by ID
    chore.completed = not chore.completed               # Flip True/False
    db.session.commit()                                # Save changes
    return redirect(url_for("main.db_test_list"))

# ChatGPT (2025) assisted with toggle route logic and redirect handling
@main_bp.route("/db-test/<int:chore_id>/delete", methods=["POST"])
def db_test_delete(chore_id: int):
    chore = Chore.query.get_or_404(chore_id)           # Find chore
    db.session.delete(chore)                           # Remove from DB
    db.session.commit()                                # Save
    return redirect(url_for("main.db_test_list"))

# ChatGPT (2025) assisted with toggle route logic and redirect handling
@main_bp.route("/db-test/<int:chore_id>/edit", methods=["GET", "POST"])
def db_test_edit(chore_id: int):
    chore = Chore.query.get_or_404(chore_id)           # Get chore
    if request.method == "POST":                       # When form is submitted
        title = (request.form.get("title") or "").strip()
        if title:
            chore.title = title                        # Update title
            db.session.commit()
            return redirect(url_for("main.db_test_list"))
    return render_template("edit_chore.html", chore=chore)  # Show edit form

# ---------- Household ----------
@main_bp.route("/create_household", methods=["GET", "POST"])
def create_household():
    if request.method == "POST":
        name = request.form.get("name")                # Get name
        address = request.form.get("address")          # Get address
        if not name:
            flash("Please enter a household name.", "warning")
            return redirect(url_for("main.create_household"))
        invite_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))  # Make code
        new_house = Household(name=name, address=address, invite_code=invite_code)          # Create record
        db.session.add(new_house)
        db.session.commit()
        return render_template("household_created.html", household=new_house)  # Show confirmation
    return render_template("create_household.html")     # Show form

@main_bp.route("/join_household", methods=["GET", "POST"])
def join_household():
    joined_household = None
    if request.method == "POST":
        code = request.form.get("invite_code")          # Get code from form
        household = Household.query.filter_by(invite_code=code).first()  # Check database
        if household:
            joined_household = household
            flash(f"Successfully joined household: {household.name}", "success")
        else:
            flash("Invalid invite code. Please try again.", "danger")
    return render_template("join_household.html", household=joined_household)  # Show result
