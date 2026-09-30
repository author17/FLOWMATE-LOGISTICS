import uuid, re
from datetime import date
from pydantic import BaseModel
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
    if doc_type not in {"receipt", "invoice", "statement", "contract", "delivery_note", "purchase_order", "tax_document", "other"}: doc_type = "other"
    if ext not in ALLOWED: raise HTTPException(415, f"File type {ext or '?'} not allowed")
    data = await file.read()
    if len(data) > MAX_MB * 1024 * 1024: raise HTTPException(413, "File too large")
    key = f"{doc_type}/{uuid.uuid4().hex}{ext}"
    path = STORAGE_DIR / key; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    try: extracted = get_ocr().extract(data, file.filename)
    except Exception as e: extracted = {"error": str(e), "confidence": 0}
    def _c(v):
        try: return round(float(v) * 100)
        except Exception: return None
    def _d(v):
        try: return date.fromisoformat(str(v))
        except Exception: return None
    doc = models.Document(doc_type=doc_type, filename=re.sub(r"[^\w.\- ]", "_", file.filename), storage_key=key, extracted=extracted, location_id=location_id, source="scan",
                          company=(extracted.get("supplier") or None), amount_cents=_c(extracted.get("total")) or None, reference=(extracted.get("number") or None), doc_date=_d(extracted.get("date")))
    db.add(doc); db.flush(); audit.log(db, u, "upload", "document", doc.id, None, {"key": key}); db.commit()
    return row(doc)

@router.get("")
def docs(status: str | None = None, doc_type: str | None = None, q: str | None = None, db: Session = Depends(get_db), u=Depends(require("documents"))):
    qry = select(models.Document).order_by(models.Document.id.desc())
    if status: qry = qry.where(models.Document.status == status)
    if doc_type: qry = qry.where(models.Document.doc_type == doc_type)
    if q: qry = qry.where(models.Document.filename.ilike(f"%{q}%") | models.Document.company.ilike(f"%{q}%") | models.Document.reference.ilike(f"%{q}%"))
    return [row(d) for d in db.scalars(qry)]

DOC_TYPES = {"receipt", "invoice", "statement", "contract", "delivery_note", "purchase_order", "tax_document", "other"}

class DocIn(BaseModel):
    doc_type: str | None = None; company: str | None = None; amount_cents: int | None = None; reference: str | None = None; doc_date: date | None = None
    related_order_id: int | None = None; related_invoice_id: int | None = None; related_transaction_id: int | None = None; status: str | None = None

@router.put("/{id}")
def update_doc(id: int, d: DocIn, db: Session = Depends(get_db), u=Depends(require("documents"))):
    doc = db.get(models.Document, id)
    if not doc: raise HTTPException(404)
    data = d.model_dump(exclude_unset=True)
    if data.get("doc_type") and data["doc_type"] not in DOC_TYPES: raise HTTPException(422, "Unknown document type")
    if data.get("status") and data["status"] not in ("NEEDS_REVIEW", "VERIFIED"): raise HTTPException(422, "Bad status")
    for k, v in data.items(): setattr(doc, k, v)
    audit.log(db, u, "update", "document", id, None, d.model_dump(mode="json", exclude_unset=True)); db.commit(); return row(doc)

@router.get("/{id}/file")
def file(id: int, db: Session = Depends(get_db), u=Depends(require("documents"))):
    d = db.get(models.Document, id)
    if not d: raise HTTPException(404)
    return FileResponse(STORAGE_DIR / d.storage_key, filename=d.filename)
