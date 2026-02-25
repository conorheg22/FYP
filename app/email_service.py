# This file sends emails using the Brevo (formerly Sendinblue) email service.
import requests
from flask import current_app

# The web address that Brevo uses to receive and send our emails.
BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    html: str,
    text: str = ""
) -> bool:
    """
    Send a transactional email using Brevo.
    Returns True if Brevo accepts the request.
    """

    # Read the email settings from the app config (set in .env or __init__.py).
    api_key = current_app.config.get("BREVO_API_KEY", "")
    sender_email = current_app.config.get("BREVO_SENDER_EMAIL", "")
    sender_name = current_app.config.get("BREVO_SENDER_NAME", "HOMI")

    # If email is not set up, do nothing and return False so the app still works (e.g. on your own computer).
    if not api_key or not sender_email:
        return False

    # Build the message: who it is from, who it is to, subject, and the body in HTML and plain text.
    payload = {
        "sender": {
            "email": sender_email,
            "name": sender_name,
        },
        "to": [
            {
                "email": to_email,
                "name": to_name or to_email,
            }
        ],
        "subject": subject,
        "htmlContent": html,
        "textContent": text or "",
    }

    # Tell Brevo we are sending JSON and include the secret key so they know it is us.
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }

    # Send the email to Brevo. If the request succeeds (status 200, 201, or 202), return True.
    try:
        response = requests.post(
            BREVO_SEND_URL,
            json=payload,
            headers=headers,
            timeout=10,
        )
        return response.status_code in (200, 201, 202)
    # If the network fails or Brevo returns an error, return False so the app does not crash.
    except requests.RequestException:
        return False
