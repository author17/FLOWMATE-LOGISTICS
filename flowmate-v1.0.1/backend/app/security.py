import hashlib, hmac, os, jwt, base64, struct, time, secrets
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .config import SECRET_KEY, TOKEN_HOURS, ENV, DEMO_MODE, REQUIRE_MFA_ROLES
from .db import get_db
from . import models
from .tenancy import get_setting

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return salt.hex() + "$" + h.hex()

def verify_password(pw: str, stored: str) -> bool:
    salt, h = stored.split("$")
    test = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    return hmac.compare_digest(test, h)

def make_token(user: models.User) -> str:
    return jwt.encode({"sub": str(user.id), "tv": user.token_version or 0, "exp": datetime.utcnow() + timedelta(hours=TOKEN_HOURS)}, SECRET_KEY, algorithm="HS256")

MFA_EXEMPT = ("/api/auth/", "/api/config", "/api/settings")

def mfa_policy(db: Session) -> str:
    """The owner chooses in Settings: 'optional' (default) or 'required' (for the roles in REQUIRE_MFA_ROLES)."""
    v = get_setting(db, "mfa_policy", "optional")
    return v if v in ("optional", "required") else "optional"

def mfa_required(user, db: Session) -> bool:
    return ENV == "production" and not DEMO_MODE and user.role in REQUIRE_MFA_ROLES and not user.totp_enabled and mfa_policy(db) == "required"

def current_user(request: Request, token: str = Depends(oauth2), db: Session = Depends(get_db)) -> models.User:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"]); uid = int(data["sub"])
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(models.User, uid)
    if not user or not user.active or data.get("tv", 0) != (user.token_version or 0):
        raise HTTPException(401, "Session ended - please log in again")
    biz = db.get(models.Business, user.business_id) if user.business_id else None
    if not biz or not biz.active: raise HTTPException(401, "This business account is closed")
    db.info["business_id"] = user.business_id      # from here on every query on this session is limited to this business
    if mfa_required(user, db) and not request.url.path.startswith(MFA_EXEMPT):
        raise HTTPException(403, "MFA_SETUP_REQUIRED")
    return user

# ---- TOTP (RFC 6238): works with Google Authenticator, Microsoft Authenticator, Authy, 1Password ...
def new_totp_secret() -> str: return base64.b32encode(os.urandom(20)).decode().rstrip("=")

def totp_code(secret: str, t: float | None = None, step: int = 30) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8)); counter = int((t or time.time()) // step)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest(); o = h[-1] & 15
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7fffffff) % 1000000:06d}"

def totp_ok(secret: str, code: str) -> bool:
    code = (code or "").strip().replace(" ", "")
    return any(hmac.compare_digest(totp_code(secret, time.time() + d * 30), code) for d in (-1, 0, 1))

# Role permissions per area. "owner" and "admin" can do everything.
PERMS = {
    "owner": {"*"}, "admin": {"*"},
    "manager": {"orders", "customers", "suppliers", "products", "stock", "invoices", "expenses", "documents", "shifts", "reports", "banking_read", "purchase", "delivery", "memberships", "assistant", "stock_read"},
    "employee": {"orders", "documents", "shifts", "stock_read", "delivery", "memberships", "assistant_basic"},
    "driver": {"delivery", "documents"},
    "accountant": {"invoices", "expenses", "reports", "banking_read", "documents", "assistant", "stock_read"},
    "bank_payment": {"invoices", "banking_read", "payments"},
}

def require(area: str):
    def dep(user: models.User = Depends(current_user)):
        p = PERMS.get(user.role, set())
        if "*" in p or area in p:
            return user
        raise HTTPException(403, f"Role '{user.role}' cannot access '{area}'")
    return dep


# Staff with these roles only see/create data for their own location (if the user has one assigned).
SCOPED_ROLES = {"employee", "driver"}
def scope_location(user, requested):
    """Returns the location a request should use: the user's own for scoped roles, otherwise what was asked for."""
    if user.role in SCOPED_ROLES and user.location_id: return user.location_id
    return requested
