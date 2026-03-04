"""
App factory and core configuration for the Flask application.

- Creates the Flask app instance
- Loads environment variables from .env
- Configures the SQLite database and migrations
- Registers the main blueprint that holds all routes
"""

# We use Flask for the web app, SQLAlchemy for the database, and Migrate for database version changes.
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
import os

# Create the database and migration objects here so we can use them in models and routes. They get attached to the app later.
db = SQLAlchemy()
migrate = Migrate()


def create_app():
    """Application factory function.

    - Called by Flask to create an app instance
    - Wires up config, database, migrations and blueprints
    """
    # Load environment variables from the .env file in the project root so we can use SECRET_KEY, database URL, etc.
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(project_root, ".env"))

    # Create the Flask app and tell it where to find HTML templates and static files (CSS, JS, images).
    app = Flask(
        __name__,
        instance_relative_config=True,  # Puts instance/ folder outside package
        template_folder="../templates",
        static_folder="../static",
    )

    # Create the instance folder if it does not exist. This is where the SQLite database file (app.db) and other app data live.
    os.makedirs(app.instance_path, exist_ok=True)

    # ---- Core configuration values ----
    # These values control how the app behaves. They can come from .env or use defaults.

    # Sessions need a secret key so Flask can sign cookies safely. We check both possible .env variable names.
    app.config["SECRET_KEY"] = (
        os.getenv("SECRET_KEY")
        or os.getenv("FLASK_SECRET_KEY")
        or "dev-key"
    )

    # Build the path to the database file. We fix backslashes for Windows so the URL is valid.
    db_path = os.path.join(app.instance_path, "app.db")
    default_sqlite = "sqlite:///" + db_path.replace("\\", "/")

    # Use DATABASE_URL from env; rewrite Render's postgres:// to postgresql:// for SQLAlchemy/psycopg2.
    db_url = os.getenv("DATABASE_URL", default_sqlite)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    # Turn off change tracking because we do not need it and it uses extra memory.
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Optional: print config at startup so you can check paths and that SECRET_KEY is set. You can remove these later.
    print("Instance path:", app.instance_path)
    print("DB URI:", app.config["SQLALCHEMY_DATABASE_URI"])
    print("SECRET_KEY set?", bool(app.config.get("SECRET_KEY")))

    # Connect the database and migration extensions to this app so we can use db.session and run migrations.
    db.init_app(app)
    migrate.init_app(app, db)

    # Import models so that Alembic and SQLAlchemy know about all our tables (User, Household, Chore, etc.).
    from . import models  # noqa: F401

    # Register the main blueprint so all the routes in main.py (login, chores, expenses, etc.) are active.
    from .main import main_bp
    app.register_blueprint(main_bp)

    with app.app_context():
        db.create_all()

        # Add expense_share paid columns if missing (SQLite doesn't support ADD COLUMN IF NOT EXISTS in older versions)
        from sqlalchemy import text
        with db.engine.connect() as conn:
            dialect_name = db.engine.dialect.name
            if dialect_name == "sqlite":
                result = conn.execute(text("PRAGMA table_info(expense_share)"))
                existing = {row[1] for row in result}
                for col, sql in [
                    ("paid", "ALTER TABLE expense_share ADD COLUMN paid INTEGER NOT NULL DEFAULT 0"),
                    ("paid_method", "ALTER TABLE expense_share ADD COLUMN paid_method VARCHAR(40)"),
                    ("paid_at", "ALTER TABLE expense_share ADD COLUMN paid_at DATETIME"),
                ]:
                    if col not in existing:
                        try:
                            conn.execute(text(sql))
                            conn.commit()
                        except Exception:
                            conn.rollback()
            else:
                for sql in [
                    "ALTER TABLE expense_share ADD COLUMN IF NOT EXISTS paid BOOLEAN NOT NULL DEFAULT FALSE",
                    "ALTER TABLE expense_share ADD COLUMN IF NOT EXISTS paid_method VARCHAR(40)",
                    "ALTER TABLE expense_share ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP",
                ]:
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                    except Exception:
                        conn.rollback()

    return app
