import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE/'bizops.db'}")  # set to postgresql+psycopg://... for Postgres
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", BASE.parent / "storage"))
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE-ME-IN-PRODUCTION")
TOKEN_HOURS = 12
OCR_PROVIDER = os.getenv("OCR_PROVIDER", "mock")  # mock | claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
