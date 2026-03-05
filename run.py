# This file is the entry point when you run the app (e.g. python run.py).
# We need the OS module for the port setting and the app factory to create the Flask app.
import os
from app import create_app

# Build the Flask app using the factory so config, database, and routes are all set up.
app = create_app()

# Only start the server when this file is run directly, not when it is imported.
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
