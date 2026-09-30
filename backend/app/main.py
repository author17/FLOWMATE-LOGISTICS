from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .config import CORS_ORIGINS, ENV, DEMO_MODE
from .db import engine, Base
from .routers import auth, crud, operations, documents, shifts, banking, reports, delivery

Base.metadata.create_all(engine)
app = FastAPI(title="FLOWMATE", version="0.3", docs_url=None if ENV == "production" else "/docs", redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
for r in [auth.router, *crud.routers, operations.router, documents.router, shifts.router, delivery.router, banking.router, reports.router]:
    app.include_router(r)

@app.middleware("http")
async def security_headers(request, call_next):
    r = await call_next(request)
    r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin",
                      "Strict-Transport-Security": "max-age=31536000"} if ENV == "production" else {"X-Content-Type-Options": "nosniff"})
    return r

@app.get("/api/config")
def config(): return {"demo": DEMO_MODE}

@app.get("/api/health")
def health(): return {"ok": True}

# serve the built React app (frontend/dist) if present
dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="web")
