import uuid, re, os, hashlib
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
ALLOWED = {".jpg", ".jpeg", ".png", ".pdf", ".webp", ".csv", ".tif", ".tiff", ".bmp"}   # scanners often produce TIFF/BMP/large PDFs
MAX_MB = int(os.getenv("MAX_UPLOAD_MB", "30"))

MAGIC = {".pdf": (b"%PDF",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",), ".png": (b"\x89PNG",), ".webp": (b"RIFF",), ".bmp": (b"BM",), ".tif": (b"II*\x00", b"MM\x00*"), ".tiff": (b"II*\x00", b"MM\x00*")}

def _looks_right(ext: str, data: bytes) -> bool:
    """The file's first bytes must match its extension (blocks e.g. a program renamed to .pdf). CSV is text, checked loosely."""
    if ext == ".csv": return b"\x00" not in data[:2048]
    m = MAGIC.get(ext); return bool(m) and any(data.startswith(x) for x in m) or (ext == ".pdf" and b"%PDF" in data[:1024])

@router.post("/scan", status_code=201)
async def scan(file: UploadFile = File(...), doc_type: str = Form("receipt"), location_id: int | None = Form(None),
               db: Session = Depends(get_db), u=Depends(require("documents"))):
    """Stores the ORIGINAL file in object storage, runs OCR, saves extracted fields for human review."""
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if doc_type not in {"receipt", "invoice", "statement", "contract", "delivery_note", "purchase_order", "tax_document", "other"}: doc_type = "other"
    if ext not in ALLOWED: raise HTTPException(415, f"File type {ext or '?'} not allowed")
    data = await file.read()
    if len(data) > MAX_MB * 1024 * 1024: raise HTTPException(413, f"File too large ({len(data) // 1048576} MB, limit {MAX_MB} MB). On the scanner choose 200 dpi, grayscale or black & white, and save as PDF or JPEG.")
    if not data: raise HTTPException(422, "The file is empty - the scanner may not have finished saving it. Scan again.")
    if not _looks_right(ext, data): raise HTTPException(415, f"This file is not a real {ext[1:].upper()} (it may be damaged or renamed). Scan it again and save as PDF or JPEG.")
    fhash = hashlib.sha256(data).hexdigest()
    dup = db.scalar(select(models.Document).where(models.Document.file_hash == fhash).order_by(models.Document.id))
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
                          company=(extracted.get("supplier") or None), amount_cents=_c(extracted.get("total")) or None, reference=(extracted.get("number") or None), doc_date=_d(extracted.get("date")), file_hash=fhash)
    db.add(doc); db.flush(); audit.log(db, u, "upload", "document", doc.id, None, {"key": key}); db.commit()
    out = row(doc); out["duplicate_of"] = dup.id if dup else None   # the same file was uploaded before: warn, don't block
    return out

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
    p = STORAGE_DIR / d.storage_key
    if not p.exists(): raise HTTPException(404, "The stored file is missing - it may have been lost with a storage reset. Upload it again.")
    return FileResponse(p, filename=d.filename, content_disposition_type="attachment" if p.suffix.lower() not in (".pdf", ".jpg", ".jpeg", ".png", ".webp") else "inline")
