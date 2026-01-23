"""
Flask application factory and extension setup.

Responsibilities:
- Load environment variables from a .env file
- Create and configure the Flask app instance
- Configure secret key and database connection
- Initialise Flask extensions (SQLAlchemy, Flask-Migrate)
- Register the main blueprint that contains routes
"""

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv

# Loads environment variables from a local .env file so configuration values
# (e.g., SECRET_KEY, DATABASE_URL) are available via os.getenv().
load_dotenv()

# Flask extensions are created once at module level.
# They are attached to the Flask app inside create_app() using init_app().
db = SQLAlchemy()
migrate = Migrate()


def create_app():
    """
    Create and configure a Flask application instance.

    Key configuration performed:
    - Ensures the instance folder exists (used for instance-specific files like SQLite DB)
    - Sets SECRET_KEY for session signing
    - Sets SQLALCHEMY_DATABASE_URI using DATABASE_URL or a local SQLite fallback
    - Disables SQLALCHEMY_TRACK_MODIFICATIONS to reduce overhead
    - Initialises SQLAlchemy and Flask-Migrate
    - Registers application blueprints (routes)
    """
    app = Flask(__name__, instance_relative_config=True)

    # Ensures the instance directory exists.
    # SQLite database file is stored here when DATABASE_URL is not provided.
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        # Directory creation failure is ignored to avoid crashing on restricted environments.
        pass

    # Secret key is required for Flask sessions (cookie signing).
    # A development fallback is used if SECRET_KEY is not set.
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")

    # Database connection string selection:
    # - Uses DATABASE_URL if defined (common for hosted DBs)
    # - Falls back to a local SQLite database inside the instance folder
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = (
            "sqlite:///" + os.path.join(app.instance_path, "app.db")
        )

    # Disables a SQLAlchemy feature that tracks object changes.
    # This reduces memory usage and avoids warnings in most Flask apps.
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Extension initialisation (binds the extensions to this app instance).
    db.init_app(app)
    migrate.init_app(app, db)

    # Blueprint registration:
    # Routes are kept in a blueprint to keep the project modular.
    from .main import main_bp
    app.register_blueprint(main_bp)

    return app
