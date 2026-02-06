import requests
from flask import current_app

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

    api_key = current_app.config.get("BREVO_API_KEY", "")
    sender_email = current_app.config.get("BREVO_SENDER_EMAIL", "")
    sender_name = current_app.config.get("BREVO_SENDER_NAME", "HOMI")

    # Fail silently if not configured (local dev safe)
    if not api_key or not sender_email:
        return False

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

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }

    try:
        response = requests.post(
            BREVO_SEND_URL,
            json=payload,
            headers=headers,
            timeout=10,
        )
        return response.status_code in (200, 201, 202)
    except requests.RequestException:
        return False
