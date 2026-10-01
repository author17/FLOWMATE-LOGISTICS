"""Text-message (SMS) codes for two-step login. Needs an SMS provider account (Twilio) - costs a few cents per message.
SMS_PROVIDER=twilio + TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN + TWILIO_FROM (a number or sender name).  SMS_PROVIDER=console is for tests only."""
import os, logging
import httpx

log = logging.getLogger("uvicorn.error")
LAST: dict[str, str] = {}   # test provider: last message per phone number

def provider() -> str: return os.getenv("SMS_PROVIDER", "").lower()
def configured() -> bool:
    p = provider()
    return p == "console" or (p == "twilio" and all(os.getenv(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM")))

def normalize_phone(raw: str) -> str | None:
    """+357 96 540597 / 0035796540597 / 96540597 (8 digits = Cyprus) -> +35796540597"""
    s = "".join(ch for ch in (raw or "") if ch.isdigit() or ch == "+")
    if s.startswith("00"): s = "+" + s[2:]
    if not s.startswith("+"):
        if len(s) == 8: s = "+357" + s
        else: return None
    digits = s[1:]
    return s if digits.isdigit() and 9 <= len(digits) <= 15 else None

def mask(phone: str) -> str: return phone[:4] + " ••• " + phone[-2:] if phone and len(phone) > 6 else "your phone"

def send_sms(to: str, text: str) -> None:
    if not configured(): raise RuntimeError("SMS is not set up on this server")
    if provider() == "console": LAST[to] = text; log.warning("SMS to %s: %s", to, text); return
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]),
                   data={"From": os.environ["TWILIO_FROM"], "To": to, "Body": text}, timeout=20)
    if r.status_code >= 300: raise RuntimeError(f"SMS provider refused the message ({r.status_code})")
