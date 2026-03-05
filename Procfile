# Run the web app with gunicorn (used by Heroku/Render).
# REF: Render Documentation - Deploying a Python/Flask Application - https://render.com/docs/deploy-flask
# REF: How to Deploy a Flask App to Render - https://www.youtube.com/watch?v=_COyD1CExKU
# REF: Claude Assisting with Render Deployment - https://claude.ai/share/8681822e-ffab-4b16-a4be-44d715a11edf
# REF: Gunicorn Documentation - Configuration - https://gunicorn.org/configure/?h=config
web: gunicorn "app:create_app()" --bind 0.0.0.0:$PORT
