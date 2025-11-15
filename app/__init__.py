from flask import Flask         # Imports Flask framework
from flask_sqlalchemy import SQLAlchemy  # Adds database support
from flask_migrate import Migrate        # Adds database migration support
from dotenv import load_dotenv           # Loads variables from .env file
import os                       # Used for file paths

db = SQLAlchemy()               # Creates a database object (not linked yet)
migrate = Migrate()             # Creates migration tool object

def create_app():
    load_dotenv()               # Loads .env file into environment variables

    # Creates the Flask app and points it to the template and static folders
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="../templates",
        static_folder="../static",
    )

    os.makedirs(app.instance_path, exist_ok=True)  # Makes sure 'instance' folder exists

    # Builds the database path inside 'instance'
    default_sqlite = "sqlite:///" + os.path.join(app.instance_path, "app.db")

    # Basic configuration settings
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-key")  # Security key
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", default_sqlite)  # DB path
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False  # Turns off unused feature

    db.init_app(app)             # Connects database to app
    migrate.init_app(app, db)    # Connects migration tool to app

    from . import models         # Imports models so tables are known

    from .main import main_bp    # Imports blueprint (routes)
    app.register_blueprint(main_bp)  # Adds blueprint to app

    return app                   # Returns the ready-to-use app
