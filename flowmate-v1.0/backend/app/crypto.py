"""Encrypts secrets stored in the database (provider keys, IBANs). Key is derived from SECRET_KEY: if you change SECRET_KEY, encrypted values can no longer be read."""
import base64, hashlib
from cryptography.fernet import Fernet, InvalidToken
from .config import SECRET_KEY

_f = Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"flowmate-data|" + SECRET_KEY.encode()).digest()))
PREFIX = "enc1:"

def encrypt(text: str | None) -> str | None:
    if not text or text.startswith(PREFIX): return text
    return PREFIX + _f.encrypt(text.encode()).decode()

def decrypt(text: str | None) -> str | None:
    if not text or not text.startswith(PREFIX): return text      # legacy plain value
    try: return _f.decrypt(text[len(PREFIX):].encode()).decode()
    except InvalidToken: return None
