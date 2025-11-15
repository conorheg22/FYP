from app import create_app      # Imports the function that builds the Flask app
app = create_app()              # Calls that function to create the app instance

if __name__ == "__main__":      # Runs this only if the file is started directly
    app.run(debug=True)         # Starts the Flask development server with debug mode on
