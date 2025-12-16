"""
App factory and core configuration for the Flask application.

- Creates the Flask app instance
- Loads environment variables from .env
- Configures the SQLite database and migrations
- Registers the main blueprint that holds all routes
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
import os

# Global extension instances (not bound to any app yet)
db = SQLAlchemy()
migrate = Migrate()


def create_app():
    """Application factory function.

    - Called by Flask to create an app instance
    - Wires up config, database, migrations and blueprints
    """
    # Load .env explicitly from project root (one level above /app)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(project_root, ".env"))

    # Create the Flask app and tell it where templates/static files live
    app = Flask(
        __name__,
        instance_relative_config=True,  # Puts instance/ folder outside package
        template_folder="../templates",
        static_folder="../static",
    )

    # Ensure the 'instance' folder exists (used for app.db etc.)
    os.makedirs(app.instance_path, exist_ok=True)

    # ---- Core configuration values ----

    # Sessions require a SECRET_KEY. Support both SECRET_KEY and FLASK_SECRET_KEY from .env
    app.config["SECRET_KEY"] = (
        os.getenv("SECRET_KEY")
        or os.getenv("FLASK_SECRET_KEY")
        or "dev-key"
    )

    # Build a default SQLite URI for instance/app.db (Windows-safe)
    db_path = os.path.join(app.instance_path, "app.db")
    default_sqlite = "sqlite:///" + db_path.replace("\\", "/")

    # Use DATABASE_URL if set; otherwise use the instance/app.db default
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", default_sqlite)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # (Optional) Debug prints — remove once everything is working
    print("Instance path:", app.instance_path)
    print("DB URI:", app.config["SQLALCHEMY_DATABASE_URI"])
    print("SECRET_KEY set?", bool(app.config.get("SECRET_KEY")))

    # Attach extensions to this specific app instance
    db.init_app(app)
    migrate.init_app(app, db)

    # Import models so Alembic / SQLAlchemy know about them
    from . import models  # noqa: F401

    # Register the main blueprint that contains all routes
    from .main import main_bp
    app.register_blueprint(main_bp)

    return app
