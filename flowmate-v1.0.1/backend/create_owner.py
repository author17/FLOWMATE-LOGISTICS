"""PRODUCTION setup: creates the tables, the locations and ONE real owner account. No demo data.
Usage:  python create_owner.py "Owner Name" owner@email.com "Temp password 10+ chars" "Main:shop"
The owner is forced to change the password at first login."""
import sys
from app.db import engine, Base, SessionLocal
from app import models
from app.security import hash_password

def main(name, email, pw, locs):
    if len(pw) < 10: sys.exit("Password must be at least 10 characters")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(models.User).first(): sys.exit("Database already has users - nothing done.")
        from app.tenancy import use_business
        import secrets
        b = models.Business(name="My business", slug="main", kind="general", inbound_token=secrets.token_urlsafe(24)); db.add(b); db.flush(); use_business(db, b.id)
        for item in locs.split(","):
            n, _, k = item.partition(":"); db.add(models.Location(name=n.strip(), kind=(k or "cafe").strip()))
        db.add(models.User(name=name, email=email.strip().lower(), password_hash=hash_password(pw), role="owner", must_change_password=True))
        db.add(models.BankAccount(name="Main bank account", provider="csv"))
        db.commit()
    print("Owner created. Log in and you will be asked to choose a new password.")

if __name__ == "__main__":
    if len(sys.argv) != 5: sys.exit(__doc__)
    main(*sys.argv[1:])
