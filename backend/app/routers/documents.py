import uuid, re
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import STORAGE_DIR
from ..db import get_db
from ..security import require
from ..ocr import get_ocr
from .. import models, audit
from .crud import row

router = APIRouter(prefix="/api/documents", tags=["documents"])
ALLOWED = {".jpg", ".jpeg", ".png", ".pdf", ".webp", ".csv"}
MAX_MB = 15

@router.post("/scan", status_code=201)
async def scan(file: UploadFile = File(...), doc_type: str = Form("receipt"), location_id: int | None = Form(None),
               db: Session = Depends(get_db), u=Depends(require("documents"))):
    """Stores the ORIGINAL file in object storage, runs OCR, saves extracted fields for human review."""
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED: raise HTTPException(415, f"File type {ext or '?'} not allowed")
    data = await file.read()
    if len(data) > MAX_MB * 1024 * 1024: raise HTTPException(413, "File too large")
    key = f"{doc_type}/{uuid.uuid4().hex}{ext}"
    path = STORAGE_DIR / key; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    try: extracted = get_ocr().extract(data, file.filename)
    except Exception as e: extracted = {"error": str(e), "confidence": 0}
    doc = models.Document(doc_type=doc_type, filename=re.sub(r"[^\w.\- ]", "_", file.filename), storage_key=key, extracted=extracted, location_id=location_id)
    db.add(doc); db.flush(); audit.log(db, u, "upload", "document", doc.id, None, {"key": key}); db.commit()
    return row(doc)

@router.get("")
def docs(status: str | None = None, db: Session = Depends(get_db), u=Depends(require("documents"))):
    q = select(models.Document).order_by(models.Document.id.desc())
    if status: q = q.where(models.Document.status == status)
    return [row(d) for d in db.scalars(q)]

@router.get("/{id}/file")
def file(id: int, db: Session = Depends(get_db), u=Depends(require("documents"))):
    d = db.get(models.Document, id)
    if not d: raise HTTPException(404)
    return FileResponse(STORAGE_DIR / d.storage_key, filename=d.filename)
