from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import require
from ..banking.csv_provider import parse_csv
from ..services import matching, payments
from .. import models, audit
from .crud import row

router = APIRouter(prefix="/api", tags=["banking"])

class AccountIn(BaseModel): name: str; iban: str | None = None; provider: str = "csv"; balance_cents: int = 0; location_id: int | None = None

@router.get("/bank/accounts")
def accounts(db: Session = Depends(get_db), u=Depends(require("banking_read"))):
    return [row(a) for a in db.scalars(select(models.BankAccount))]

@router.post("/bank/accounts", status_code=201)
def add_account(d: AccountIn, db: Session = Depends(get_db), u=Depends(require("banking_admin"))):
    a = models.BankAccount(**d.model_dump()); db.add(a); db.flush(); audit.log(db, u, "create", "bank_account", a.id); db.commit(); return row(a)

@router.post("/bank/accounts/{id}/import-csv")
async def import_csv(id: int, file: UploadFile = File(...), db: Session = Depends(get_db), u=Depends(require("banking_admin"))):
    acc = db.get(models.BankAccount, id)
    if not acc: raise HTTPException(404)
    try: raw = parse_csv((await file.read()).decode("utf-8-sig"))
    except Exception as e: raise HTTPException(422, f"Could not read CSV: {e}")
    have = {t for t in db.scalars(select(models.BankTransaction.external_id).where(models.BankTransaction.account_id == id))}
    added = 0
    for r in raw:
        if r.external_id in have: continue
        db.add(models.BankTransaction(account_id=id, external_id=r.external_id, booked_on=r.booked_on, amount_cents=r.amount_cents, reference=r.reference, counterparty=r.counterparty))
        have.add(r.external_id); added += 1
    audit.log(db, u, "import_csv", "bank_account", id, None, {"added": added, "skipped_duplicates": len(raw) - added}); db.commit()
    return {"added": added, "skipped_duplicates": len(raw) - added, "matching": matching.run_matching(db, u)}

@router.get("/bank/transactions")
def txs(status: str | None = None, db: Session = Depends(get_db), u=Depends(require("banking_read"))):
    q = select(models.BankTransaction).order_by(models.BankTransaction.booked_on.desc(), models.BankTransaction.id.desc())
    if status: q = q.where(models.BankTransaction.match_status == status)
    out = []
    for t in db.scalars(q):
        m = db.scalar(select(models.PaymentMatch).where(models.PaymentMatch.transaction_id == t.id).order_by(models.PaymentMatch.id.desc()))
        out.append({**row(t), "match": row(m) if m else None})
    return out

@router.post("/bank/match/run")
def run(db: Session = Depends(get_db), u=Depends(require("banking_admin"))): return matching.run_matching(db, u)

class ManualMatch(BaseModel): target_type: str; target_id: int

@router.post("/bank/transactions/{id}/match")
def manual(id: int, d: ManualMatch, db: Session = Depends(get_db), u=Depends(require("banking_admin"))):
    t = db.get(models.BankTransaction, id)
    if not t: raise HTTPException(404)
    if d.target_type not in ("order", "invoice"): raise HTTPException(422, "target_type must be order or invoice")
    if not db.get(models.Order if d.target_type == "order" else models.Invoice, d.target_id): raise HTTPException(404, "Target not found")
    matching.apply_match(db, t, d.target_type, d.target_id, 100, "manual", u); db.commit(); return row(t)

@router.post("/bank/transactions/{id}/confirm")
def confirm(id: int, db: Session = Depends(get_db), u=Depends(require("banking_admin"))):
    t = db.get(models.BankTransaction, id)
    m = db.scalar(select(models.PaymentMatch).where(models.PaymentMatch.transaction_id == id, models.PaymentMatch.confirmed == False).order_by(models.PaymentMatch.id.desc()))
    if not t or not m: raise HTTPException(404, "No suggestion to confirm")
    m.confirmed = True; t.match_status = "RECONCILED"
    tgt = db.get(models.Order if m.target_type == "order" else models.Invoice, m.target_id); tgt.status = "PAID"
    if m.target_type == "invoice": tgt.paid_on, tgt.paid_method = t.booked_on, "BANK_TRANSFER"; payments.complete_by_statement(db, tgt.id, u)
    audit.log(db, u, "confirm_match", "bank_transaction", id, None, {"target": m.target_type, "id": m.target_id}); db.commit(); return row(t)

# ---------- payments (outgoing) ----------
@router.get("/payments")
def pays(db: Session = Depends(get_db), u=Depends(require("banking_read"))):
    out = []
    for p in db.scalars(select(models.PaymentRequest).order_by(models.PaymentRequest.id.desc())):
        i = db.get(models.Invoice, p.invoice_id); s = db.get(models.Supplier, i.supplier_id) if i else None; by = db.get(models.User, p.created_by)
        out.append({**row(p), "invoice_number": i.number if i else "", "supplier": s.name if s else "", "prepared_by": by.name if by else ""})
    return out

class PayIn(BaseModel): invoice_id: int; account_id: int

@router.post("/payments", status_code=201)
def pay(d: PayIn, db: Session = Depends(get_db), u=Depends(require("payments"))):
    """Prepare a supplier payment (waits for the owner's approval)."""
    inv, acc = db.get(models.Invoice, d.invoice_id), db.get(models.BankAccount, d.account_id)
    if not inv or not acc: raise HTTPException(404)
    pr = payments.prepare_payment(db, inv, acc, u); db.commit(); return row(pr)

@router.post("/payments/{id}/approve")
def approve(id: int, db: Session = Depends(get_db), u=Depends(require("payments_approve"))):
    pr = db.get(models.PaymentRequest, id)
    if not pr: raise HTTPException(404)
    payments.approve_payment(db, pr, u); db.commit(); return row(pr)

class Why(BaseModel): reason: str = ""

@router.post("/payments/{id}/reject")
def reject(id: int, d: Why, db: Session = Depends(get_db), u=Depends(require("payments_approve"))):
    pr = db.get(models.PaymentRequest, id)
    if not pr: raise HTTPException(404)
    payments.reject_payment(db, pr, u, d.reason); db.commit(); return row(pr)

@router.post("/payments/{id}/refresh")
def refresh(id: int, db: Session = Depends(get_db), u=Depends(require("payments"))):
    pr = db.get(models.PaymentRequest, id)
    if not pr: raise HTTPException(404)
    payments.refresh(db, pr, u); db.commit(); return row(pr)
