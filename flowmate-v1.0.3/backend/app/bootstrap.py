"""First-start setup for the REAL system: if the database has no users and BOOTSTRAP_* variables are set,
create the locations and the owner account (forced to change password at first login). Does nothing otherwise."""
import os, secrets
from sqlalchemy import select
from . import models
from .db import SessionLocal
from .tenancy import use_business
from .security import hash_password

def bootstrap():
    email, pw, name = os.getenv("BOOTSTRAP_OWNER_EMAIL"), os.getenv("BOOTSTRAP_OWNER_PASSWORD"), os.getenv("BOOTSTRAP_OWNER_NAME", "Owner")
    if not email or not pw: return
    if len(pw) < 10: raise RuntimeError("BOOTSTRAP_OWNER_PASSWORD must be at least 10 characters")
    with SessionLocal() as db:
        if db.scalar(select(models.User).limit(1)): return
        b = models.Business(name=os.getenv("BOOTSTRAP_BUSINESS_NAME", "My business"), slug="main", kind=os.getenv("BOOTSTRAP_KIND", "general"), inbound_token=secrets.token_urlsafe(24)); db.add(b); db.flush()
        use_business(db, b.id)
        for item in os.getenv("BOOTSTRAP_LOCATIONS", "Main:shop").split(","):
            n, _, k = item.partition(":"); db.add(models.Location(name=n.strip(), kind=(k or "cafe").strip()))
        db.add(models.User(name=name, email=email.strip().lower(), password_hash=hash_password(pw), role="owner", must_change_password=True))
        db.add(models.BankAccount(name="Main bank account", provider="csv"))
        db.commit()
        print("Owner account created from BOOTSTRAP variables.")
