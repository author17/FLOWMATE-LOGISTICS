"""Wipes the PRACTICE database and re-creates fresh demo data. Only runs when DEMO_MODE=1 (never on the real system)."""
import os, sys
if os.getenv("DEMO_MODE") != "1": sys.exit("Refusing: DEMO_MODE is not 1. This script must never touch real data.")
from app.db import engine, Base, SessionLocal
Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
import seed
with SessionLocal() as db: seed.seed(db)
print("Practice data reset.")
