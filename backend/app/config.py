import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
ENV = os.getenv("ENV", "development")  # set ENV=production on the server
_db = os.getenv("DATABASE_URL", f"sqlite:///{BASE/'bizops.db'}")
# hosting providers often give postgres:// or postgresql:// - SQLAlchemy needs the psycopg driver name
DATABASE_URL = _db.replace("postgres://", "postgresql+psycopg://", 1).replace("postgresql://", "postgresql+psycopg://", 1)
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", BASE.parent / "storage"))
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE-ME-IN-PRODUCTION-dev-only-key-32b")
if ENV == "production" and (len(SECRET_KEY) < 32 or "CHANGE-ME" in SECRET_KEY):
    raise RuntimeError("Refusing to start: set SECRET_KEY to a random string of 32+ characters (ENV=production)")
CORS_ORIGINS = [o for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o]
TOKEN_HOURS = 12
OCR_PROVIDER = os.getenv("OCR_PROVIDER", "mock")  # mock | claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"  # practice copy with fake data + banner

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")          # sk_test_... first, sk_live_... later
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")  # whsec_... from the Stripe webhook page
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")  # public https address of this app
