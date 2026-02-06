"""
Main application routes and business logic.

Contains:
- Authentication (register, login, logout)
- Household creation, joining, and management
- Chore CRUD operations (db-test routes)
- Expense tracking (equal split + custom split + summary)
- Inventory items (Item 12)
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
    jsonify,
)
from .models import (
    Chore,
    Household,
    User,
    Expense,
    ExpenseShare,
    ChoreSwapRequest,
    InventoryItem,
    Notification,
)

from . import db
import random
import string
from functools import wraps
from datetime import date, datetime

main_bp = Blueprint("main", __name__)

# ---------------------------------------------------------
# Inventory constants (Step 2)
# ---------------------------------------------------------
# I keep these lists here so my inventory form options stay consistent across the app.
INVENTORY_CATEGORIES = [
    "Food",
    "Household Supplies",
    "Cleaning",
    "Toiletries",
    "Laundry",
    "Pet",
    "Medicine",
    "Other",
]

INVENTORY_LOCATIONS = [
    "Fridge",
    "Freezer",
    "Pantry",
    "Bathroom",
    "Utility room",
    "Other",
]


# Reference: Flask sessions and template access
# https://flask.palletsprojects.com/en/stable/quickstart/

# ---------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------
def login_required(f):
    """I use this to protect routes so only logged-in users can access them."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        # I check session first because it’s the quickest way to see if a user is logged in.
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("main.login"))
        return f(*args, **kwargs)
    return wrapper


def get_active_household():
    """I read the active household ID from the session and load the Household from the database."""
    household_id = session.get("active_household_id")
    if not household_id:
        return None
    return Household.query.get(household_id)


def household_required(f):
    """I use this to make sure a user has an active household before they can use household features."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        # I redirect here so users don’t accidentally access pages without selecting a household.
        if not get_active_household():
            flash("Please create or join a household first.", "warning")
            return redirect(url_for("main.join_household"))
        return f(*args, **kwargs)
    return wrapper


def get_household_members(household_id: int):
    """I use this helper to get all members for a household (sorted by name for nicer UI)."""
    return (
        User.query
        .filter_by(household_id=household_id)
        .order_by(User.name.asc())
        .all()
    )


# ---------------------------------------------------------
# Notifications helpers
# ---------------------------------------------------------
# Notification helper (prevents duplicates so refresh doesn't spam).
# Approach informed by AI-assisted guidance during notifications implementation.
# Source: ChatGPT conversation – Notifications feature prompt (Feb 2026) - https://chatgpt.com/share/69865e70-4154-8007-b020-98259faaf812

def create_notification(
    *,
    household_id: int,
    user_id: int | None,
    type: str,
    title: str,
    message: str,
    link_url: str | None = None,
):
    """
    I create a notification for the household (or a specific user).
    I also prevent duplicates so refreshing a page doesn’t spam notifications.
    """
    existing = (
        Notification.query
        .filter_by(
            household_id=household_id,
            user_id=user_id,
            type=type,
            is_read=False,
        )
        .filter(Notification.message == message)
        .first()
    )

    # I skip creating it if the same unread notification already exists.
    if existing:
        return

    n = Notification(
        household_id=household_id,
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        link_url=link_url,
    )
    db.session.add(n)
    db.session.commit()


# ---------------------------------------------------------
# Home
# ---------------------------------------------------------
@main_bp.route("/")
def index():
    """I use this route to show the landing page."""
    return render_template("index.html", user_name=session.get("user_name"))


# ---------------------------------------------------------
# Household
# ---------------------------------------------------------
@main_bp.route("/create_household", methods=["GET", "POST"])
@login_required
def create_household():
    """I use this route to create a new household and set it as the active one in the session."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()

        # I validate the household name because it’s the main thing the user sees everywhere.
        if not name:
            flash("Household name is required.", "danger")
            return redirect(url_for("main.create_household"))

        # I generate a short invite code so other users can join easily.
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

        # I store the household ID in the session so it’s restored when the user moves around the app.
        session["active_household_id"] = household.id

        # I link the logged-in user to the new household in the database.
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
    """I use this route to join an existing household using an invite code."""
    if request.method == "POST":
        code = request.form.get("invite_code", "").strip()
        household = Household.query.filter_by(invite_code=code).first()

        if household:
            # I set the active household in the session so all household features use the right data.
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
    """I use this route to show the settings/details page for the active household."""
    household = get_active_household()
    if not household:
        flash("No active household selected.", "warning")
        return redirect(url_for("main.join_household"))

    return render_template("manage_household.html", household=household)


@main_bp.route("/household/update", methods=["POST"])
@login_required
def update_household():
    """I use this route to update the active household name/address from the manage page."""
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
    """I use this route to let the user leave the current household and clear it from session."""
    session.pop("active_household_id", None)

    # I also clear the household links on the user record so it doesn’t load again by accident.
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
    """I use this route to show the chores page for the active household."""
    household = get_active_household()
    today = date.today()

    base_query = Chore.query.filter_by(household_id=household.id)

    # I create notifications for chores that are due today or already overdue.
    for c in base_query.filter(Chore.completed == False).all():  # noqa: E712
        if c.due_date == today:
            create_notification(
                household_id=household.id,
                user_id=c.assigned_to_user_id,
                type="chore_due",
                title="⏰ Chore due today",
                message=f"{c.title} is due today",
                link_url=url_for("main.db_test_list"),
            )
        elif c.due_date and c.due_date < today:
            create_notification(
                household_id=household.id,
                user_id=c.assigned_to_user_id,
                type="chore_overdue",
                title="⚠️ Chore overdue",
                message=f"{c.title} is overdue",
                link_url=url_for("main.db_test_list"),
            )

    # I also send reminders shortly before a chore is due so people get a heads-up.
    REMINDER_WINDOW_DAYS = 2
    for c in base_query.filter(Chore.completed == False).all():  # noqa: E712
        if not c.due_date:
            continue

        days_left = (c.due_date - today).days
        if 1 <= days_left <= REMINDER_WINDOW_DAYS:
            create_notification(
                household_id=household.id,
                user_id=c.assigned_to_user_id,
                type="chore_reminder",
                title="🔔 Chore reminder",
                message=f"“{c.title}” is due in {days_left} day(s)",
                link_url=url_for("main.db_test_list"),
            )

    # I split chores into groups so the UI can show overdue/upcoming/no-date/completed clearly.
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

    active_chores = overdue_chores + upcoming_chores + no_date_chores
    users = get_household_members(household.id)
    users_by_id = {u.id: u for u in users}

    # I group active chores by user so I can show a simple “assigned chores” view.
    chores_by_user = {u.id: [] for u in users}
    for c in active_chores:
        if c.assigned_to_user_id in chores_by_user:
            chores_by_user[c.assigned_to_user_id].append(c)

    # I load swap requests so users can see what’s waiting for them.
    incoming_swaps = (
        ChoreSwapRequest.query
        .filter_by(household_id=household.id, to_user_id=session.get("user_id"), status="pending")
        .order_by(ChoreSwapRequest.created_at.desc())
        .all()
    )

    outgoing_swaps = (
        ChoreSwapRequest.query
        .filter_by(household_id=household.id, from_user_id=session.get("user_id"), status="pending")
        .order_by(ChoreSwapRequest.created_at.desc())
        .all()
    )

    # I calculate a quick “load” count so the UI can show how chores are distributed.
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

    # I also fetch pending swaps again here because the template expects this list.
    pending_swaps = (
        ChoreSwapRequest.query
        .filter_by(
            household_id=household.id,
            to_user_id=session.get("user_id"),
            status="pending",
        )
        .order_by(ChoreSwapRequest.created_at.desc())
        .all()
    )

    return render_template(
        "db_test.html",
        household=household,
        overdue_chores=overdue_chores,
        upcoming_chores=upcoming_chores,
        no_date_chores=no_date_chores,
        completed_chores=completed_chores,

        distribution=distribution,
        unassigned_count=unassigned_count,
        max_count=max_count,

        users_by_id=users_by_id,
        household_members=users,

        chores_by_user=chores_by_user,
        incoming_swaps=incoming_swaps,
        outgoing_swaps=outgoing_swaps,
        pending_swaps=pending_swaps,
    )


@main_bp.route("/db-test/add", methods=["POST"])
@login_required
@household_required
def db_test_add():
    """I use this route to add a new chore to the active household."""
    household = get_active_household()
    title = (request.form.get("title") or "").strip()
    due_str = (request.form.get("due_date") or "").strip()

    if not title:
        flash("Please enter a chore name.", "warning")
        return redirect(url_for("main.db_test_list"))

    # I parse the due date from the form, and fall back to None if it isn’t valid.
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

    # I notify other housemates so they see the new chore without needing to check manually.
    creator_id = session.get("user_id")
    members = get_household_members(household.id)
    for u in members:
        if u.id == creator_id:
            continue
        create_notification(
            household_id=household.id,
            user_id=u.id,
            type="chore_new",
            title="🧹 New chore added",
            message=f"“{c.title}” was added to chores",
            link_url=url_for("main.db_test_list"),
        )

    flash("Chore added.", "success")
    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/<int:chore_id>/toggle", methods=["POST"])
@login_required
@household_required
def db_test_toggle(chore_id: int):
    """I use this route to mark a chore as done/undone."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    # I check household IDs here to make sure users can’t access chores from other households.
    if chore.household_id != household.id:
        abort(404)

    chore.completed = not chore.completed
    db.session.commit()

    # I only send the “nice work” notification when a chore is completed.
    if chore.completed:
        create_notification(
            household_id=household.id,
            user_id=session.get("user_id"),
            type="chore_complete",
            title="🎉 Nice work!",
            message=f"You completed the chore: {chore.title}",
            link_url=url_for("main.db_test_list"),
        )

    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/<int:chore_id>/delete", methods=["POST"])
@login_required
@household_required
def db_test_delete(chore_id: int):
    """I use this route to delete a chore, but only if it belongs to me."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    if chore.household_id != household.id:
        abort(404)

    # I limit deletes to the assigned user so chores can’t be removed by random housemates.
    if chore.assigned_to_user_id != session.get("user_id"):
        flash("You can only delete chores assigned to you.", "danger")
        return redirect(url_for("main.db_test_list"))

    db.session.delete(chore)
    db.session.commit()

    flash("Chore deleted.", "info")
    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/<int:chore_id>/edit", methods=["GET", "POST"])
@login_required
@household_required
def db_test_edit(chore_id: int):
    """I use this route to edit a chore (title + due date) when the chore is assigned to me."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    if chore.household_id != household.id:
        abort(404)

    # I keep edits restricted to the assigned user to avoid people changing each other’s chores.
    if chore.assigned_to_user_id != session.get("user_id"):
        flash("You can only edit chores assigned to you.", "danger")
        return redirect(url_for("main.db_test_list"))

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        due_str = (request.form.get("due_date") or "").strip()

        if title:
            chore.title = title

        # I update the due date only if the input parses correctly.
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
    """I use this route to assign a chore to myself (and send a confirmation email if possible)."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    if chore.household_id != household.id:
        abort(404)

    chore.assigned_to_user_id = session["user_id"]
    db.session.commit()

    # I wrap email sending in a try/except so the app still works even if email fails.
    try:
        from .email_service import send_email

        user = User.query.get(session["user_id"])
        if user and user.email:
            send_email(
                to_email=user.email,
                to_name=user.name,
                subject="You’ve been assigned a chore 🧹",
                html=f"""
                    <p>Hi {user.name},</p>
                    <p>You’ve just been assigned a new chore:</p>
                    <p><strong>{chore.title}</strong></p>
                    <p>— HOMI</p>
                """,
                text=f"Hi {user.name}, you’ve been assigned the chore: {chore.title}"
            )
    except Exception:
        pass

    flash("Chore assigned to you.", "success")
    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/<int:chore_id>/unassign", methods=["POST"])
@login_required
@household_required
def db_test_unassign(chore_id: int):
    """I use this route to clear the chore assignment and make it available again."""
    household = get_active_household()
    chore = Chore.query.get_or_404(chore_id)

    if chore.household_id != household.id:
        abort(404)

    chore.assigned_to_user_id = None
    db.session.commit()

    flash("Chore assignment cleared.", "info")
    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/auto-assign", methods=["POST"])
@login_required
@household_required
def db_test_auto_assign():
    """I use this route to auto-assign unassigned chores fairly (least chores first)."""
    household = get_active_household()

    active_chores = (
        Chore.query
        .filter_by(household_id=household.id)
        .filter(Chore.completed == False)  # noqa: E712
        .all()
    )

    users = (
        User.query
        .filter_by(household_id=household.id)
        .order_by(User.id.asc())
        .all()
    )

    if not users:
        flash("No users available to assign chores.", "danger")
        return redirect(url_for("main.db_test_list"))

    # I calculate current “load” so I can assign chores to the least-loaded user each time.
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
# Chore Swaps
# ---------------------------------------------------------
@main_bp.route("/db-test/<int:chore_id>/swap/request", methods=["POST"])
@login_required
@household_required
def request_chore_swap(chore_id: int):
    """I use this route to request that someone else takes a chore that’s currently assigned to me."""
    household = get_active_household()
    current_user_id = session.get("user_id")

    offered_chore = Chore.query.get_or_404(chore_id)
    if offered_chore.household_id != household.id:
        abort(404)

    # I only allow swap requests for chores that belong to the current user.
    if offered_chore.assigned_to_user_id != current_user_id:
        flash("You can only request a swap for a chore assigned to you.", "danger")
        return redirect(url_for("main.db_test_list"))

    to_user_id_raw = (request.form.get("to_user_id") or "").strip()
    if not to_user_id_raw:
        flash("Please choose a person to send the request to.", "warning")
        return redirect(url_for("main.db_test_list"))

    try:
        to_user_id = int(to_user_id_raw)
    except ValueError:
        flash("Invalid swap request.", "danger")
        return redirect(url_for("main.db_test_list"))

    if to_user_id == current_user_id:
        flash("You cannot request a swap with yourself.", "warning")
        return redirect(url_for("main.db_test_list"))

    to_user = User.query.get_or_404(to_user_id)

    if to_user.household_id != household.id:
        flash("That user is not in your household.", "danger")
        return redirect(url_for("main.db_test_list"))

    # I prevent duplicates so the same person doesn’t get spammed with repeated requests.
    existing = (
        ChoreSwapRequest.query
        .filter_by(
            household_id=household.id,
            from_user_id=current_user_id,
            to_user_id=to_user_id,
            offered_chore_id=offered_chore.id,
            status="pending",
        )
        .first()
    )
    if existing:
        flash("You already have a pending request for this chore.", "info")
        return redirect(url_for("main.db_test_list"))

    swap = ChoreSwapRequest(
        household_id=household.id,
        from_user_id=current_user_id,
        to_user_id=to_user_id,
        offered_chore_id=offered_chore.id,
        requested_chore_id=None,
        status="pending",
    )
    db.session.add(swap)
    db.session.commit()

    flash("Request sent. The other user can accept or decline.", "success")
    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/swap/<int:swap_id>/accept", methods=["POST"])
@login_required
@household_required
def accept_chore_swap(swap_id: int):
    """I use this route to accept a swap request and take over the offered chore."""
    household = get_active_household()
    current_user_id = session.get("user_id")

    swap = ChoreSwapRequest.query.get_or_404(swap_id)

    if swap.household_id != household.id:
        abort(404)

    # I check this so only the recipient can accept the swap.
    if swap.to_user_id != current_user_id:
        flash("You are not allowed to accept this request.", "danger")
        return redirect(url_for("main.db_test_list"))

    if swap.status != "pending":
        flash("This request is no longer pending.", "info")
        return redirect(url_for("main.db_test_list"))

    offered = Chore.query.get_or_404(swap.offered_chore_id)

    # I validate again here so the swap can’t be accepted if the chore changed since the request.
    if offered.household_id != household.id:
        flash("This request is no longer valid.", "danger")
        return redirect(url_for("main.db_test_list"))

    if offered.completed:
        flash("This request is no longer valid because the chore was completed.", "warning")
        return redirect(url_for("main.db_test_list"))

    if offered.assigned_to_user_id != swap.from_user_id:
        flash("This request is no longer valid because the chore is no longer assigned to the requester.", "warning")
        return redirect(url_for("main.db_test_list"))

    offered.assigned_to_user_id = swap.to_user_id

    swap.status = "accepted"
    swap.responded_at = datetime.utcnow()

    db.session.commit()

    flash("Accepted. The chore is now assigned to you.", "success")
    return redirect(url_for("main.db_test_list"))


@main_bp.route("/db-test/swap/<int:swap_id>/decline", methods=["POST"])
@login_required
@household_required
def decline_chore_swap(swap_id: int):
    """I use this route to decline a swap request."""
    household = get_active_household()
    current_user_id = session.get("user_id")

    swap = ChoreSwapRequest.query.get_or_404(swap_id)

    if swap.household_id != household.id:
        abort(404)

    # I check this so only the recipient can decline the swap.
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


# ---------------------------------------------------------
# Inventory
# ---------------------------------------------------------
# Reference: Flask templating with Jinja
# https://flask.palletsprojects.com/en/stable/templating/
@main_bp.route("/inventory")
@login_required
@household_required
def inventory_list():
    """I use this route to show the inventory page for the active household."""
    household = get_active_household()

    all_items = (
        InventoryItem.query
        .filter_by(household_id=household.id)
        .order_by(InventoryItem.name.asc())
        .all()
    )

    # I show a “frequent items” list if the model has a use_count field available.
    use_count_attr = getattr(InventoryItem, "use_count", None)
    if use_count_attr is not None:
        frequent_items = sorted(
            all_items,
            key=lambda i: getattr(i, "use_count", 0) or 0,
            reverse=True,
        )[:10]
    else:
        frequent_items = []

    # Inventory insights:
    # - Low stock items: quantity <= 1
    # - Frequent items: highest use_count values
    # Approach informed by AI-assisted suggestion for inventory dashboards.
    # Source: ChatGPT – Inventory feature prompt (Feb 2026) - https://chatgpt.com/share/69865b3d-3e40-8007-b7fd-0ff594971ab5

    # I treat quantity <= 1 as low stock so it stands out for the user.
    low_stock_items = [i for i in all_items if (getattr(i, "quantity", 0) or 0) <= 1]

    items = all_items

    today = date.today()
    active_filter = (request.args.get("filter") or "all").strip().lower()

    # I pre-calculate expiry info so the template can show warnings and filters easily.
    days_to_expiry = {}
    is_expired = {}
    is_expiring_soon = {}

    for item in items:
        if getattr(item, "expiry_date", None):
            diff = (item.expiry_date - today).days
            days_to_expiry[item.id] = diff
            is_expired[item.id] = diff < 0
            is_expiring_soon[item.id] = 0 <= diff <= 7

            # I notify the household when something is close to expiring so it doesn’t get wasted.
            if 0 <= diff <= 2:
                create_notification(
                    household_id=household.id,
                    user_id=None,
                    type="expiry_soon",
                    title="⚠️ Expiring soon",
                    message=f"{item.name} expires soon",
                    link_url=url_for("main.inventory_list"),
                )
        else:
            days_to_expiry[item.id] = None
            is_expired[item.id] = False
            is_expiring_soon[item.id] = False

    # I apply the selected filter so users can quickly see expired/expiring items.
    if active_filter == "expired":
        items = [i for i in items if is_expired.get(i.id)]
    elif active_filter == "expiring":
        items = [i for i in items if is_expiring_soon.get(i.id)]

    # I group items by category so the page stays organised.
    grouped = {cat: [] for cat in INVENTORY_CATEGORIES}
    grouped["Uncategorised"] = []

    for item in items:
        cat = (getattr(item, "category", None) or "").strip()
        if cat in grouped:
            grouped[cat].append(item)
        else:
            grouped["Uncategorised"].append(item)

    return render_template(
        "inventory.html",
        household=household,
        items=items,
        frequent_items=frequent_items,
        low_stock_items=low_stock_items,
        grouped_items=grouped,
        categories=INVENTORY_CATEGORIES,
        locations=INVENTORY_LOCATIONS,
        active_filter=active_filter,
        days_to_expiry=days_to_expiry,
        is_expired=is_expired,
        is_expiring_soon=is_expiring_soon,
    )


@main_bp.route("/inventory/add", methods=["POST"])
@login_required
@household_required
def inventory_add():
    """I use this route to add a new inventory item for the active household."""
    household = get_active_household()

    name = (request.form.get("name") or "").strip()
    qty_raw = (request.form.get("quantity") or "").strip()
    unit = (request.form.get("unit") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    category = (request.form.get("category") or "").strip()
    sub_category = (request.form.get("sub_category") or "").strip()
    location = (request.form.get("location") or "").strip()

    if not name:
        flash("Item name is required.", "warning")
        return redirect(url_for("main.inventory_list"))

    # I validate quantity as a whole number so the inventory counts stay predictable.
    quantity = 1
    if qty_raw:
        try:
            quantity = int(qty_raw)
            if quantity < 0:
                raise ValueError
        except ValueError:
            flash("Quantity must be a whole number (0 or more).", "danger")
            return redirect(url_for("main.inventory_list"))

    # I prevent duplicates so the inventory doesn’t end up with the same item repeated.
    existing = (
        InventoryItem.query
        .filter_by(household_id=household.id)
        .filter(InventoryItem.name.ilike(name))
        .first()
    )
    if existing:
        flash("That item already exists in your inventory.", "info")
        return redirect(url_for("main.inventory_list"))

    expiry_type = (request.form.get("expiry_type") or "").strip() or None
    expiry_date_raw = (request.form.get("expiry_date") or "").strip()

    # I parse the expiry date if the user provides one.
    expiry_date = None
    if expiry_date_raw:
        try:
            expiry_date = datetime.strptime(expiry_date_raw, "%Y-%m-%d").date()
        except ValueError:
            expiry_date = None

    item = InventoryItem(
        household_id=household.id,
        name=name,
        quantity=quantity,
        unit=unit or None,
        notes=notes or None,
        category=category or None,
        sub_category=sub_category or None,
        location=location or None,
        use_count=1,
        expiry_type=expiry_type,
        expiry_date=expiry_date,
    )
    db.session.add(item)
    db.session.commit()

    flash("Inventory item added.", "success")
    return redirect(url_for("main.inventory_list"))


@main_bp.route("/inventory/<int:item_id>/edit", methods=["POST"])
@login_required
@household_required
def inventory_edit(item_id: int):
    """I use this route to edit an inventory item, but only inside the active household."""
    household = get_active_household()

    item = InventoryItem.query.get_or_404(item_id)
    if item.household_id != household.id:
        abort(404)

    name = (request.form.get("name") or "").strip()
    qty_raw = (request.form.get("quantity") or "").strip()
    unit = (request.form.get("unit") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    category = (request.form.get("category") or "").strip()
    sub_category = (request.form.get("sub_category") or "").strip()
    location = (request.form.get("location") or "").strip()

    expiry_type = (request.form.get("expiry_type") or "").strip() or None
    expiry_date_raw = (request.form.get("expiry_date") or "").strip()

    expiry_date = None
    if expiry_date_raw:
        try:
            expiry_date = datetime.strptime(expiry_date_raw, "%Y-%m-%d").date()
        except ValueError:
            expiry_date = None

    if not name:
        flash("Item name is required.", "warning")
        return redirect(url_for("main.inventory_list"))

    # I validate the quantity again here so edits can’t save invalid values.
    try:
        quantity = int(qty_raw) if qty_raw != "" else item.quantity
        if quantity < 0:
            raise ValueError
    except ValueError:
        flash("Quantity must be a whole number (0 or more).", "danger")
        return redirect(url_for("main.inventory_list"))

    item.name = name
    item.quantity = quantity
    item.unit = unit or None
    item.notes = notes or None

    item.category = category or None
    item.sub_category = sub_category or None
    item.location = location or None

    item.expiry_type = expiry_type
    item.expiry_date = expiry_date

    # I increment use_count so the “frequent items” section reflects what gets updated/used.
    if hasattr(item, "use_count"):
        item.use_count = (item.use_count or 0) + 1

    db.session.commit()

    flash("Inventory item updated.", "success")
    return redirect(url_for("main.inventory_list"))


@main_bp.route("/inventory/<int:item_id>/use", methods=["POST"])
@login_required
@household_required
def inventory_use(item_id: int):
    """I use this route to record one use of an item (basically decrement the quantity)."""
    household = get_active_household()

    item = InventoryItem.query.get_or_404(item_id)
    if item.household_id != household.id:
        abort(404)

    # I clamp at 0 so the quantity can’t go negative.
    item.quantity = max(0, item.quantity - 1)
    if hasattr(item, "use_count"):
        item.use_count = (item.use_count or 0) + 1
    db.session.commit()

    # I send a low-stock notification so the household knows it’s nearly gone.
    if item.quantity <= 1:
        create_notification(
            household_id=household.id,
            user_id=None,
            type="inventory_low",
            title="🥛 Low stock",
            message=f"{item.name} is almost gone",
            link_url=url_for("main.inventory_list"),
        )

    flash("Use recorded.", "info")
    return redirect(url_for("main.inventory_list"))


@main_bp.route("/inventory/<int:item_id>/delete", methods=["POST"])
@login_required
@household_required
def inventory_delete(item_id: int):
    """I use this route to delete an inventory item from the active household."""
    household = get_active_household()

    item = InventoryItem.query.get_or_404(item_id)
    if item.household_id != household.id:
        abort(404)

    db.session.delete(item)
    db.session.commit()

    flash("Inventory item removed.", "info")
    return redirect(url_for("main.inventory_list"))


# ---------------------------------------------------------
# Expenses
# ---------------------------------------------------------
@main_bp.route("/expenses")
@login_required
@household_required
def expenses():
    """I use this route to list expenses and show what I owe / what people owe me."""
    household = get_active_household()
    current_user_id = session.get("user_id")

    expenses_list = (
        Expense.query
        .filter_by(household_id=household.id)
        .order_by(Expense.created_at.desc())
        .all()
    )

    household_members = get_household_members(household.id)

    # I calculate totals for the current user so the page can show a simple summary.
    my_total_owed = 0.0
    my_total_owed_to_me = 0.0

    my_owed_lines = []
    owed_by_person = {}
    owed_to_me_by_person = {}

    # I loop through each expense and use the shares table to work out who owes what.
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

    # I sort the summary lists so the biggest amounts show first.
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
    """I use this route to add an expense and create the per-user shares (even or custom split)."""
    household = get_active_household()

    title = request.form.get("title", "").strip()
    amount_str = request.form.get("total_amount", "").strip()
    split_method = request.form.get("split_method", "even").strip().lower()

    if not title or not amount_str:
        flash("Please enter an expense name and amount.", "danger")
        return redirect(url_for("main.expenses"))

    # I validate the total amount here to avoid saving broken data.
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

    # I work in cents to avoid rounding issues when splitting money.
    total_cents = int(round(total_amount * 100))

    try:
        if split_method == "custom":
            # I read each custom amount from the form and make sure it adds up exactly.
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

            # I notify other members so they see the new expense without needing to refresh.
            creator_id = session.get("user_id")
            members = get_household_members(household.id)
            for u in members:
                if u.id == creator_id:
                    continue
                create_notification(
                    household_id=household.id,
                    user_id=u.id,
                    type="expense_new",
                    title="💸 New expense added",
                    message=f"“{expense.title}” was added (€{expense.total_amount:.2f})",
                    link_url=url_for("main.expenses"),
                )

            flash("Expense added with custom split.", "success")
            return redirect(url_for("main.expenses"))

        # I split evenly and use a remainder method so the total stays exact in cents.
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

        # I notify other members about the new expense here too.
        creator_id = session.get("user_id")
        members = get_household_members(household.id)
        for u in members:
            if u.id == creator_id:
                continue
            create_notification(
                household_id=household.id,
                user_id=u.id,
                type="expense_new",
                title="💸 New expense added",
                message=f"“{expense.title}” was added (€{expense.total_amount:.2f})",
                link_url=url_for("main.expenses"),
            )

        flash("Expense added and split equally.", "success")
        return redirect(url_for("main.expenses"))

    except ValueError as e:
        # I rollback here so partial shares don’t get saved if validation fails.
        db.session.rollback()
        flash(str(e), "danger")
        return redirect(url_for("main.expenses"))


# ---------------------------------------------------------
# Calendar  NEW
# ---------------------------------------------------------
# Calendar feature (calendar page + JSON events feed for FullCalendar).
# Implemented with AI-assisted guidance to map chores/expenses into calendar events.
# Source: ChatGPT conversation – Calendar feature prompt (Feb 2026) - https://chatgpt.com/share/69866053-0d34-8007-9bfa-0f43543abcf2

@main_bp.route("/calendar")
@login_required
@household_required
def calendar_view():
    """I use this route to show the calendar page for the active household."""
    household = get_active_household()
    return render_template("calendar.html", household=household)


@main_bp.route("/api/calendar/events")
@login_required
@household_required
def calendar_events():
    """
    I use this route to return chores + expenses as JSON for FullCalendar.

    - Chores use due_date
    - Expenses use created_at date (converted to just a date)
    """
    household = get_active_household()
    today = date.today()
    current_user_id = session.get("user_id")

    events = []

    # I add chores as calendar events using their due date.
    chores = (
        Chore.query
        .filter_by(household_id=household.id)
        .filter(Chore.due_date != None)  # noqa: E711
        .all()
    )

    for c in chores:
        # I set a simple status so the frontend can colour-code events.
        status = "upcoming"
        if c.completed:
            status = "completed"
        elif c.due_date and c.due_date < today:
            status = "overdue"
        elif c.due_date == today:
            status = "due_today"

        assigned_to_me = (c.assigned_to_user_id == current_user_id)

        events.append({
            "id": f"chore-{c.id}",
            "title": f"🧹 {c.title}",
            "start": c.due_date.isoformat(),
            "allDay": True,
            "url": url_for("main.db_test_list"),
            "extendedProps": {
                "kind": "chore",
                "status": status,
                "completed": bool(c.completed),
                "assigned_to_me": bool(assigned_to_me),
                "assigned_to_user_id": c.assigned_to_user_id,
                "chore_id": c.id,
            },
        })

    # I add expenses as calendar events using the created_at date as a timeline marker.
    expenses = (
        Expense.query
        .filter_by(household_id=household.id)
        .order_by(Expense.created_at.desc())
        .all()
    )

    for e in expenses:
        created_date = e.created_at.date() if getattr(e, "created_at", None) else None
        if not created_date:
            continue

        events.append({
            "id": f"expense-{e.id}",
            "title": f"💸 {e.title}",
            "start": created_date.isoformat(),
            "allDay": True,
            "url": url_for("main.expenses"),
            "extendedProps": {
                "kind": "expense",
                "amount": float(getattr(e, "total_amount", 0) or 0),
                "paid_by_user_id": getattr(e, "paid_by_user_id", None),
                "expense_id": e.id,
            },
        })

    return jsonify(events)


# ---------------------------------------------------------
# Notifications API (Toast popups)
# ---------------------------------------------------------
# Notifications API endpoints (toast popups + mark-as-read).
# Implemented with AI-assisted guidance to support frontend polling and read-state updates.
# Source: ChatGPT conversation – Notifications feature prompt (Feb 2026) - https://chatgpt.com/share/69865e70-4154-8007-b020-98259faaf812

@main_bp.route("/api/notifications/unread")
@login_required
def unread_notifications():
    """I use this route to return a small list of unread notifications for toast popups."""
    household = get_active_household()
    user_id = session.get("user_id")

    if not household:
        return {"notifications": []}

    # I return household-wide notifications (user_id is None) and personal ones for this user.
    notes = (
        Notification.query
        .filter_by(household_id=household.id, is_read=False)
        .filter(
            (Notification.user_id == None) |  # noqa: E711
            (Notification.user_id == user_id)
        )
        .order_by(Notification.created_at.asc())
        .limit(5)
        .all()
    )

    return {
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "link_url": n.link_url,
            }
            for n in notes
        ]
    }


@main_bp.route("/api/notifications/<int:note_id>/read", methods=["POST"])
@login_required
def mark_notification_read(note_id: int):
    """I use this route to mark a single notification as read."""
    n = Notification.query.get_or_404(note_id)
    n.is_read = True
    db.session.commit()
    return {"ok": True}


# ---------------------------------------------------------
# Auth
# ---------------------------------------------------------
@main_bp.route("/register", methods=["GET", "POST"])
def register():
    """I use this route to register a new user account."""
    if request.method == "POST":
        # I clear the session so old login state can’t interfere with a new registration.
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

        # I block duplicate emails so accounts stay unique.
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
    """I use this route to log a user in and store their details in the session."""
    if request.method == "POST":
        # I clear session first to avoid mixing accounts if someone logs in after another user.
        session.clear()

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        # I only set session values if the password check passes.
        if user and user.check_password(password):
            session["user_id"] = user.id
            session["user_name"] = user.name

            # I restore the last active household so the user continues where they left off.
            if getattr(user, "active_household_id", None):
                session["active_household_id"] = user.active_household_id

            flash("Logged in successfully.", "success")
            return redirect(url_for("main.expenses"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@main_bp.route("/logout")
def logout():
    """I use this route to log the user out by clearing their session."""
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("main.index"))