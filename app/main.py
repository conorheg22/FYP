"""Main application routes and business logic.

Contains:
- Authentication (register, login, logout)
- Household creation, joining, and management
- Chore CRUD operations (add, edit, delete, mark done)
- Chore assignment and due-date handling
"""

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    abort,
    flash,
    session,
)
from .models import Chore, Household, User
from . import db
import random, string
from functools import wraps
from datetime import date, datetime  # Used for due date and filtering

# ---------------------------------------------------------
# Blueprint Setup
# ---------------------------------------------------------
# This blueprint groups all routes under a single logical module ("main")
main_bp = Blueprint("main", __name__)   # Used as url_for("main.some_route")


# ---------------------------------------------------------
# Login Required Decorator
# ---------------------------------------------------------
def login_required(f):
    """Decorator to protect routes so only logged-in users can access them."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        # If there's no user_id in the session, user is not logged in
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("main.login"))
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------
# Helper: get the currently active household from the session
# ---------------------------------------------------------
def get_active_household():
    """Return the active Household object stored in the session, or None."""
    household_id = session.get("active_household_id")
    if not household_id:
        return None
    return Household.query.get(household_id)


# ---------------------------------------------------------
# Household Required Decorator
# ---------------------------------------------------------
def household_required(f):
    """Decorator to ensure the user has selected or joined a household."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        household = get_active_household()
        if household is None:
            flash("Please create or join a household first.", "warning")
            return redirect(url_for("main.join_household"))
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------
# Home page (Landing page)
# ---------------------------------------------------------
@main_bp.route("/")
def index():
    """Landing page of the application."""
    return render_template("index.html", user_name=session.get("user_name"))


# ---------------------------------------------------------
# Chores (db-test) — household-scoped with due-date logic
# ---------------------------------------------------------
@main_bp.route("/db-test")
@login_required
@household_required
def db_test_list():
    """Main chores page.

    - Fetches all chores for the active household
    - Splits them into overdue, upcoming, no-date and completed
    - Renders them in the db_test.html template
    """
    household = get_active_household()
    today = date.today()

    # Base query for chores in this household
    base_query = Chore.query.filter_by(household_id=household.id)

    # Active + overdue: due_date is set and is before today
    overdue_chores = (
        base_query
        .filter(
            Chore.completed == False,  # noqa: E712 (SQLAlchemy boolean pattern)
            Chore.due_date != None,
            Chore.due_date < today,
        )
        .order_by(Chore.due_date.asc())
        .all()
    )

    # Active + upcoming: due_date today or in the future
    upcoming_chores = (
        base_query
        .filter(
            Chore.completed == False,
            Chore.due_date != None,
            Chore.due_date >= today,
        )
        .order_by(Chore.due_date.asc())
        .all()
    )

    # Active + no due date set
    no_date_chores = (
        base_query
        .filter(
            Chore.completed == False,
            Chore.due_date == None,
        )
        .order_by(Chore.created_at.desc())
        .all()
    )

    # Completed chores, regardless of date
    completed_chores = (
        base_query
        .filter(Chore.completed == True)  # noqa: E712
        .order_by(Chore.created_at.desc())
        .all()
    )

    # Render all four lists into the template
    return render_template(
        "db_test.html",
        household=household,
        overdue_chores=overdue_chores,
        upcoming_chores=upcoming_chores,
        no_date_chores=no_date_chores,
        completed_chores=completed_chores,
    )


@main_bp.route("/db-test/add", methods=["POST"])
@login_required
@household_required
def db_test_add():
    """Handle adding a new chore from the db_test form."""
    household = get_active_household()

    # Read and clean form values
    title = (request.form.get("title") or "").strip()
    due_str = (request.form.get("due_date") or "").strip()

    if not title:
        flash("Please enter a chore name.", "warning")
        return redirect(url_for("main.db_test_list"))

    # Convert date string from HTML input (YYYY-MM-DD) to Python date
    due_date = None
    if due_str:
        try:
            due_date = datetime.strptime(due_str, "%Y-%m-%d").date()
        except ValueError:
            # If parsing fails, skip setting a due date
            pass

    # Create a new Chore record linked to this household
    c = Chore(
        title=title,
        household_id=household.id,
        due_date=due_date,
    )
    db.session.add(c)
    db.session.commit()

    flash("Chore added.", "success")
    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/<int:chore_id>/toggle", methods=["POST"])
@login_required
@household_required
def db_test_toggle(chore_id: int):
    """Toggle a chore between completed and not completed."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    # Security check: only allow toggling chores in the active household
    if chore.household_id != household.id:
        abort(404)

    chore.completed = not chore.completed
    db.session.commit()

    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/<int:chore_id>/delete", methods=["POST"])
@login_required
@household_required
def db_test_delete(chore_id: int):
    """Delete an existing chore."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    # Only delete if chore belongs to this household
    if chore.household_id != household.id:
        abort(404)

    db.session.delete(chore)
    db.session.commit()

    flash("Chore deleted.", "info")
    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/<int:chore_id>/edit", methods=["GET", "POST"])
@login_required
@household_required
def db_test_edit(chore_id: int):
    """Edit a chore's title and/or due date."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    # Prevent editing chores from another household
    if chore.household_id != household.id:
        abort(404)

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        due_str = (request.form.get("due_date") or "").strip()

        # Only update title if non-empty
        if title:
            chore.title = title

        # Update due date (or clear it if nothing given)
        if due_str:
            try:
                chore.due_date = datetime.strptime(due_str, "%Y-%m-%d").date()
            except ValueError:
                # Invalid date entered, ignore change
                pass
        else:
            chore.due_date = None

        db.session.commit()
        flash("Chore updated.", "success")
        return redirect(url_for("main.db_test_list"))

    # GET request: show edit form
    return render_template("edit_chore.html", chore=chore, household=household)


# ---------------------------------------------------------
# Chore assignment (assign to specific users)
# ---------------------------------------------------------
@main_bp.route("/db-test/<int:chore_id>/assign", methods=["POST"])
@login_required
@household_required
def db_test_assign(chore_id: int):
    """Assign a chore to the currently logged-in user."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    if chore.household_id != household.id:
        abort(404)

    # Link the chore to the current user's ID
    chore.assigned_to_user_id = session["user_id"]
    db.session.commit()

    flash("Chore assigned to you.", "success")
    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/<int:chore_id>/unassign", methods=["POST"])
@login_required
@household_required
def db_test_unassign(chore_id: int):
    """Remove any user assignment from a chore."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    if chore.household_id != household.id:
        abort(404)

    chore.assigned_to_user_id = None
    db.session.commit()

    flash("Chore assignment cleared.", "info")
    return redirect(url_for("main.db_test_list"))


# ---------------------------------------------------------
# Household Creation & Joining
# ---------------------------------------------------------
@main_bp.route("/create_household", methods=["GET", "POST"])
@login_required
def create_household():
    """Create a new household and generate an invite code."""
    if request.method == "POST":
        name = request.form.get("name")
        address = request.form.get("address")

        if not name:
            flash("Please enter a household name.", "warning")
            return redirect(url_for("main.create_household"))

        # Generate a random 6-character invite code
        invite_code = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )

        # Create the Household record
        new_house = Household(
            name=name,
            address=address,
            invite_code=invite_code,
        )
        db.session.add(new_house)
        db.session.commit()

        # Set this as the active household in the session
        session["active_household_id"] = new_house.id

        return render_template("household_created.html", household=new_house)

    # GET request: show the create household form
    return render_template("create_household.html")


@main_bp.route("/join_household", methods=["GET", "POST"])
@login_required
def join_household():
    """Allow a user to join an existing household by invite code."""
    joined_household = None

    if request.method == "POST":
        code = request.form.get("invite_code")
        household = Household.query.filter_by(invite_code=code).first()

        if household:
            # Store the joined household in the session
            joined_household = household
            session["active_household_id"] = household.id
            flash(f"Successfully joined household: {household.name}", "success")
        else:
            flash("Invalid invite code. Please try again.", "danger")

    return render_template("join_household.html", household=joined_household)


# ---------------------------------------------------------
# Manage Household page (Edit / Leave)
# ---------------------------------------------------------
@main_bp.route("/household/manage")
@login_required
def manage_household():
    """Display the manage-household page for the active household."""
    household = get_active_household()
    if household is None:
        flash(
            "No active household selected. Please create or join a household first.",
            "warning",
        )
        return redirect(url_for("main.index"))

    return render_template("manage_household.html", household=household)


@main_bp.route("/household/update", methods=["POST"])
@login_required
def update_household():
    """Update the name and/or address of the active household."""
    household = get_active_household()
    if household is None:
        flash("No active household to update.", "warning")
        return redirect(url_for("main.index"))

    new_name = request.form.get("name", "").strip()
    new_address = request.form.get("address", "").strip()

    if not new_name:
        flash("Household name cannot be empty.", "danger")
        return redirect(url_for("main.manage_household"))

    household.name = new_name
    household.address = new_address or None
    db.session.commit()

    flash("Household details updated successfully.", "success")
    return redirect(url_for("main.manage_household"))


@main_bp.route("/household/leave", methods=["POST"])
@login_required
def leave_household():
    """Remove the active household from the session (user leaves)."""
    household = get_active_household()
    if household is None:
        flash("You are not currently in a household.", "warning")
        return redirect(url_for("main.index"))

    # Clear household from session
    session.pop("active_household_id", None)

    flash(
        "You have left the household. You can create or join another one anytime.",
        "info",
    )
    return redirect(url_for("main.index"))


# ---------------------------------------------------------
# Registration / Login / Logout
# ---------------------------------------------------------
@main_bp.route("/register", methods=["GET", "POST"])
def register():
    """Handle new user registration."""
    # If already logged in, no need to register again
    if session.get("user_id"):
        flash("You’re already logged in.", "info")
        return redirect(url_for("main.index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        # Basic validation checks
        if not name or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("main.register"))

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("main.register"))

        # Check if email is already in use
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash("An account with that email already exists.", "warning")
            return redirect(url_for("main.register"))

        # Create new user with hashed password
        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Account created successfully. You can now log in.", "success")
        return redirect(url_for("main.login"))

    # GET request: show registration form
    return render_template("register.html")


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    """Handle user login and set session variables."""
    if session.get("user_id"):
        flash("You are already logged in.", "info")
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        # Check both existence and password validity
        if user and user.check_password(password):
            # Store basic user info in the session
            session["user_id"] = user.id
            session["user_name"] = user.name
            flash(f"Welcome back, {user.name}!", "success")
            return redirect(url_for("main.db_test_list"))
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("main.login"))

    # GET request: show login form
    return render_template("login.html")


@main_bp.route("/logout")
def logout():
    """Log the user out by clearing session values."""
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("active_household_id", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))
