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

# Open Banking (Enable Banking). Either set these here, or the owner pastes them in Settings -> Bank connections.
ENABLEBANKING_APP_ID = os.getenv("ENABLEBANKING_APP_ID", "")
ENABLEBANKING_PRIVATE_KEY = os.getenv("ENABLEBANKING_PRIVATE_KEY", "").replace("\\n", "\n")
BANK_SYNC_HOURS = float(os.getenv("BANK_SYNC_HOURS", "6"))   # 0 turns automatic sync off
DISABLE_SCHEDULER = os.getenv("DISABLE_SCHEDULER", "0") == "1"
REQUIRE_MFA_ROLES = {r.strip() for r in os.getenv("REQUIRE_MFA_ROLES", "owner,admin,bank_payment").split(",") if r.strip()}
SMTP_HOST = os.getenv("SMTP_HOST", ""); SMTP_PORT = int(os.getenv("SMTP_PORT", "587")); SMTP_USER = os.getenv("SMTP_USER", ""); SMTP_PASS = os.getenv("SMTP_PASS", ""); SMTP_FROM = os.getenv("SMTP_FROM", "")
INBOUND_EMAIL_TOKEN = os.getenv("INBOUND_EMAIL_TOKEN", "")
