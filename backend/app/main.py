from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .db import engine, Base
from .routers import auth, crud, operations, documents, shifts, banking, reports, delivery

Base.metadata.create_all(engine)
app = FastAPI(title="FLOWMATE", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
for r in [auth.router, *crud.routers, operations.router, documents.router, shifts.router, delivery.router, banking.router, reports.router]:
    app.include_router(r)

@app.get("/api/health")
def health(): return {"ok": True}

# serve the built React app (frontend/dist) if present
dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="web")
