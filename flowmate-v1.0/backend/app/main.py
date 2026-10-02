from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .config import CORS_ORIGINS, ENV, DEMO_MODE
from .db import engine, Base
from .routers import auth, crud, operations, documents, shifts, banking, reports, delivery, memberships, reports_ext, stripe_router, assistant, finance, openbanking, extras, cockpit, search, accounts, legal

Base.metadata.create_all(engine)
from .migrate import migrate
migrate()
from .migrate import adopt_legacy
adopt_legacy()
from .bootstrap import bootstrap
bootstrap()
app = FastAPI(title="FLOWMATE", version="1.0.0", docs_url=None if ENV == "production" else "/docs", redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
for r in [auth.router, *crud.routers, operations.router, documents.router, shifts.router, delivery.router, memberships.router, banking.router, reports.router, reports_ext.router, stripe_router.router, assistant.router, finance.router, openbanking.router, extras.router, extras.page_router, cockpit.router, search.router, accounts.router, legal.router]:
    app.include_router(r)

from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
@app.exception_handler(PermissionError)
async def _perm(request, exc): return JSONResponse({"detail": "Not found"}, status_code=404)     # never reveal that the other business's record exists
@app.exception_handler(IntegrityError)
async def _integrity(request, exc): return JSONResponse({"detail": "That already exists or refers to something that does not exist"}, status_code=409)

@app.middleware("http")
async def security_headers(request, call_next):
    r = await call_next(request)
    r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin",
                      "Strict-Transport-Security": "max-age=31536000"} if ENV == "production" else {"X-Content-Type-Options": "nosniff"})
    return r

from . import scheduler
@app.on_event("startup")
def _start_jobs(): scheduler.start()

@app.get("/api/config")
def config():
    from .services import sms
    return {"demo": DEMO_MODE, "sms_available": sms.configured()}

@app.get("/api/health")
def health(): return {"ok": True}

# serve the built React app (frontend/dist) if present
dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="web")
