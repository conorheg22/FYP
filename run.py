# This file is the entry point when you run the app (e.g. python run.py).
from app import create_app
# Build the Flask app using the factory so config, database, and routes are all set up.
app = create_app()

# Only start the server when this file is run directly, not when it is imported.
if __name__ == "__main__":
    # Start the development server with debug mode on so changes reload and errors show details.
    app.run(debug=True)
