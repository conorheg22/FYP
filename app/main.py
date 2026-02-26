"""
Main application routes and business logic.

Contains:
- Authentication (register, login, logout)
- Household creation, joining, and management
- Chore CRUD operations (db-test routes)
- Expense tracking (equal split + custom split + summary)
- Inventory items (Item 12)
"""

# Flask pieces we use for routes, templates, redirects, and JSON responses.
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
# Our database models: users, households, chores, expenses, swaps, inventory, notifications.
from .models import (
    Chore,
    Household,
    User,
    Expense,
    ExpenseShare,
    ChoreSwapRequest,
    InventoryItem,
    Notification,
    LeaderboardReward,
    ShoppingListItem,
)

from . import db
from .models import CHORE_REPEAT_TYPES
import random
import string
from functools import wraps
from datetime import date, datetime, timedelta, timezone

# This blueprint holds all our routes; we register it in __init__.py.
main_bp = Blueprint("main", __name__)


def _time_ago(dt):
    """Return a human-readable 'time ago' string for a datetime (e.g. '2 hours ago')."""
    if dt is None:
        return ""
    # Work in UTC so we compare times correctly no matter where the server is.
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    # Pick the right phrase based on how long ago it was (minutes, hours, days, weeks, months, years).
    if delta.total_seconds() < 60:
        return "just now"
    if delta.total_seconds() < 3600:
        m = int(delta.total_seconds() / 60)
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if delta.total_seconds() < 86400:
        h = int(delta.total_seconds() / 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if delta.days < 7:
        return f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
    if delta.days < 30:
        w = delta.days // 7
        return f"{w} week{'s' if w != 1 else ''} ago"
    if delta.days < 365:
        mo = delta.days // 30
        return f"{mo} month{'s' if mo != 1 else ''} ago"
    y = delta.days // 365
    return f"{y} year{'s' if y != 1 else ''} ago"


@main_bp.app_template_filter("time_ago")
def time_ago_filter(dt):
    """Jinja filter: {{ n.created_at|time_ago }}."""
    return _time_ago(dt)


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


def mark_notifications_read_for_page(household_id: int, user_id: int, link_path: str):
    """
    Mark as read all unread notifications for this user in this household
    whose link_url points to the given path. Call this when the user lands
    on a page so those notifications don't keep popping up as toasts.
    """
    if not link_path:
        return
    to_mark = (
        Notification.query
        .filter_by(household_id=household_id, is_read=False)
        .filter(
            (Notification.user_id == None) | (Notification.user_id == user_id)  # noqa: E711
        )
        .filter(Notification.link_url.isnot(None), Notification.link_url.like(f"%{link_path}"))
        .all()
    )
    for n in to_mark:
        n.is_read = True
    if to_mark:
        db.session.commit()


# ---------------------------------------------------------
# Home
# ---------------------------------------------------------
# The landing page when someone visits the site. Shows different content if they are logged in.
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

            # Notify the user they joined the household (user-specific).
            create_notification(
                household_id=household.id,
                user_id=user.id if user else None,
                type="household_joined",
                title="Welcome to the household",
                message=f"You joined {household.name}",
                link_url=url_for("main.expenses"),
            )

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
# The main chores page: lists overdue, upcoming, no-date, and completed chores and handles notifications.
@main_bp.route("/db-test")
@login_required
@household_required
def db_test_list():
    """I use this route to show the chores page for the active household."""
    household = get_active_household()
    today = date.today()
    user_id = session.get("user_id")

    # Mark chore-related notifications as read when the user visits this page
    # so they don't keep popping up as toasts every time they come here.
    chores_path = url_for("main.db_test_list")
    mark_notifications_read_for_page(household.id, user_id, chores_path)

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

    # Completed chores are not shown in the main list view; they drop off once done.
    completed_chores = []

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
    active_minutes_by_user = {u.id: 0 for u in users}
    unassigned_count = 0

    for c in active_chores:
        mins = getattr(c, "estimated_minutes", None) or 0
        if c.assigned_to_user_id:
            if c.assigned_to_user_id in active_by_user:
                active_by_user[c.assigned_to_user_id] += 1
                active_minutes_by_user[c.assigned_to_user_id] += mins
        else:
            unassigned_count += 1

    distribution = []
    for u in users:
        distribution.append({
            "name": u.name,
            "count": active_by_user.get(u.id, 0),
            "active_minutes": active_minutes_by_user.get(u.id, 0),
            "is_me": (u.id == session.get("user_id")),
        })

    max_count = max([d["count"] for d in distribution], default=0)
    max_minutes = max([d["active_minutes"] for d in distribution], default=0)

    completed_in_household = (
        Chore.query
        .filter_by(household_id=household.id)
        .filter(Chore.completed == True)  # noqa: E712
        .all()
    )
    overdue_count_by_user = {u.id: 0 for u in users}
    total_completed_by_user = {u.id: 0 for u in users}
    for c in completed_in_household:
        uid = c.completed_by_id or c.assigned_to_user_id
        if uid and uid in total_completed_by_user:
            total_completed_by_user[uid] += 1
            if getattr(c, "was_overdue", False):
                overdue_count_by_user[uid] += 1

    overdue_stats = []
    for u in users:
        total = total_completed_by_user.get(u.id, 0)
        overdue = overdue_count_by_user.get(u.id, 0)
        pct = round(overdue / total * 100) if total else 0
        overdue_stats.append({
            "name": u.name,
            "overdue_count": overdue,
            "total_completed": total,
            "overdue_pct": pct,
            "is_me": (u.id == session.get("user_id")),
        })

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
        max_minutes=max_minutes,
        overdue_stats=overdue_stats,

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
    repeat_type = (request.form.get("repeat_type") or "none").strip().lower()
    estimated_raw = (request.form.get("estimated_minutes") or "").strip()

    if not title:
        flash("Please enter a chore name.", "warning")
        return redirect(url_for("main.db_test_list"))

    if repeat_type not in CHORE_REPEAT_TYPES:
        repeat_type = "none"

    due_date = None
    if due_str:
        try:
            due_date = datetime.strptime(due_str, "%Y-%m-%d").date()
        except ValueError:
            due_date = None

    estimated_minutes = None
    if estimated_raw:
        try:
            estimated_minutes = int(estimated_raw)
            if estimated_minutes < 0:
                estimated_minutes = None
        except ValueError:
            pass

    c = Chore(
        title=title,
        household_id=household.id,
        due_date=due_date,
        repeat_type=repeat_type,
        estimated_minutes=estimated_minutes,
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


def _utc_now():
    """Return current UTC time (timezone-aware) for consistent storage and comparison."""
    return datetime.now(timezone.utc)


def _next_due_date_for_repeat(due_date: date | None, repeat_type: str) -> date | None:
    """
    Compute the next due date when a recurring chore is completed.
    Uses the completed chore's due_date as the base. Returns None if repeat_type is "none" or due_date is None.
    """
    if not due_date or not repeat_type or repeat_type == "none":
        return None
    today = date.today()
    # Daily means tomorrow; weekly means same day next week; monthly means same day next month (or last day if needed).
    if repeat_type == "daily":
        return today + timedelta(days=1)
    if repeat_type == "weekly":
        return today + timedelta(weeks=1)
    if repeat_type == "monthly":
        # Next month, same day if possible; else last day of month
        if today.month == 12:
            next_year, next_month = today.year + 1, 1
        else:
            next_year, next_month = today.year, today.month + 1
        try:
            return date(next_year, next_month, min(today.day, 28))
        except ValueError:
            import calendar
            last = calendar.monthrange(next_year, next_month)[1]
            return date(next_year, next_month, min(today.day, last))
    return None


# Reference: ChatGPT assisting with points/leaderboard functionality: https://chatgpt.com/share/6998b226-acd0-8007-a92c-8456ae64e0d8
# Reference: SQLAlchemy (2024) Updating and deleting rows with the ORM. https://docs.sqlalchemy.org/en/21/orm/tutorial.html#updating-and-deleting-with-the-orm
def _award_points_for_completion(chore, user, today: date):
    """Award points and update streak when a user completes a chore. Returns (total_points, new_streak_count)."""
    # Late completions get fewer base points; on-time gets more. Streak bonus adds extra for consecutive days.
    is_overdue = chore.due_date and chore.due_date < today
    base_points = 5 if is_overdue else 10
    if user.last_streak_date is None:
        new_streak = 1
    elif user.last_streak_date == today:
        new_streak = user.streak_count
    elif user.last_streak_date == today - timedelta(days=1):
        new_streak = user.streak_count + 1
    else:
        new_streak = 1
    if new_streak >= 14:
        streak_bonus = 30
    elif new_streak >= 7:
        streak_bonus = 15
    elif new_streak >= 3:
        streak_bonus = 5
    else:
        streak_bonus = 0
    total_points = base_points + streak_bonus
    user.points = (user.points or 0) + total_points
    user.streak_count = new_streak
    user.last_streak_date = today
    return total_points, new_streak


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

    current_user_id = session.get("user_id")
    if (
        chore.assigned_to_user_id is not None
        and chore.assigned_to_user_id != current_user_id
    ):
        flash("You can only complete chores assigned to you.", "danger")
        return redirect(url_for("main.db_test_list"))

    user = User.query.get(current_user_id)
    today = date.today()

    if chore.completed:
        if chore.points_awarded and chore.completed_by_id:
            completer = User.query.get(chore.completed_by_id)
            if completer:
                completer.points = max(0, (completer.points or 0) - chore.points_awarded)
        chore.completed = False
        chore.completed_at = None
        chore.completed_by_id = None
        chore.points_awarded = None
        chore.was_overdue = False
        db.session.commit()
        return redirect(url_for("main.db_test_list"))

    # Mark complete: timezone-safe timestamp and overdue flag
    now_utc = _utc_now()
    chore.completed = True
    chore.completed_at = now_utc
    chore.completed_by_id = current_user_id
    was_overdue = (
        chore.due_date is not None
        and now_utc.date() > chore.due_date
    )
    chore.was_overdue = was_overdue

    total_points, new_streak = _award_points_for_completion(chore, user, today)
    chore.points_awarded = total_points
    # Reference: SQLAlchemy (2024) Updating and deleting rows with the ORM. https://docs.sqlalchemy.org/en/21/orm/tutorial.html#updating-and-deleting-with-the-orm
    db.session.commit()

    # Recurring: create next chore (same title, estimated_minutes, assignee, household)
    repeat_type = getattr(chore, "repeat_type", None) or "none"
    next_due = _next_due_date_for_repeat(chore.due_date, repeat_type)
    if next_due is not None:
        next_chore = Chore(
            title=chore.title,
            household_id=chore.household_id,
            assigned_to_user_id=chore.assigned_to_user_id,
            due_date=next_due,
            repeat_type=repeat_type,
            estimated_minutes=getattr(chore, "estimated_minutes", None),
        )
        db.session.add(next_chore)
        db.session.commit()

    flash(
        f"Nice! You earned +{total_points} points (Streak: {new_streak} day{'s' if new_streak != 1 else ''} )",
        "success",
    )
    create_notification(
        household_id=household.id,
        user_id=current_user_id,
        type="chore_complete",
        title="Nice work!",
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
        repeat_type = (request.form.get("repeat_type") or "none").strip().lower()
        estimated_raw = (request.form.get("estimated_minutes") or "").strip()

        if title:
            chore.title = title

        if due_str:
            try:
                chore.due_date = datetime.strptime(due_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        else:
            chore.due_date = None

        if repeat_type in CHORE_REPEAT_TYPES:
            chore.repeat_type = repeat_type

        estimated_minutes = None
        if estimated_raw:
            try:
                estimated_minutes = int(estimated_raw)
                if estimated_minutes < 0:
                    estimated_minutes = None
            except ValueError:
                pass
        chore.estimated_minutes = estimated_minutes

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

    # Notify the user they were assigned this chore (household-aware, no duplicate).
    create_notification(
        household_id=household.id,
        user_id=session["user_id"],
        type="chore_assigned",
        title="Chore assigned",
        message=f"“{chore.title}” is now assigned to you",
        link_url=url_for("main.db_test_list"),
    )

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
# A user can request to swap a chore with another household member. The other user can accept or decline.
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

    # Cancel all other pending swaps for this chore so no ghost requests remain.
    ChoreSwapRequest.query.filter(
        ChoreSwapRequest.offered_chore_id == offered.id,
        ChoreSwapRequest.id != swap.id,
        ChoreSwapRequest.status == "pending",
    ).update({"status": "declined"})

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
# Household inventory: add, edit, use, and delete items. Track quantity, location, category, and expiry.
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
# Shopping List (shared household list, integrates with inventory)
# ---------------------------------------------------------
# View list at /shopping; add manually or from inventory; toggle picked up; delete; prompt to update stock when picked up.
@main_bp.route("/shopping")
@login_required
@household_required
def shopping_list():
    """I use this route to show the shared shopping list for the active household."""
    household = get_active_household()
    items = (
        ShoppingListItem.query
        .filter_by(household_id=household.id)
        .order_by(ShoppingListItem.picked_up.asc(), ShoppingListItem.created_at.asc())
        .all()
    )
    return render_template(
        "shopping.html",
        household=household,
        items=items,
        categories=INVENTORY_CATEGORIES,
    )


@main_bp.route("/shopping/add", methods=["POST"])
@login_required
@household_required
def shopping_add():
    """I use this route to add an item to the shopping list (manual: name, quantity, category)."""
    household = get_active_household()
    name = (request.form.get("name") or "").strip()
    qty_raw = (request.form.get("quantity") or "1").strip()
    category = (request.form.get("category") or "").strip() or None
    unit = (request.form.get("unit") or "").strip() or None

    if not name:
        flash("Item name is required.", "warning")
        return redirect(url_for("main.shopping_list"))

    try:
        quantity = int(qty_raw)
        if quantity < 1:
            quantity = 1
    except ValueError:
        quantity = 1

    item = ShoppingListItem(
        household_id=household.id,
        name=name,
        quantity=quantity,
        unit=unit,
        category=category,
    )
    db.session.add(item)
    db.session.commit()
    flash("Added to shopping list.", "success")
    return redirect(url_for("main.shopping_list"))


@main_bp.route("/shopping/add-from-inventory/<int:item_id>", methods=["POST"])
@login_required
@household_required
def shopping_add_from_inventory(item_id: int):
    """I use this route to add an inventory item to the shopping list when it is low or out of stock."""
    household = get_active_household()
    inv_item = InventoryItem.query.get_or_404(item_id)
    if inv_item.household_id != household.id:
        abort(404)

    # Avoid duplicate: same name already on list (optional — could allow multiple rows).
    existing = (
        ShoppingListItem.query
        .filter_by(household_id=household.id, name=inv_item.name, picked_up=False)
        .first()
    )
    if existing:
        existing.quantity = max(existing.quantity, inv_item.quantity or 1)
        existing.unit = inv_item.unit or existing.unit
        existing.category = inv_item.category or existing.category
        existing.inventory_item_id = inv_item.id
        db.session.commit()
        flash(f"Updated quantity for “{inv_item.name}” on the shopping list.", "info")
    else:
        sl_item = ShoppingListItem(
            household_id=household.id,
            name=inv_item.name,
            quantity=max(1, (inv_item.quantity or 0) + 1),
            unit=inv_item.unit,
            category=inv_item.category,
            inventory_item_id=inv_item.id,
        )
        db.session.add(sl_item)
        db.session.commit()
        flash(f"Added “{inv_item.name}” to the shopping list.", "success")
    return redirect(url_for("main.shopping_list"))


@main_bp.route("/api/shopping/<int:item_id>/toggle", methods=["POST"])
@login_required
@household_required
def shopping_toggle(item_id: int):
    """I use this API to toggle picked_up on a shopping list item (for real-time checkbox). Returns JSON."""
    household = get_active_household()
    item = ShoppingListItem.query.get_or_404(item_id)
    if item.household_id != household.id:
        abort(404)
    item.picked_up = not item.picked_up
    db.session.commit()
    return jsonify({
        "ok": True,
        "id": item.id,
        "picked_up": item.picked_up,
        "name": item.name,
        "quantity": item.quantity,
        "unit": item.unit,
        "inventory_item_id": item.inventory_item_id,
    })


@main_bp.route("/shopping/<int:item_id>/update-stock", methods=["POST"])
@login_required
@household_required
def shopping_update_stock(item_id: int):
    """I use this route to add quantity to the linked inventory item when user confirms 'update stock?' after picking up."""
    household = get_active_household()
    item = ShoppingListItem.query.get_or_404(item_id)
    if item.household_id != household.id:
        abort(404)
    qty_raw = (request.form.get("quantity_added") or request.form.get("quantity") or "").strip()
    try:
        to_add = int(qty_raw)
        if to_add < 1:
            to_add = item.quantity
    except ValueError:
        to_add = item.quantity
    if item.inventory_item_id:
        inv = InventoryItem.query.get(item.inventory_item_id)
        if inv and inv.household_id == household.id:
            inv.quantity = (inv.quantity or 0) + to_add
            if hasattr(inv, "use_count"):
                inv.use_count = (inv.use_count or 0) + 1
            db.session.commit()
            flash(f"Updated stock: “{inv.name}” +{to_add}.", "success")
    else:
        flash("No linked inventory item to update.", "info")
    return redirect(url_for("main.shopping_list"))


@main_bp.route("/shopping/<int:item_id>/delete", methods=["POST"])
@login_required
@household_required
def shopping_delete(item_id: int):
    """I use this route to remove an item from the shopping list."""
    household = get_active_household()
    item = ShoppingListItem.query.get_or_404(item_id)
    if item.household_id != household.id:
        abort(404)
    db.session.delete(item)
    db.session.commit()
    flash("Removed from shopping list.", "info")
    return redirect(url_for("main.shopping_list"))


# ---------------------------------------------------------
# Expenses
# ---------------------------------------------------------
# List household expenses and show who owes what. Add expenses with even split or custom amounts per person.
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
# Calendar page shows chores (by due date) and expenses (by date added) on a calendar. The events feed is used by FullCalendar.
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
# Analytics
# ---------------------------------------------------------
# Household analytics: chores, expenses, inventory, and overview. All data passed to template for Chart.js.
MEMBER_CHART_COLOURS = [
    "#5b4ae0", "#7c6cf7", "#16a34a", "#d97706", "#0ea5e9", "#8b5cf6", "#ec4899", "#14b8a6",
]


def _chore_analytics_for_window(household_id: int, members: list, since: datetime):
    """Build chore stats for a time window: per-member counts, on-time/overdue, by weekday, top/neglected titles, avg days to complete."""
    completed_in_window = (
        Chore.query
        .filter_by(household_id=household_id)
        .filter(Chore.completed == True, Chore.completed_at >= since)  # noqa: E712
        .all()
    )
    member_ids = [u.id for u in members]
    total_completed = {uid: 0 for uid in member_ids}
    total_minutes = {uid: 0 for uid in member_ids}
    overdue_count = {uid: 0 for uid in member_ids}
    on_time_count = {uid: 0 for uid in member_ids}
    by_weekday = {i: 0 for i in range(7)}  # Monday=0 .. Sunday=6
    creation_to_completion_days = {uid: [] for uid in member_ids}

    for c in completed_in_window:
        uid = c.completed_by_id or c.assigned_to_user_id
        if uid not in member_ids:
            continue
        total_completed[uid] = total_completed.get(uid, 0) + 1
        total_minutes[uid] = total_minutes.get(uid, 0) + (c.estimated_minutes or 0)
        if getattr(c, "was_overdue", False):
            overdue_count[uid] = overdue_count.get(uid, 0) + 1
        else:
            on_time_count[uid] = on_time_count.get(uid, 0) + 1
        if c.completed_at:
            by_weekday[(c.completed_at.weekday() + 1) % 7] = by_weekday.get((c.completed_at.weekday() + 1) % 7, 0) + 1
        if c.created_at and c.completed_at:
            delta = (c.completed_at.date() - c.created_at.date()).days
            creation_to_completion_days[uid].append(delta)

    top_chores = {}
    for c in completed_in_window:
        top_chores[c.title] = top_chores.get(c.title, 0) + 1
    top_5_completed = sorted(top_chores.items(), key=lambda x: -x[1])[:5]

    neglected = (
        Chore.query
        .filter_by(household_id=household_id)
        .filter(Chore.completed == False, Chore.due_date != None, Chore.due_date < date.today())  # noqa: E712, E711
        .all()
    )
    neglected_by_title = {}
    for c in neglected:
        neglected_by_title[c.title] = neglected_by_title.get(c.title, 0) + 1
    top_5_neglected = sorted(neglected_by_title.items(), key=lambda x: -x[1])[:5]

    avg_days_to_complete = {}
    for uid in member_ids:
        days_list = creation_to_completion_days.get(uid) or []
        avg_days_to_complete[uid] = round(sum(days_list) / len(days_list), 1) if days_list else None

    return {
        "members": [
            {
                "id": u.id,
                "name": u.name,
                "total_completed": total_completed.get(u.id, 0),
                "total_minutes": total_minutes.get(u.id, 0),
                "overdue_count": overdue_count.get(u.id, 0),
                "on_time_count": on_time_count.get(u.id, 0),
                "avg_days_to_complete": avg_days_to_complete.get(u.id),
                "is_me": False,
            }
            for u in members
        ],
        "by_weekday": [by_weekday.get(i, 0) for i in range(7)],
        "top_5_completed": top_5_completed,
        "top_5_neglected": top_5_neglected,
    }


@main_bp.route("/analytics")
@login_required
@household_required
def analytics():
    """I use this route to show household analytics: chores, expenses, inventory, and overview."""
    user = User.query.get(session["user_id"])
    household = get_active_household()
    members = get_household_members(household.id)
    current_user_id = session.get("user_id")
    today = date.today()

    # --- Chore analytics (30 and 90 days) ---
    since_30 = datetime.combine(today - timedelta(days=30), datetime.min.time())
    since_90 = datetime.combine(today - timedelta(days=90), datetime.min.time())
    chore_30 = _chore_analytics_for_window(household.id, members, since_30)
    chore_90 = _chore_analytics_for_window(household.id, members, since_90)
    for m in chore_30["members"]:
        m["is_me"] = m["id"] == current_user_id
    for m in chore_90["members"]:
        m["is_me"] = m["id"] == current_user_id

    # --- Expense analytics ---
    expenses_all = (
        Expense.query
        .filter_by(household_id=household.id)
        .all()
    )
    total_spend_all_time = sum(float(e.total_amount) for e in expenses_all)

    spend_by_month = []
    year, month = today.year, today.month
    for _ in range(6):
        month_start = date(year, month, 1)
        if month >= 12:
            next_month_start = date(year + 1, 1, 1)
        else:
            next_month_start = date(year, month + 1, 1)
        total = 0.0
        for e in expenses_all:
            if not e.created_at:
                continue
            ed = e.created_at.date() if hasattr(e.created_at, "date") else e.created_at
            if month_start <= ed < next_month_start:
                total += float(e.total_amount)
        spend_by_month.append({
            "label": month_start.strftime("%b %Y"),
            "total": round(total, 2),
        })
        month -= 1
        if month < 1:
            month, year = 12, year - 1
    spend_by_month.reverse()

    current_month_start = today.replace(day=1)
    current_month_spend = 0.0
    for e in expenses_all:
        if not e.created_at:
            continue
        ed = e.created_at.date() if hasattr(e.created_at, "date") else e.created_at
        if ed >= current_month_start:
            current_month_spend += float(e.total_amount)

    amount_paid = {u.id: 0.0 for u in members}
    amount_owed = {u.id: 0.0 for u in members}
    for e in expenses_all:
        amount_paid[e.paid_by_user_id] = amount_paid.get(e.paid_by_user_id, 0) + float(e.total_amount)
        for share in e.shares:
            amount_owed[share.user_id] = amount_owed.get(share.user_id, 0) + float(share.amount_owed)
    expense_balance = [
        {
            "id": u.id,
            "name": u.name,
            "paid": round(amount_paid.get(u.id, 0), 2),
            "owed": round(amount_owed.get(u.id, 0), 2),
            "net": round(amount_paid.get(u.id, 0) - amount_owed.get(u.id, 0), 2),
            "is_me": u.id == current_user_id,
        }
        for u in members
    ]

    # --- Inventory analytics ---
    inventory_items = (
        InventoryItem.query
        .filter_by(household_id=household.id)
        .all()
    )
    expiring_soon_count = 0
    expired_count = 0
    for item in inventory_items:
        if not getattr(item, "expiry_date", None):
            continue
        if item.expiry_date < today:
            expired_count += 1
        elif today <= item.expiry_date <= today + timedelta(days=7):
            expiring_soon_count += 1
    category_breakdown = {}
    for item in inventory_items:
        cat = (getattr(item, "category", None) or "").strip() or "Uncategorised"
        category_breakdown[cat] = category_breakdown.get(cat, 0) + 1
    low_stock = sorted(
        [i for i in inventory_items if (getattr(i, "quantity", 0) or 0) <= 2],
        key=lambda i: (getattr(i, "quantity", 0) or 0),
    )
    expiring_soon_items = []
    for item in inventory_items:
        if not getattr(item, "expiry_date", None):
            continue
        if today <= item.expiry_date <= today + timedelta(days=7):
            expiring_soon_items.append({
                "name": item.name,
                "expiry_date": item.expiry_date,
                "days_left": (item.expiry_date - today).days,
            })

    # --- Household overview (summary cards) ---
    total_chores_done_all_time = Chore.query.filter_by(household_id=household.id).filter(Chore.completed == True).count()  # noqa: E712
    overdue_now = (
        Chore.query
        .filter_by(household_id=household.id)
        .filter(Chore.completed == False, Chore.due_date != None, Chore.due_date < today)  # noqa: E712, E711
        .count()
    )
    this_month_start = today.replace(day=1)
    chores_this_month = (
        Chore.query
        .filter_by(household_id=household.id)
        .filter(Chore.completed == True, Chore.completed_at >= datetime.combine(this_month_start, datetime.min.time()))  # noqa: E712
        .all()
    )
    completions_this_month_by_user = {}
    for c in chores_this_month:
        uid = c.completed_by_id or c.assigned_to_user_id
        if uid:
            completions_this_month_by_user[uid] = completions_this_month_by_user.get(uid, 0) + 1
    most_active_this_month_id = None
    most_active_count = 0
    for uid, cnt in completions_this_month_by_user.items():
        if cnt > most_active_count:
            most_active_count = cnt
            most_active_this_month_id = uid
    most_active_member = next((u for u in members if u.id == most_active_this_month_id), None)
    top_streak_member = max(members, key=lambda u: u.streak_count or 0) if members else None

    return render_template(
        "analytics.html",
        household=household,
        user=user,
        current_user_id=current_user_id,
        members=members,
        member_colours=MEMBER_CHART_COLOURS,
        # Overview
        total_chores_done_all_time=total_chores_done_all_time,
        overdue_now=overdue_now,
        total_spend_all_time=round(total_spend_all_time, 2),
        current_month_spend=round(current_month_spend, 2),
        most_active_member=most_active_member,
        most_active_count=most_active_count,
        top_streak_member=top_streak_member,
        # Chores (30 & 90)
        chore_30=chore_30,
        chore_90=chore_90,
        # Expenses
        spend_by_month=spend_by_month,
        expense_balance=expense_balance,
        # Inventory
        expiring_soon_count=expiring_soon_count,
        expired_count=expired_count,
        category_breakdown=category_breakdown,
        low_stock=low_stock,
        expiring_soon_items=expiring_soon_items,
    )


# ---------------------------------------------------------
# Notifications API (Toast popups)
# ---------------------------------------------------------
# The frontend calls these endpoints to get unread notifications (for toasts) and to mark them as read.
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
        return {"unread_count": 0, "notifications": []}

    # I return household-wide notifications (user_id is None) and personal ones for this user.
    base_q = (
        Notification.query
        .filter_by(household_id=household.id, is_read=False)
        .filter(
            (Notification.user_id == None) | (Notification.user_id == user_id)  # noqa: E711
        )
    )
    unread_count = base_q.count()
    notes = (
        base_q.order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        "unread_count": unread_count,
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "link_url": n.link_url,
                "type": n.type,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ],
    }


@main_bp.route("/api/notifications/<int:note_id>/read", methods=["POST"])
@login_required
def mark_notification_read(note_id: int):
    """I use this route to mark a single notification as read (API, returns JSON)."""
    n = Notification.query.get_or_404(note_id)
    _ensure_notification_owns_or_household(n, session.get("user_id"))
    n.is_read = True
    db.session.commit()
    return {"ok": True}


def _ensure_notification_owns_or_household(n, user_id):
    """Abort 404 if the notification is not for this user or their active household."""
    # Security: only the intended user (or any member of the household for household-wide notifications) can act on it.
    if n.user_id is not None and n.user_id != user_id:
        abort(404)
    household = get_active_household()
    if household and n.household_id != household.id:
        abort(404)


@main_bp.route("/notifications")
@login_required
def notifications_page():
    """Full notifications page: all notifications for the logged-in user in the active household."""
    user_id = session.get("user_id")
    household = get_active_household()

    if not household:
        flash("Create or join a household to see notifications.", "info")
        return redirect(url_for("main.join_household"))

    # Notifications for this user in this household (household-wide or addressed to this user).
    query = (
        Notification.query
        .filter_by(household_id=household.id)
        .filter(
            (Notification.user_id == None) | (Notification.user_id == user_id)  # noqa: E711
        )
        .order_by(Notification.created_at.desc())
    )

    page = request.args.get("page", 1, type=int)
    per_page = 20
    if per_page < 1:
        per_page = 20
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    notifications = pagination.items

    unread_count = (
        Notification.query
        .filter_by(household_id=household.id, is_read=False)
        .filter(
            (Notification.user_id == None) | (Notification.user_id == user_id)  # noqa: E711
        )
        .count()
    )

    return render_template(
        "notifications.html",
        notifications=notifications,
        pagination=pagination,
        unread_count=unread_count,
        household=household,
    )


@main_bp.route("/notifications/<int:note_id>/read", methods=["POST"])
@login_required
def notification_mark_read_redirect(note_id: int):
    """Mark one notification as read and redirect back (for full page links)."""
    n = Notification.query.get_or_404(note_id)
    user_id = session.get("user_id")
    if n.user_id is not None and n.user_id != user_id:
        abort(404)
    household = get_active_household()
    if not household or n.household_id != household.id:
        abort(404)
    n.is_read = True
    db.session.commit()
    flash("Notification marked as read.", "info")
    return redirect(request.referrer or url_for("main.notifications_page"))


@main_bp.route("/notifications/mark_all_read", methods=["POST"])
@login_required
def notifications_mark_all_read():
    """Mark all notifications for the current user in the active household as read."""
    user_id = session.get("user_id")
    household = get_active_household()
    if not household:
        flash("No active household.", "warning")
        return redirect(url_for("main.join_household"))

    to_mark = (
        Notification.query
        .filter_by(household_id=household.id, is_read=False)
        .filter(
            (Notification.user_id == None) | (Notification.user_id == user_id)  # noqa: E711
        )
        .all()
    )
    for n in to_mark:
        n.is_read = True
    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for("main.notifications_page"))


@main_bp.route("/notifications/<int:note_id>/delete", methods=["POST"])
@login_required
def notification_delete(note_id: int):
    """Delete one notification (only if it belongs to this user or is household-wide for their household)."""
    n = Notification.query.get_or_404(note_id)
    user_id = session.get("user_id")
    if n.user_id is not None and n.user_id != user_id:
        abort(404)
    household = get_active_household()
    if not household or n.household_id != household.id:
        abort(404)
    db.session.delete(n)
    db.session.commit()
    flash("Notification deleted.", "info")
    return redirect(request.referrer or url_for("main.notifications_page"))


# ---------------------------------------------------------
# Auth
# ---------------------------------------------------------
# Register, login, and logout. Session stores user_id, user_name, and active_household_id.
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
            return render_template("register.html", name=name, email=email)

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("register.html", name=name, email=email)

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            return render_template("register.html", name=name, email=email)

        # I block duplicate emails so accounts stay unique.
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "warning")
            return render_template("register.html", name=name, email=email)

        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session["user_id"] = user.id
        session["user_name"] = user.name
        flash("Account created. Welcome!", "success")
        return redirect(url_for("main.welcome"))

    return render_template("register.html", name="", email="")


@main_bp.route("/welcome", methods=["GET", "POST"])
@login_required
def welcome():
    """After signup: prompt user to join a household with an invite code or skip."""
    if request.method == "POST":
        code = request.form.get("invite_code", "").strip()
        if not code:
            flash("Please enter an invite code.", "warning")
            return redirect(url_for("main.welcome"))

        household = Household.query.filter_by(invite_code=code).first()
        if household:
            session["active_household_id"] = household.id
            user = User.query.get(session.get("user_id"))
            if user:
                user.household_id = household.id
                user.active_household_id = household.id
                db.session.commit()

            create_notification(
                household_id=household.id,
                user_id=user.id if user else None,
                type="household_joined",
                title="Welcome to the household",
                message=f"You joined {household.name}",
                link_url=url_for("main.db_test_list"),
            )
            flash(f"Joined {household.name}. Welcome!", "success")
            return redirect(url_for("main.db_test_list"))

        flash("Invalid invite code. Please check and try again.", "danger")
        return redirect(url_for("main.welcome"))

    return render_template("welcome.html")


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

# ---------------------------------------------------------
# Profile 
# ---------------------------------------------------------
# The logged-in user can view and edit their name, email, and see badges earned from completing chores.
@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile_view():
    # Only the logged-in user can see this page; we load by session so it's always their own profile.
    # (If you add Flask-Login later, you can use current_user instead of this lookup.)
    user = User.query.get(session["user_id"])
    if not user:
        flash("Session invalid. Please log in again.", "warning")
        return redirect(url_for("main.login"))

    # Reference: Flask Project (2024) Request object – request.form and form data. https://flask.palletsprojects.com/en/3.0.x/reqcontext/#the-request-object
    # Reference: Flask Project (2024) File uploads – request.files. https://flask.palletsprojects.com/en/3.0.x/patterns/fileuploads/
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()

        if not name:
            flash("Name is required.", "danger")
            return render_template("profile.html", user=user, badges=[])
        if not email:
            flash("Email is required.", "danger")
            return render_template("profile.html", user=user, badges=[])

        # If they changed email, make sure it's not already used by another user.
        if email != user.email:
            existing = User.query.filter_by(email=email).first()
            if existing:
                flash("That email is already in use by another account.", "danger")
                return render_template("profile.html", user=user, badges=[])

        user.name = name
        user.email = email
        db.session.commit()
        session["user_name"] = user.name
        flash("Profile updated.", "success")
        return redirect(url_for("main.profile_view"))

    # Badges are earned from chore completions (e.g. first clean, on fire, reliable). We need the household to work out the weekly champion.
    badges = []
    household = get_active_household()
    if household and user.household_id == household.id:
        week_ago = date.today() - timedelta(days=7)
        chores_in_week = (
            Chore.query
            .filter_by(household_id=household.id)
            .filter(Chore.completed_at != None, Chore.completed_at >= datetime.combine(week_ago, datetime.min.time()))
            .all()
        )
        weekly_points = {}
        for c in chores_in_week:
            if c.completed_by_id:
                weekly_points[c.completed_by_id] = weekly_points.get(c.completed_by_id, 0) + (c.points_awarded or 0)
        weekly_champion_id = min((uid for uid, pts in weekly_points.items() if pts == max(weekly_points.values())), default=None) if weekly_points else None
        badges = _get_badges_for_user(household.id, user.id, weekly_champion_id)
    # Reference: Python Software Foundation (2024) Built-in Types – dict. https://docs.python.org/3/library/stdtypes.html#mapping-types-dict
    return render_template("profile.html", user=user, badges=badges)


# ---------------------------------------------------------
# Members (view housemates and their profiles)
# ---------------------------------------------------------
# List everyone in the active household and link to their profile. Shows chore counts and a "most active" badge.
@main_bp.route("/members")
@login_required
@household_required
def members_list():
    """I show a list of all members in the active household so housemates can see who they live with."""
    household = get_active_household()
    members = get_household_members(household.id)
    current_user_id = session.get("user_id")

    # I load all chores for this household so I can count assigned and completed per user.
    household_chores = (
        Chore.query
        .filter_by(household_id=household.id)
        .all()
    )

    # Reference: Python Software Foundation (2024) Built-in Types – dict. https://docs.python.org/3/library/stdtypes.html#mapping-types-dict
    # Build a list of member summaries: name, id, completed count, assigned count, is_me, and most_active badge.
    completed_per_user = {u.id: 0 for u in members}
    assigned_per_user = {u.id: 0 for u in members}
    for c in household_chores:
        if c.assigned_to_user_id in assigned_per_user:
            assigned_per_user[c.assigned_to_user_id] += 1
            if c.completed:
                completed_per_user[c.assigned_to_user_id] += 1

    # Who has the most completed chores (for "Most active" badge); tie goes to first.
    most_active_user_id = None
    most_completed = 0
    for uid, cnt in completed_per_user.items():
        if cnt > most_completed:
            most_completed = cnt
            most_active_user_id = uid

    member_cards = []
    for u in members:
        member_cards.append({
            "user_id": u.id,
            "user_name": u.name,
            "chores_completed": completed_per_user[u.id],
            "chores_assigned": assigned_per_user[u.id],
            "is_me": (u.id == current_user_id),
            "is_most_active": (u.id == most_active_user_id and most_completed > 0),
        })

    # Optional: sort by most active (most completed first) then by name.
    member_cards.sort(key=lambda m: (-m["chores_completed"], m["user_name"].lower()))

    return render_template(
        "members.html",
        household=household,
        members=member_cards,
    )


@main_bp.route("/members/<int:user_id>")
@login_required
@household_required
def member_profile(user_id: int):
    """I show one member's public profile. Only allowed if they are in the same household as the logged-in user."""
    household = get_active_household()
    current_user_id = session.get("user_id")
    today = date.today()

    # Load the requested user and make sure they exist and belong to our household.
    user = User.query.get(user_id)
    if not user:
        flash("That member was not found.", "warning")
        return redirect(url_for("main.members_list"))
    if user.household_id != household.id:
        flash("You can only view profiles of people in your household.", "danger")
        return redirect(url_for("main.members_list"))

    # Count chores assigned to this user and how many are completed (using household chores only).
    chores_assigned = (
        Chore.query
        .filter_by(household_id=household.id, assigned_to_user_id=user.id)
        .all()
    )
    chores_completed = [c for c in chores_assigned if c.completed]
    assigned_count = len(chores_assigned)
    completed_count = len(chores_completed)

    # Join date: we use the user's account created_at as "member since".
    join_date = user.created_at.strftime("%d %b %Y") if user.created_at else None

    # Check if this profile is the logged-in user (for "You" badge and slight styling).
    is_me = user.id == current_user_id

    # Who is most active in the household (for optional "Most active" badge on profile)?
    members = get_household_members(household.id)
    household_chores = Chore.query.filter_by(household_id=household.id).all()
    completed_by_user = {u.id: 0 for u in members}
    for c in household_chores:
        if c.completed and c.assigned_to_user_id in completed_by_user:
            completed_by_user[c.assigned_to_user_id] += 1
    most_completed = max(completed_by_user.values()) if completed_by_user else 0
    # Only one member gets the "Most active" badge; tie-break by smallest user id.
    first_among_tied = min((uid for uid, cnt in completed_by_user.items() if cnt == most_completed), default=None)
    is_most_active = most_completed > 0 and user.id == first_among_tied

    # Weekly champion for Household Hero badge.
    week_ago = today - timedelta(days=7)
    chores_in_week = (
        Chore.query
        .filter_by(household_id=household.id)
        .filter(Chore.completed_at != None, Chore.completed_at >= datetime.combine(week_ago, datetime.min.time()))
        .all()
    )
    weekly_points = {}
    for c in chores_in_week:
        if c.completed_by_id:
            weekly_points[c.completed_by_id] = weekly_points.get(c.completed_by_id, 0) + (c.points_awarded or 0)
    weekly_champion_id = min((uid for uid, pts in weekly_points.items() if pts == max(weekly_points.values())), default=None) if weekly_points else None
    badges = _get_badges_for_user(household.id, user.id, weekly_champion_id)

    return render_template(
        "member_profile.html",
        household=household,
        member=user,
        assigned_count=assigned_count,
        completed_count=completed_count,
        join_date=join_date,
        is_me=is_me,
        is_most_active=is_most_active,
        badges=badges,
    )


# Reference: Python Software Foundation (2024) Built-in Types – dict. https://docs.python.org/3/library/stdtypes.html#mapping-types-dict
def _get_badges_for_user(household_id: int, user_id: int, weekly_champion_id: int | None):
    """I compute which badges a user has earned (from chore completion data). Returns a list of badge keys."""
    badges = []
    household_chores = Chore.query.filter_by(household_id=household_id).all()
    # Count completions by this user: we use completed_by_id when set, or the assignee for older completed chores.
    completions = [
        c for c in household_chores
        if c.completed and (c.completed_by_id == user_id or (c.assigned_to_user_id == user_id and not c.completed_by_id))
    ]
    total_completed = len(completions)
    user = User.query.get(user_id)
    if not user:
        return badges
    if total_completed >= 1:
        badges.append("first_clean")
    if (user.streak_count or 0) >= 7:
        badges.append("on_fire")
    if total_completed >= 10:
        badges.append("reliable")
    # Speedrunner: 3+ chores in one day (need completed_at).
    by_date = {}
    for c in household_chores:
        if c.completed_by_id == user_id and c.completed_at:
            d = c.completed_at.date() if hasattr(c.completed_at, "date") else c.completed_at
            by_date[d] = by_date.get(d, 0) + 1
    if any(count >= 3 for count in by_date.values()):
        badges.append("speedrunner")
    if user_id == weekly_champion_id:
        badges.append("household_hero")
    return badges


# ---------------------------------------------------------
# Leaderboard (points and streaks)
# ---------------------------------------------------------
# Reference: Stack Overflow Leaderboard (Flask/Jinja creating a leaderboard from dict): https://stackoverflow.com/questions/17911276/flask-jinja-creating-a-leaderboard-out-of-an-unordered-dict-object
# Reference: ChatGPT assisting with points/leaderboard functionality: https://chatgpt.com/share/6998b226-acd0-8007-a92c-8456ae64e0d8
# Shows each household member's points, streak, badges, and who is the weekly champion (most points in last 7 days).
@main_bp.route("/leaderboard")
@login_required
@household_required
def leaderboard_view():
    """I show the household leaderboard: points, streaks, weekly champion, and badges."""
    household = get_active_household()
    members = get_household_members(household.id)
    current_user_id = session.get("user_id")
    today = date.today()
    week_ago = today - timedelta(days=7)

    # Weekly champion: most points earned in the last 7 days (from chore completions with completed_at).
    chores_in_week = (
        Chore.query
        .filter_by(household_id=household.id)
        .filter(Chore.completed_at != None, Chore.completed_at >= datetime.combine(week_ago, datetime.min.time()))
        .all()
    )
    # Reference: Python Software Foundation (2024) Built-in Types – dict. https://docs.python.org/3/library/stdtypes.html#mapping-types-dict
    weekly_points = {}
    for c in chores_in_week:
        if c.completed_by_id:
            weekly_points[c.completed_by_id] = weekly_points.get(c.completed_by_id, 0) + (c.points_awarded or 0)
    weekly_champion_id = None
    if weekly_points:
        max_weekly = max(weekly_points.values())
        weekly_champion_id = min(uid for uid, pts in weekly_points.items() if pts == max_weekly)

    # Build leaderboard rows: user, points, streak, badges, is_me.
    rows = []
    for u in members:
        badges = _get_badges_for_user(household.id, u.id, weekly_champion_id)
        rows.append({
            "user_id": u.id,
            "user_name": u.name,
            "points": u.points or 0,
            "streak_count": u.streak_count or 0,
            "badges": badges,
            "is_me": u.id == current_user_id,
            "is_weekly_champion": u.id == weekly_champion_id,
        })
    # Reference: W3Schools (n.d.) Python list sort() method. https://www.w3schools.com/python/ref_list_sort.asp
    rows.sort(key=lambda r: (-r["points"], r["user_name"].lower()))

    # Rewards: pre-made (household_id NULL) + custom for this household.
    premade = (
        LeaderboardReward.query
        .filter_by(household_id=None)
        .order_by(LeaderboardReward.id.asc())
        .all()
    )
    custom = (
        LeaderboardReward.query
        .filter_by(household_id=household.id)
        .order_by(LeaderboardReward.created_at.asc())
        .all()
    )
    available_rewards = list(premade) + list(custom)
    selected_reward = household.selected_leader_reward if household else None

    return render_template(
        "leaderboard.html",
        household=household,
        leaderboard=rows,
        weekly_champion_id=weekly_champion_id,
        available_rewards=available_rewards,
        selected_reward=selected_reward,
    )


@main_bp.route("/leaderboard/reward/select", methods=["POST"])
@login_required
@household_required
def leaderboard_select_reward():
    """Set the household's selected reward for the leader."""
    household = get_active_household()
    reward_id_raw = (request.form.get("reward_id") or "").strip()

    if not reward_id_raw:
        household.selected_leader_reward_id = None
        db.session.commit()
        flash("Leader reward cleared.", "info")
        return redirect(url_for("main.leaderboard_view"))

    try:
        reward_id = int(reward_id_raw)
    except ValueError:
        flash("Invalid reward.", "danger")
        return redirect(url_for("main.leaderboard_view"))

    reward = LeaderboardReward.query.get(reward_id)
    if not reward:
        flash("Reward not found.", "danger")
        return redirect(url_for("main.leaderboard_view"))

    # Pre-made (household_id is None) or custom for this household.
    if reward.household_id is not None and reward.household_id != household.id:
        flash("You can only select a reward for your household.", "danger")
        return redirect(url_for("main.leaderboard_view"))

    household.selected_leader_reward_id = reward.id
    db.session.commit()
    flash(f"Leader reward set: {reward.title}", "success")
    return redirect(url_for("main.leaderboard_view"))


@main_bp.route("/leaderboard/reward/add", methods=["POST"])
@login_required
@household_required
def leaderboard_add_reward():
    """Add a custom reward for this household."""
    household = get_active_household()
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()

    if not title:
        flash("Reward title is required.", "warning")
        return redirect(url_for("main.leaderboard_view"))

    reward = LeaderboardReward(
        household_id=household.id,
        title=title[:200],
        description=description[:500] if description else None,
        created_by_user_id=session.get("user_id"),
    )
    db.session.add(reward)
    db.session.commit()
    flash(f"Custom reward added: {reward.title}", "success")
    return redirect(url_for("main.leaderboard_view"))


@main_bp.route("/leaderboard/reward/<int:reward_id>/delete", methods=["POST"])
@login_required
@household_required
def leaderboard_delete_reward(reward_id: int):
    """Delete a custom reward (only if it belongs to this household)."""
    household = get_active_household()
    reward = LeaderboardReward.query.get_or_404(reward_id)

    if reward.household_id != household.id:
        flash("You can only delete your household's custom rewards.", "danger")
        return redirect(url_for("main.leaderboard_view"))

    if household.selected_leader_reward_id == reward.id:
        household.selected_leader_reward_id = None
    db.session.delete(reward)
    db.session.commit()
    flash("Custom reward removed.", "info")
    return redirect(url_for("main.leaderboard_view"))