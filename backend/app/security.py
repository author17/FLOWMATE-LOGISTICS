import hashlib, hmac, os, jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .config import SECRET_KEY, TOKEN_HOURS
from .db import get_db
from . import models

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
    return jwt.encode({"sub": str(user.id), "exp": datetime.utcnow() + timedelta(hours=TOKEN_HOURS)}, SECRET_KEY, algorithm="HS256")

def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> models.User:
    try:
        uid = int(jwt.decode(token, SECRET_KEY, algorithms=["HS256"])["sub"])
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(models.User, uid)
    if not user or not user.active:
        raise HTTPException(401, "User disabled")
    return user

# Role permissions per area. "owner" and "admin" can do everything.
PERMS = {
    "owner": {"*"}, "admin": {"*"},
    "manager": {"orders", "customers", "suppliers", "products", "stock", "invoices", "expenses", "documents", "shifts", "reports", "banking_read", "purchase", "delivery"},
    "employee": {"orders", "documents", "shifts", "stock_read", "delivery"},
    "driver": {"delivery", "documents"},
    "accountant": {"invoices", "expenses", "reports", "banking_read", "documents"},
    "bank_payment": {"invoices", "banking_read", "payments"},
}

def require(area: str):
    def dep(user: models.User = Depends(current_user)):
        p = PERMS.get(user.role, set())
        if "*" in p or area in p:
            return user
        raise HTTPException(403, f"Role '{user.role}' cannot access '{area}'")
    return dep
