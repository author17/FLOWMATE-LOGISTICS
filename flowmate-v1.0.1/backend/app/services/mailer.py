import smtplib, ssl
from email.message import EmailMessage
from .. import config

def configured() -> bool: return bool(config.SMTP_HOST and config.SMTP_FROM)

def send_email(to: list[str], subject: str, body: str, attachments: list[tuple[str, bytes, str]] | None = None) -> bool:
    """Returns False (does nothing) when email is not set up - the app keeps working with in-app notifications only."""
    if not configured() or not to: return False
    m = EmailMessage(); m["From"], m["To"], m["Subject"] = config.SMTP_FROM, ", ".join(to), subject; m.set_content(body)
    for name, data, mime in attachments or []:
        main, _, sub = mime.partition("/"); m.add_attachment(data, maintype=main, subtype=sub or "octet-stream", filename=name)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as s:
        s.starttls(context=ssl.create_default_context())
        if config.SMTP_USER: s.login(config.SMTP_USER, config.SMTP_PASS)
        s.send_message(m)
    return True
