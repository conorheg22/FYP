"""
Main application routes and business logic.

Contains:
- Authentication (register, login, logout)
- Household creation, joining, and management
- Chore CRUD operations (db-test routes)
- Expense tracking (equal split + custom split + summary)
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
from .models import (
    Chore,
    Household,
    User,
    Expense,
    ExpenseShare,
    ChoreSwapRequest,
)
from . import db
import random
import string
from functools import wraps
from datetime import date, datetime

main_bp = Blueprint("main", __name__)


# ---------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------
def login_required(f):
    """Protect routes so only logged-in users can access them."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("main.login"))
        return f(*args, **kwargs)
    return wrapper


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


def get_household_members(household_id: int):
    """Return users who belong to this household."""
    return (
        User.query
        .filter_by(household_id=household_id)
        .order_by(User.name.asc())
        .all()
    )


# ---------------------------------------------------------
# Home
# ---------------------------------------------------------
@main_bp.route("/")
def index():
    """Landing page."""
    return render_template("index.html", user_name=session.get("user_name"))


# ---------------------------------------------------------
# Household
# ---------------------------------------------------------
@main_bp.route("/create_household", methods=["GET", "POST"])
@login_required
def create_household():
    """Create a new household and set it active."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()

        if not name:
            flash("Household name is required.", "danger")
            return redirect(url_for("main.create_household"))

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

        # Session + DB persistence for this user's active household
        session["active_household_id"] = household.id

        user = User.query.get(session.get("user_id"))
        if user:
            # Membership + restore-on-login
            user.household_id = household.id
            user.active_household_id = household.id
            db.session.commit()

        flash("Household created successfully.", "success")
        return redirect(url_for("main.expenses"))

    return render_template("create_household.html")


@main_bp.route("/join_household", methods=["GET", "POST"])
@login_required
def join_household():
    """Join an existing household using invite code."""
    if request.method == "POST":
        code = request.form.get("invite_code", "").strip()
        household = Household.query.filter_by(invite_code=code).first()

        if household:
            # Session + DB persistence for this user's active household
            session["active_household_id"] = household.id
            user = User.query.get(session.get("user_id"))
            if user:
                # Membership + restore-on-login
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
    """Leave the currently active household."""
    # Clear session selection
    session.pop("active_household_id", None)

    # Clear membership + persisted selection so it doesn't restore on next login
    user = User.query.get(session.get("user_id"))
    if user:
        user.active_household_id = None
        user.household_id = None
        db.session.commit()

    flash("You have left the household.", "info")
    return redirect(url_for("main.index"))


# ---------------------------------------------------------
# Chores (db-test)
# ---------------------------------------------------------
@main_bp.route("/db-test")
@login_required
@household_required
def db_test_list():
    """Chores page (existing Iteration 2 feature)."""
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

    # FIX: members are ONLY users in this household
    users = get_household_members(household.id)
    users_by_id = {u.id: u for u in users}

    # --- Swap request data (for "trade chores" feature) ---
    # Only show active (not completed) chores that are currently assigned to each user.
    chores_by_user = {u.id: [] for u in users}
    for c in active_chores:
        if c.assigned_to_user_id in chores_by_user:
            chores_by_user[c.assigned_to_user_id].append(c)

    # Incoming swap requests where *I* need to accept/decline
    incoming_swaps = (
        ChoreSwapRequest.query
        .filter_by(household_id=household.id, to_user_id=session.get("user_id"), status="pending")
        .order_by(ChoreSwapRequest.created_at.desc())
        .all()
    )

    # Outgoing swap requests that I have sent (still pending)
    outgoing_swaps = (
        ChoreSwapRequest.query
        .filter_by(household_id=household.id, from_user_id=session.get("user_id"), status="pending")
        .order_by(ChoreSwapRequest.created_at.desc())
        .all()
    )

    active_by_user = {u.id: 0 for u in users}
    unassigned_count = 0

    for c in active_chores:
        if c.assigned_to_user_id:
            if c.assigned_to_user_id in active_by_user:
                active_by_user[c.assigned_to_user_id] += 1
        else:
            unassigned_count += 1

    distribution = []
    for u in users:
        distribution.append({
            "name": u.name,
            "count": active_by_user.get(u.id, 0),
            "is_me": (u.id == session.get("user_id")),
        })

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

        # household members (used for chore swap UI)
        household_members=users,

        # swap requests
        chores_by_user=chores_by_user,
        incoming_swaps=incoming_swaps,
        outgoing_swaps=outgoing_swaps,
    )


@main_bp.route("/db-test/add", methods=["POST"])
@login_required
@household_required
def db_test_add():
    """Add a new chore."""
    household = get_active_household()
    title = (request.form.get("title") or "").strip()
    due_str = (request.form.get("due_date") or "").strip()

    if not title:
        flash("Please enter a chore name.", "warning")
        return redirect(url_for("main.db_test_list"))

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
    """Toggle a chore completed/uncompleted."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    if chore.household_id != household.id:
        abort(404)

    chore.completed = not chore.completed
    db.session.commit()

    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/<int:chore_id>/delete", methods=["POST"])
@login_required
@household_required
def db_test_delete(chore_id: int):
    """Delete a chore."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

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
    """Edit a chore (title + due date)."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    if chore.household_id != household.id:
        abort(404)

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        due_str = (request.form.get("due_date") or "").strip()

        if title:
            chore.title = title

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
    """Assign a chore to the current user."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

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
    """Clear chore assignment."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    if chore.household_id != household.id:
        abort(404)

    chore.assigned_to_user_id = None
    db.session.commit()

    flash("Chore assignment cleared.", "info")
    return redirect(url_for("main.db_test_list"))


# ---------------------------------------------------------
# Chore Swaps
# ---------------------------------------------------------
@main_bp.route("/db-test/<int:chore_id>/swap/request", methods=["POST"])
@login_required
@household_required
def db_test_swap_request(chore_id: int):
    """Create a swap request for one of my chores with another user's chore."""
    household = get_active_household()
    current_user_id = session.get("user_id")

    offered_chore = Chore.query.get_or_404(chore_id)
    if offered_chore.household_id != household.id:
        abort(404)

    # Safety rule: you can only offer a chore that is currently assigned to you.
    if offered_chore.assigned_to_user_id != current_user_id:
        flash("You can only request a swap for a chore assigned to you.", "danger")
        return redirect(url_for("main.db_test_list"))

    to_user_id_raw = (request.form.get("to_user_id") or "").strip()
    requested_chore_id_raw = (request.form.get("requested_chore_id") or "").strip()

    if not to_user_id_raw or not requested_chore_id_raw:
        flash("Please choose a person and a chore to swap with.", "warning")
        return redirect(url_for("main.db_test_list"))

    try:
        to_user_id = int(to_user_id_raw)
        requested_chore_id = int(requested_chore_id_raw)
    except ValueError:
        flash("Invalid swap request.", "danger")
        return redirect(url_for("main.db_test_list"))

    if to_user_id == current_user_id:
        flash("You cannot swap with yourself.", "warning")
        return redirect(url_for("main.db_test_list"))

    to_user = User.query.get_or_404(to_user_id)

    # Must be in the same household
    if to_user.household_id != household.id:
        flash("That user is not in your household.", "danger")
        return redirect(url_for("main.db_test_list"))

    requested_chore = Chore.query.get_or_404(requested_chore_id)

    # Requested chore must belong to same household, be active, and be assigned to the target user.
    if requested_chore.household_id != household.id:
        flash("That chore is not in your household.", "danger")
        return redirect(url_for("main.db_test_list"))

    if requested_chore.completed:
        flash("You cannot swap for a completed chore.", "warning")
        return redirect(url_for("main.db_test_list"))

    if requested_chore.assigned_to_user_id != to_user_id:
        flash("That chore is not assigned to the selected user.", "warning")
        return redirect(url_for("main.db_test_list"))

    # Prevent duplicate pending requests for the same pair (keeps UI cleaner)
    existing = (
        ChoreSwapRequest.query
        .filter_by(
            household_id=household.id,
            from_user_id=current_user_id,
            to_user_id=to_user_id,
            offered_chore_id=offered_chore.id,
            requested_chore_id=requested_chore.id,
            status="pending",
        )
        .first()
    )
    if existing:
        flash("You already have a pending swap request for those chores.", "info")
        return redirect(url_for("main.db_test_list"))

    swap = ChoreSwapRequest(
        household_id=household.id,
        from_user_id=current_user_id,
        to_user_id=to_user_id,
        offered_chore_id=offered_chore.id,
        requested_chore_id=requested_chore.id,
        status="pending",
    )
    db.session.add(swap)
    db.session.commit()

    flash("Swap request sent. The other user can accept or decline.", "success")
    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/swap/<int:swap_id>/accept", methods=["POST"])
@login_required
@household_required
def db_test_swap_accept(swap_id: int):
    """Accept a pending swap request and swap chore assignments."""
    household = get_active_household()
    current_user_id = session.get("user_id")

    swap = ChoreSwapRequest.query.get_or_404(swap_id)

    if swap.household_id != household.id:
        abort(404)

    # Only the recipient can accept
    if swap.to_user_id != current_user_id:
        flash("You are not allowed to accept this swap.", "danger")
        return redirect(url_for("main.db_test_list"))

    if swap.status != "pending":
        flash("This swap request is no longer pending.", "info")
        return redirect(url_for("main.db_test_list"))

    offered = Chore.query.get_or_404(swap.offered_chore_id)
    requested = Chore.query.get_or_404(swap.requested_chore_id)

    # Re-check ownership hasn't changed since request was created
    if offered.household_id != household.id or requested.household_id != household.id:
        flash("This swap is no longer valid.", "danger")
        return redirect(url_for("main.db_test_list"))

    if offered.completed or requested.completed:
        flash("This swap is no longer valid because a chore was completed.", "warning")
        return redirect(url_for("main.db_test_list"))

    if offered.assigned_to_user_id != swap.from_user_id:
        flash("Swap failed because the offered chore is no longer assigned to the requester.", "warning")
        return redirect(url_for("main.db_test_list"))

    if requested.assigned_to_user_id != swap.to_user_id:
        flash("Swap failed because your chore is no longer assigned to you.", "warning")
        return redirect(url_for("main.db_test_list"))

    # Swap the chore assignments
    offered.assigned_to_user_id = swap.to_user_id
    requested.assigned_to_user_id = swap.from_user_id

    swap.status = "accepted"
    swap.responded_at = datetime.utcnow()

    db.session.commit()

    flash("Swap accepted. Chores have been swapped.", "success")
    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/swap/<int:swap_id>/decline", methods=["POST"])
@login_required
@household_required
def db_test_swap_decline(swap_id: int):
    """Decline a pending swap request."""
    household = get_active_household()
    current_user_id = session.get("user_id")

    swap = ChoreSwapRequest.query.get_or_404(swap_id)

    if swap.household_id != household.id:
        abort(404)

    # Only the recipient can decline
    if swap.to_user_id != current_user_id:
        flash("You are not allowed to decline this swap.", "danger")
        return redirect(url_for("main.db_test_list"))

    if swap.status != "pending":
        flash("This swap request is no longer pending.", "info")
        return redirect(url_for("main.db_test_list"))

    swap.status = "declined"
    swap.responded_at = datetime.utcnow()
    db.session.commit()

    flash("Swap declined.", "info")
    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/auto-assign", methods=["POST"])
@login_required
@household_required
def db_test_auto_assign():
    """Auto-assign UNASSIGNED active chores fairly (least loaded)."""
    household = get_active_household()

    active_chores = (
        Chore.query
        .filter_by(household_id=household.id)
        .filter(Chore.completed == False)  # noqa: E712
        .all()
    )

    # FIX: only household members
    users = (
        User.query
        .filter_by(household_id=household.id)
        .order_by(User.id.asc())
        .all()
    )
    if not users:
        flash("No users available to assign chores.", "danger")
        return redirect(url_for("main.db_test_list"))

    load = {u.id: 0 for u in users}
    for c in active_chores:
        if c.assigned_to_user_id in load:
            load[c.assigned_to_user_id] += 1

    unassigned = [c for c in active_chores if not c.assigned_to_user_id]
    if not unassigned:
        flash("No unassigned chores to auto-assign.", "info")
        return redirect(url_for("main.db_test_list"))

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

    # FIX: only household members
    household_members = get_household_members(household.id)

    my_total_owed = 0.0
    my_total_owed_to_me = 0.0

    my_owed_lines = []
    owed_by_person = {}
    owed_to_me_by_person = {}

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

    try:
        total_amount = float(amount_str)
        if total_amount <= 0:
            raise ValueError
    except ValueError:
        flash("Invalid amount.", "danger")
        return redirect(url_for("main.expenses"))

    expense = Expense(
        title=title,
        total_amount=total_amount,
        household_id=household.id,
        paid_by_user_id=session["user_id"],
    )
    db.session.add(expense)
    db.session.flush()

    # FIX: only users in this household
    users = (
        User.query
        .filter_by(household_id=household.id)
        .order_by(User.id.asc())
        .all()
    )
    if not users:
        flash("No household members found to split the expense.", "danger")
        db.session.rollback()
        return redirect(url_for("main.expenses"))

    total_cents = int(round(total_amount * 100))

    try:
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

    except ValueError as e:
        db.session.rollback()
        flash(str(e), "danger")
        return redirect(url_for("main.expenses"))


# ---------------------------------------------------------
# Auth
# ---------------------------------------------------------
@main_bp.route("/register", methods=["GET", "POST"])
def register():
    """User registration."""
    if request.method == "POST":
        # stop session leakage between accounts in the same browser
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
        db.session.add(user)
        db.session.commit()

        flash("Account created. Please log in.", "success")
        return redirect(url_for("main.login"))

    return render_template("register.html")


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    """User login."""
    if request.method == "POST":
        # stop session leakage between accounts in the same browser
        session.clear()

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            session["user_id"] = user.id
            session["user_name"] = user.name

            # restore household for this user (survives logout/login)
            if getattr(user, "active_household_id", None):
                session["active_household_id"] = user.active_household_id

            flash("Logged in successfully.", "success")
            return redirect(url_for("main.expenses"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@main_bp.route("/logout")
def logout():
    """Log out."""
    # Keep DB value so household restores next login
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("main.index"))
