"""
Main application routes and business logic.

Contains:
- Authentication (register, login, logout)
- Household creation, joining, and management
- Chore CRUD operations (db-test routes)
- Expense tracking (equal split + custom split + summary)
"""
# ChatGPT was used to assist in generating the logic for the chore auto-assignment feature based on a least-loaded fairness strategy
# ChatGPT was used to assist in generating the expense-splitting logic, including even and custom splits with currency-safe handling
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
from .models import (
    Chore,
    Household,
    User,
    Expense,
    ExpenseShare,
)
from . import db
import random
import string
from functools import wraps
from datetime import date, datetime


# ---------------------------------------------------------
# Blueprint setup
# ---------------------------------------------------------
# All routes in this file live under the "main" blueprint.
# Keeping features in a blueprint makes the app easier to grow and test.
main_bp = Blueprint("main", __name__)


# ---------------------------------------------------------
# Auth + session helpers
# ---------------------------------------------------------
# Helper functions to keep route code clean:
# - login_required(): blocks access unless a user is logged in
# - get_active_household(): returns the currently selected household
# - household_required(): blocks access unless a household is selected
# - get_household_members(): returns users who belong to the active household
def login_required(f):
    """Protect routes so only logged-in users can access them."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("main.login"))
        return f(*args, **kwargs)
    return wrapper


# Note:
# The active household is stored in the session for fast access.
# To persist this across logout/login, the last-used household id is stored on the User model
# (see User.active_household_id in models.py) and restored during login.
def get_active_household():
    """Return the active Household object stored in session, or None."""
    household_id = session.get("active_household_id")
    if not household_id:
        return None
    return Household.query.get(household_id)


def household_required(f):
    """Ensure user has selected/joined a household."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not get_active_household():
            flash("Please create or join a household first.", "warning")
            return redirect(url_for("main.join_household"))
        return f(*args, **kwargs)
    return wrapper


# Household membership helper:
# Users are members of exactly one household in this iteration (User.household_id).
# This function ensures chores/expenses only show people from the current household,
# instead of all users in the database.
def get_household_members(household_id: int):
    """Return a list of users who belong to a given household."""
    return User.query.filter_by(household_id=household_id).order_by(User.name.asc()).all()


# Session recovery:
# If a user logs in with a saved active_household_id, it is copied into the session
# so navigation (chores/expenses) works immediately without re-joining.
def ensure_household_selected_for_session(user: User) -> None:
    """Restore active household selection into session if user has one saved."""
    if user and getattr(user, "active_household_id", None):
        session["active_household_id"] = user.active_household_id


# ---------------------------------------------------------
# Home
# ---------------------------------------------------------
# Home routes: landing page that does not require login.
@main_bp.route("/")
def index():
    """Landing page."""
    return render_template("index.html", user_name=session.get("user_name"))


# ---------------------------------------------------------
# Household
# ---------------------------------------------------------
# Household routes: create/join/manage/leave household, and persist the user's selection.
@main_bp.route("/create_household", methods=["GET", "POST"])
@login_required
def create_household():
    """
    Create a new household and set it as:
    - the user's membership (user.household_id)
    - the user's active selection (user.active_household_id + session)
    """
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()

        if not name:
            flash("Household name is required.", "danger")
            return redirect(url_for("main.create_household"))

        # Create a short join code (invite_code must be unique).
        invite_code = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )

        household = Household(
            name=name,
            address=address or None,
            invite_code=invite_code,
        )
        db.session.add(household)
        db.session.commit()

        # Save selection in the browser session so the user immediately "is in" that household.
        session["active_household_id"] = household.id

        # Also store membership and last-used household on the user record (persists across logins).
        user = User.query.get(session.get("user_id"))
        if user:
            user.household_id = household.id
            user.active_household_id = household.id
            db.session.commit()

        flash("Household created successfully.", "success")
        return redirect(url_for("main.expenses"))

    return render_template("create_household.html")


@main_bp.route("/join_household", methods=["GET", "POST"])
@login_required
def join_household():
    """
    Join an existing household using invite code.
    Actions performed:
    - Look up household by invite_code
    - Set session active household
    - Set the user's membership and last-used household
    """
    if request.method == "POST":
        code = request.form.get("invite_code", "").strip()
        household = Household.query.filter_by(invite_code=code).first()

        if household:
            session["active_household_id"] = household.id

            user = User.query.get(session.get("user_id"))
            if user:
                user.household_id = household.id
                user.active_household_id = household.id
                db.session.commit()

            flash(f"Joined household: {household.name}", "success")
            return redirect(url_for("main.expenses"))

        flash("Invalid invite code.", "danger")

    return render_template("join_household.html")


@main_bp.route("/household/manage")
@login_required
def manage_household():
    """Manage the active household."""
    household = get_active_household()
    if not household:
        flash("No active household selected.", "warning")
        return redirect(url_for("main.join_household"))

    return render_template("manage_household.html", household=household)


@main_bp.route("/household/update", methods=["POST"])
@login_required
def update_household():
    """Update the active household details (name/address)."""
    household = get_active_household()
    if not household:
        flash("No active household selected.", "warning")
        return redirect(url_for("main.join_household"))

    name = (request.form.get("name") or "").strip()
    address = (request.form.get("address") or "").strip()

    if not name:
        flash("Household name is required.", "danger")
        return redirect(url_for("main.manage_household"))

    household.name = name
    household.address = address or None
    db.session.commit()

    flash("Household updated.", "success")
    return redirect(url_for("main.manage_household"))


@main_bp.route("/household/leave", methods=["POST"])
@login_required
def leave_household():
    """
    Leave the household:
    - remove active household from session
    - remove membership + active household from the user record
    """
    session.pop("active_household_id", None)

    user = User.query.get(session.get("user_id"))
    if user:
        user.household_id = None
        user.active_household_id = None
        db.session.commit()

    flash("You have left the household.", "info")
    return redirect(url_for("main.index"))


# ---------------------------------------------------------
# Chores (db-test) — RESTORED so templates keep working
# ---------------------------------------------------------
# Chores routes: CRUD + assignment + fairness + auto-assign, all scoped to the active household.
@main_bp.route("/db-test")
@login_required
@household_required
def db_test_list():
    """
    Chores dashboard:
    - Only shows chores from the active household
    - Separates chores into: overdue, upcoming, no-date, completed
    - Computes a "distribution" view so workload balance per member can be displayed
    """
    household = get_active_household()
    today = date.today()

    base_query = Chore.query.filter_by(household_id=household.id)

    overdue_chores = (
        base_query
        .filter(
            Chore.completed == False,  # noqa: E712
            Chore.due_date != None,    # noqa: E711
            Chore.due_date < today,
        )
        .order_by(Chore.due_date.asc())
        .all()
    )

    upcoming_chores = (
        base_query
        .filter(
            Chore.completed == False,  # noqa: E712
            Chore.due_date != None,    # noqa: E711
            Chore.due_date >= today,
        )
        .order_by(Chore.due_date.asc())
        .all()
    )

    no_date_chores = (
        base_query
        .filter(
            Chore.completed == False,  # noqa: E712
            Chore.due_date == None,    # noqa: E711
        )
        .order_by(Chore.created_at.desc())
        .all()
    )

    completed_chores = (
        base_query
        .filter(Chore.completed == True)  # noqa: E712
        .order_by(Chore.created_at.desc())
        .all()
    )

    # --- Fairness distribution (active chores per user + unassigned) ---
    active_chores = overdue_chores + upcoming_chores + no_date_chores

    # Household members only (prevents all users appearing in every household)
    users = get_household_members(household.id)
    users_by_id = {u.id: u for u in users}

    active_by_user = {u.id: 0 for u in users}
    unassigned_count = 0

    # Count active chores per assignee and count unassigned chores
    for c in active_chores:
        if c.assigned_to_user_id:
            if c.assigned_to_user_id in active_by_user:
                active_by_user[c.assigned_to_user_id] += 1
        else:
            unassigned_count += 1

    # Build a list structure that is easy for the template to render
    distribution = []
    for u in users:
        distribution.append({
            "name": u.name,
            "count": active_by_user.get(u.id, 0),
            "is_me": (u.id == session.get("user_id")),
        })

    # Highest count used to scale the progress bars in the UI
    max_count = max([d["count"] for d in distribution], default=0)

    return render_template(
        "db_test.html",
        household=household,
        overdue_chores=overdue_chores,
        upcoming_chores=upcoming_chores,
        no_date_chores=no_date_chores,
        completed_chores=completed_chores,

        # fairness
        distribution=distribution,
        unassigned_count=unassigned_count,
        max_count=max_count,

        # for showing owner names in the chore cards
        users_by_id=users_by_id,
    )


@main_bp.route("/db-test/add", methods=["POST"])
@login_required
@household_required
def db_test_add():
    """Add a new chore (in the active household only)."""
    household = get_active_household()
    title = (request.form.get("title") or "").strip()
    due_str = (request.form.get("due_date") or "").strip()

    if not title:
        flash("Please enter a chore name.", "warning")
        return redirect(url_for("main.db_test_list"))

    # Parse optional due date from the HTML date input
    due_date = None
    if due_str:
        try:
            due_date = datetime.strptime(due_str, "%Y-%m-%d").date()
        except ValueError:
            due_date = None

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
    """Toggle a chore completed/uncompleted (household-scoped security check included)."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    # Prevent cross-household access by ensuring ids match the active household
    if chore.household_id != household.id:
        abort(404)

    chore.completed = not chore.completed
    db.session.commit()

    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/<int:chore_id>/delete", methods=["POST"])
@login_required
@household_required
def db_test_delete(chore_id: int):
    """Delete a chore (only if it belongs to the active household)."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    # Prevent cross-household deletion
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
    """Edit a chore (title + due date), household-scoped."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    # Prevent editing chores outside the active household
    if chore.household_id != household.id:
        abort(404)

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        due_str = (request.form.get("due_date") or "").strip()

        # Update title if provided
        if title:
            chore.title = title

        # Update due date if provided, otherwise clear it
        if due_str:
            try:
                chore.due_date = datetime.strptime(due_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        else:
            chore.due_date = None

        db.session.commit()
        flash("Chore updated.", "success")
        return redirect(url_for("main.db_test_list"))

    return render_template("edit_chore.html", chore=chore, household=household)


@main_bp.route("/db-test/<int:chore_id>/assign", methods=["POST"])
@login_required
@household_required
def db_test_assign(chore_id: int):
    """Assign a chore to the current logged-in user."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    # Prevent assignment outside the active household
    if chore.household_id != household.id:
        abort(404)

    chore.assigned_to_user_id = session["user_id"]
    db.session.commit()

    flash("Chore assigned to you.", "success")
    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/<int:chore_id>/unassign", methods=["POST"])
@login_required
@household_required
def db_test_unassign(chore_id: int):
    """Clear chore assignment (set assignee to None)."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    # Prevent unassignment outside the active household
    if chore.household_id != household.id:
        abort(404)

    chore.assigned_to_user_id = None
    db.session.commit()

    flash("Chore assignment cleared.", "info")
    return redirect(url_for("main.db_test_list"))


# Auto-assign algorithm (least-loaded):
# 1) Load all active (not completed) chores for the household.
# 2) Count how many active chores each user currently has (the "load" dict).
# 3) For each unassigned chore, pick the user with the smallest load and assign it.
# This greedy strategy produces a fair distribution for typical small households.
# ChatGPT was used to assist in generating the logic for the chore auto-assignment feature based on a least-loaded fairness strategy
@main_bp.route("/db-test/auto-assign", methods=["POST"])
@login_required
@household_required
def db_test_auto_assign():
    """Auto-assign unassigned active chores fairly (least loaded)."""
    household = get_active_household()

    active_chores = (
        Chore.query
        .filter_by(household_id=household.id)
        .filter(Chore.completed == False)  # noqa: E712
        .all()
    )

    # Only users in this household can receive chores
    users = get_household_members(household.id)
    if not users:
        flash("No users available to assign chores.", "danger")
        return redirect(url_for("main.db_test_list"))

    # Build load dictionary: active chores per user
    load = {u.id: 0 for u in users}
    for c in active_chores:
        if c.assigned_to_user_id in load:
            load[c.assigned_to_user_id] += 1

    # Filter to only unassigned chores
    unassigned = [c for c in active_chores if not c.assigned_to_user_id]
    if not unassigned:
        flash("No unassigned chores to auto-assign.", "info")
        return redirect(url_for("main.db_test_list"))

    # Greedy least-loaded assignment
    assigned_count = 0
    for chore in unassigned:
        chosen_user_id = min(load, key=lambda uid: (load[uid], uid))
        chore.assigned_to_user_id = chosen_user_id
        load[chosen_user_id] += 1
        assigned_count += 1

    db.session.commit()
    flash(f"Auto-assigned {assigned_count} chore(s) fairly.", "success")
    return redirect(url_for("main.db_test_list"))


# ---------------------------------------------------------
# Expenses (Equal Split + Custom Split + Summary)
# ---------------------------------------------------------
# Expenses routes: add expenses, split (even/custom), and calculate per-user summaries.
# Expenses summary logic:
# Three values are computed for the logged-in user:
# - my_total_owed: total the user owes other payers
# - my_total_owed_to_me: total other users owe the logged-in user (if they paid)
# - my_net: owed_to_me - owed
# Breakdown lists are also built for "What I owe" and "Who owes me" so the UI can explain totals.
# ChatGPT was used to assist in generating the expense-splitting logic, including even and custom splits with currency-safe handling
@main_bp.route("/expenses")
@login_required
@household_required
def expenses():
    """Expense list page + per-user summary for the active household."""
    household = get_active_household()
    current_user_id = session.get("user_id")

    expenses_list = (
        Expense.query
        .filter_by(household_id=household.id)
        .order_by(Expense.created_at.desc())
        .all()
    )

    # Only members of this household show up in splits/summaries
    household_members = get_household_members(household.id)

    my_total_owed = 0.0
    my_total_owed_to_me = 0.0

    my_owed_lines = []
    owed_by_person = {}
    owed_to_me_by_person = {}

    # Walk every expense and its shares, and build totals/breakdowns for the logged-in user.
    for exp in expenses_list:
        payer = exp.payer

        for share in exp.shares:
            if share.user_id == current_user_id:
                if payer and payer.id != current_user_id:
                    amt = float(share.amount_owed)
                    if amt > 0:
                        my_total_owed += amt
                        my_owed_lines.append({
                            "to_name": payer.name,
                            "expense_title": exp.title,
                            "amount": amt,
                        })
                        owed_by_person[payer.name] = owed_by_person.get(payer.name, 0.0) + amt

        if payer and payer.id == current_user_id:
            for share in exp.shares:
                if share.user_id != current_user_id:
                    amt = float(share.amount_owed)
                    if amt > 0:
                        my_total_owed_to_me += amt
                        debtor = next((u for u in household_members if u.id == share.user_id), None)
                        debtor_name = debtor.name if debtor else f"User {share.user_id}"
                        owed_to_me_by_person[debtor_name] = owed_to_me_by_person.get(debtor_name, 0.0) + amt

    my_net = my_total_owed_to_me - my_total_owed

    # Format totals into lists for template rendering
    my_owed_by_person = [{"name": k, "total": v} for k, v in owed_by_person.items()]
    my_owed_by_person.sort(key=lambda x: x["total"], reverse=True)

    owed_to_me_by_person_list = [{"name": k, "total": v} for k, v in owed_to_me_by_person.items()]
    owed_to_me_by_person_list.sort(key=lambda x: x["total"], reverse=True)

    my_owed_lines.sort(key=lambda x: x["amount"], reverse=True)

    return render_template(
        "expenses.html",
        household=household,
        expenses=expenses_list,
        household_members=household_members,

        my_total_owed=my_total_owed,
        my_total_owed_to_me=my_total_owed_to_me,
        my_net=my_net,
        my_owed_lines=my_owed_lines,
        my_owed_by_person=my_owed_by_person,
        owed_to_me_by_person=owed_to_me_by_person_list,
    )


# Adding an expense:
# Currency values are converted to cents (integers) to avoid floating-point rounding issues when splitting.
# - Even split: divide cents equally, distribute remainder by user id order.
# - Custom split: validate all per-user amounts add up exactly to the total.
@main_bp.route("/expenses/add", methods=["POST"])
@login_required
@household_required
def add_expense():
    """Add an expense and split it evenly or by custom amounts."""
    household = get_active_household()

    title = request.form.get("title", "").strip()
    amount_str = request.form.get("total_amount", "").strip()
    split_method = request.form.get("split_method", "even").strip().lower()

    if not title or not amount_str:
        flash("Please enter an expense name and amount.", "danger")
        return redirect(url_for("main.expenses"))

    # Validate and parse the amount input
    try:
        total_amount = float(amount_str)
        if total_amount <= 0:
            raise ValueError
    except ValueError:
        flash("Invalid amount.", "danger")
        return redirect(url_for("main.expenses"))

    # Create expense row (shares are added after)
    expense = Expense(
        title=title,
        total_amount=total_amount,
        household_id=household.id,
        paid_by_user_id=session["user_id"],
    )
    db.session.add(expense)
    db.session.flush()

    # Users list defines who participates in the split
    users = get_household_members(household.id)
    if not users:
        flash("No users found to split the expense.", "danger")
        db.session.rollback()
        return redirect(url_for("main.expenses"))

    total_cents = int(round(total_amount * 100))

    try:
        # Custom split: each user provides an amount that must sum to total
        if split_method == "custom":
            shares = []
            sum_cents = 0

            for user in users:
                key = f"custom_amount_{user.id}"
                raw = (request.form.get(key) or "").strip()
                if raw == "":
                    cents = 0
                else:
                    try:
                        val = float(raw)
                        if val < 0:
                            raise ValueError
                        cents = int(round(val * 100))
                    except ValueError:
                        raise ValueError("Custom split contains an invalid amount.")

                sum_cents += cents
                shares.append((user.id, cents))

            if sum_cents != total_cents:
                raise ValueError("Custom amounts must add up exactly to the total expense.")

            for user_id, cents in shares:
                db.session.add(
                    ExpenseShare(
                        expense_id=expense.id,
                        user_id=user_id,
                        amount_owed=cents / 100.0,
                    )
                )

            db.session.commit()
            flash("Expense added with custom split.", "success")
            return redirect(url_for("main.expenses"))

        # Even split: distribute remainder fairly by sorted user id order
        split_cents = total_cents // len(users)
        remainder = total_cents % len(users)
        users_sorted = sorted(users, key=lambda u: u.id)

        for idx, user in enumerate(users_sorted):
            cents = split_cents + (1 if idx < remainder else 0)
            db.session.add(
                ExpenseShare(
                    expense_id=expense.id,
                    user_id=user.id,
                    amount_owed=cents / 100.0,
                )
            )

        db.session.commit()
        flash("Expense added and split equally.", "success")
        return redirect(url_for("main.expenses"))

    # Validation failures rollback the transaction and show an error message
    except ValueError as e:
        db.session.rollback()
        flash(str(e), "danger")
        return redirect(url_for("main.expenses"))


# ---------------------------------------------------------
# Auth
# ---------------------------------------------------------
# Auth routes: register/login/logout. Session is cleared on register/login to avoid cross-user leakage.
@main_bp.route("/register", methods=["GET", "POST"])
def register():
    """User registration."""
    if request.method == "POST":
        # Clear any previous user's session data (prevents browser session mixing accounts)
        session.clear()

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("main.register"))

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("main.register"))

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "warning")
            return redirect(url_for("main.register"))

        user = User(name=name, email=email)
        user.set_password(password)

        # household_id and active_household_id remain None until the user creates/joins a household.
        db.session.add(user)
        db.session.commit()

        flash("Account created. Please log in.", "success")
        return redirect(url_for("main.login"))

    return render_template("register.html")


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    """User login."""
    if request.method == "POST":
        # Clear session so another user's active household is not leaked into this login.
        session.clear()

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            session["user_id"] = user.id
            session["user_name"] = user.name

            # Restore user's last selected household so navigation works immediately after login.
            ensure_household_selected_for_session(user)

            flash("Logged in successfully.", "success")
            return redirect(url_for("main.expenses"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@main_bp.route("/logout")
def logout():
    """
    Log out:
    - clear session (removes user_id + active_household_id from browser)
    - keep user.active_household_id in the database so it restores on next login
    """
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("main.index"))
