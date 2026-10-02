"""Profiles (supplier/customer), invoice details + manual paid, scan suggestions, refunds, bank classification, accounting ledger."""
import difflib, re
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import require
from .. import models, audit
from .crud import row
from .operations import adjust_stock

router = APIRouter(prefix="/api", tags=["finance"])
norm = lambda s: re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()
def best(name, candidates, cutoff=0.6):
    n = norm(name); scored = [(difflib.SequenceMatcher(None, n, norm(c[1])).ratio() + (0.25 if n and (n in norm(c[1]) or norm(c[1]) in n) else 0), c[0]) for c in candidates]
    scored = [x for x in scored if x[0] >= cutoff]; return max(scored)[1] if scored else None

# ---------------- supplier / customer profiles ----------------
@router.get("/suppliers/{id}/profile")
def supplier_profile(id: int, db: Session = Depends(get_db), u=Depends(require("invoices"))):
    s = db.get(models.Supplier, id)
    if not s: raise HTTPException(404)
    invs = db.scalars(select(models.Invoice).where(models.Invoice.supplier_id == id).order_by(models.Invoice.issue_date.desc())).all()
    pays = db.scalars(select(models.PaymentRequest).where(models.PaymentRequest.invoice_id.in_([i.id for i in invs] or [0])).order_by(models.PaymentRequest.id.desc())).all()
    unpaid = [i for i in invs if i.status != "PAID"]; paid = [i for i in invs if i.status == "PAID" and i.paid_on]
    last = max(paid, key=lambda i: i.paid_on) if paid else None
    docs = db.scalars(select(models.Document).where(models.Document.id.in_([i.document_id for i in invs if i.document_id] or [0]))).all()
    prods = db.scalars(select(models.Product).where(models.Product.supplier_id == id)).all()
    return {"supplier": row(s), "outstanding_cents": sum(i.total_cents for i in unpaid), "pending_invoices": len(unpaid), "last_payment": {"amount_cents": last.total_cents, "date": str(last.paid_on)} if last else None,
            "invoices": [{**row(i)} for i in invs], "payments": [row(p) for p in pays], "documents": [row(d) | {"extracted": None} for d in docs], "products": [row(p) for p in prods]}

@router.get("/customers/{id}/profile")
def customer_profile(id: int, db: Session = Depends(get_db), u=Depends(require("orders"))):
    c = db.get(models.Customer, id)
    if not c: raise HTTPException(404)
    orders = db.scalars(select(models.Order).where(models.Order.customer_id == id).order_by(models.Order.id.desc())).all()
    refunds = sum(db.scalar(select(func.coalesce(func.sum(models.Refund.amount_cents), 0)).where(models.Refund.order_id == o.id)) or 0 for o in orders)
    owed = sum(o.total_cents for o in orders if o.status in ("NEW", "PROCESSING", "COMPLETED")); paid = sum(o.total_cents for o in orders if o.status == "PAID")
    return {"customer": row(c), "orders": [{**row(o), "items": [row(i) for i in o.items]} for o in orders], "paid_cents": paid - refunds, "owed_cents": owed, "refunded_cents": refunds}

# ---------------- invoices: detail, manual paid, suggestions ----------------
@router.get("/invoices/{id}")
def invoice_detail(id: int, db: Session = Depends(get_db), u=Depends(require("invoices"))):
    i = db.get(models.Invoice, id)
    if not i: raise HTTPException(404)
    s = db.get(models.Supplier, i.supplier_id)
    return {**row(i), "supplier": row(s) if s else None, "items": [row(x) for x in i.items], "document": (row(db.get(models.Document, i.document_id)) | {"extracted": None}) if i.document_id else None,
            "payments": [row(p) for p in db.scalars(select(models.PaymentRequest).where(models.PaymentRequest.invoice_id == id))]}

class MarkPaid(BaseModel): method: str = "BANK_TRANSFER"; paid_on: date | None = None; note: str = ""

@router.post("/invoices/{id}/mark-paid")
def mark_paid(id: int, d: MarkPaid, db: Session = Depends(get_db), u=Depends(require("invoices"))):
    """For invoices paid outside the app (cash, or from the bank's own app). Not used for bank-initiated payments."""
    i = db.get(models.Invoice, id)
    if not i: raise HTTPException(404)
    if i.status == "PAID": raise HTTPException(409, "Already paid")
    if db.scalar(select(models.PaymentRequest).where(models.PaymentRequest.invoice_id == id, models.PaymentRequest.status.in_(["AUTHORIZATION_REQUIRED", "PROCESSING", "PENDING_APPROVAL"]))): raise HTTPException(409, "A bank payment is in progress for this invoice")
    i.status, i.paid_on, i.paid_method = "PAID", d.paid_on or date.today(), d.method
    audit.log(db, u, "invoice_marked_paid", "invoice", id, {"status": "UNPAID"}, {"method": d.method, "note": d.note}); db.commit(); return row(i)

class SuggestIn(BaseModel): supplier: str = ""; items: list[dict] = []

@router.post("/scan/suggest")
def suggest(d: SuggestIn, db: Session = Depends(get_db), u=Depends(require("documents"))):
    """Turns OCR text into suggestions: which supplier, which products. The user confirms - nothing is saved here."""
    sup = best(d.supplier, [(s.id, s.name) for s in db.scalars(select(models.Supplier))])
    prods = [(p.id, p.name) for p in db.scalars(select(models.Product))]
    return {"supplier_id": sup, "items": [{"description": it.get("description", ""), "quantity": it.get("quantity") or 1, "unit_price": it.get("unit_price") or 0, "product_id": best(it.get("description", ""), prods, 0.55)} for it in d.items]}

# ---------------- refunds ----------------
class RefundIn(BaseModel): amount_cents: int; reason: str = ""; restock: bool = False

@router.post("/orders/{id}/refund", status_code=201)
def refund(id: int, d: RefundIn, db: Session = Depends(get_db), u=Depends(require("orders"))):
    o = db.get(models.Order, id)
    if not o: raise HTTPException(404)
    if o.status != "PAID": raise HTTPException(409, "Only paid orders can be refunded")
    done = db.scalar(select(func.coalesce(func.sum(models.Refund.amount_cents), 0)).where(models.Refund.order_id == id)) or 0
    if d.amount_cents <= 0 or d.amount_cents > o.total_cents - done: raise HTTPException(422, f"Refund must be between 0.01 and {(o.total_cents - done) / 100:.2f} EUR")
    method = o.payment_method
    if method == "ONLINE":
        from ..services import stripe_service as st
        op = db.scalar(select(models.OnlinePayment).where(models.OnlinePayment.target_type == "order", models.OnlinePayment.target_id == id, models.OnlinePayment.status == "PAID"))
        if op and op.payment_intent and st.configured(db):
            try: st.refund(db, op.payment_intent, d.amount_cents)
            except Exception as e: raise HTTPException(502, f"Stripe refused the refund: {e}")
        else: raise HTTPException(409, "Online payment details not found - refund it in the Stripe dashboard, then record it as CASH/OTHER here")
    r = models.Refund(order_id=id, amount_cents=d.amount_cents, reason=d.reason, method=method, created_by=u.id); db.add(r)
    if done + d.amount_cents == o.total_cents:
        o.status = "REFUNDED"
        if d.restock:
            for it in o.items:
                if it.product_id: adjust_stock(db, it.product_id, o.location_id, it.quantity, "adjustment", f"REFUND-ORDER-{o.id}")
    db.flush(); audit.log(db, u, "refund", "order", id, None, {"amount_cents": d.amount_cents, "reason": d.reason, "method": method}); audit.notify(db, "refund", f"Refund {d.amount_cents/100:.2f} EUR on order #{id}")
    db.commit(); return row(r)

# ---------------- bank: classify unmatched lines ----------------
class Classify(BaseModel): category: str; expense_category: str | None = None; description: str | None = None; location_id: int | None = None

@router.post("/bank/transactions/{id}/classify")
def classify(id: int, d: Classify, db: Session = Depends(get_db), u=Depends(require("banking_admin"))):
    t = db.get(models.BankTransaction, id)
    if not t: raise HTTPException(404)
    if t.match_status == "RECONCILED": raise HTTPException(409, "Already reconciled")
    cat = d.category.upper()
    if cat in ("EXPENSE", "BANK_FEE"):
        if t.amount_cents >= 0: raise HTTPException(422, "Only money going out can be an expense or bank fee")
        e = models.Expense(category="Bank fees" if cat == "BANK_FEE" else (d.expense_category or "Other"), description=d.description or t.reference or t.counterparty, amount_cents=-t.amount_cents,
                           spent_on=t.booked_on, payment_method="BANK_TRANSFER", location_id=d.location_id); db.add(e); db.flush(); t.expense_id = e.id
        db.add(models.PaymentMatch(transaction_id=id, target_type="expense", target_id=e.id, confidence=100, confirmed=True, reason="classified by user"))
    elif cat == "OTHER_INCOME":
        if t.amount_cents <= 0: raise HTTPException(422, "Only money coming in can be other income")
    elif cat not in ("TRANSFER", "REFUND"): raise HTTPException(422, "Unknown category")
    t.category, t.match_status = cat, "RECONCILED"
    audit.log(db, u, "classify_bank_line", "bank_transaction", id, None, {"category": cat}); db.commit(); return row(t)

# ---------------- accounting records (journal) ----------------
def ledger(db, a: date, b: date, loc=None):
    names = {l.id: l.name for l in db.scalars(select(models.Location))}; out = []
    def add(d, typ, desc, amt, vat=0, loc_id=None, ref=""):
        if loc and loc_id != loc: return
        out.append([str(d), typ, desc, names.get(loc_id, ""), round(amt / 100, 2), round(vat / 100, 2), ref])
    for o in db.scalars(select(models.Order).where(models.Order.status.notin_(["CANCELLED"]), models.Order.created_at >= a, models.Order.created_at < datetime.combine(b, datetime.max.time()))):
        vat = 0
        for it in o.items:
            p = db.get(models.Product, it.product_id) if it.product_id else None; rate = p.vat_percent if p else 19; vat += round(it.unit_cents * it.quantity * rate / (100 + rate))
        add(o.created_at.date(), "INCOME", f"Order #{o.id} ({o.payment_method})", o.total_cents, 0, o.location_id, f"ORDER-{o.id}")
        add(o.created_at.date(), "VAT", f"Output VAT on order #{o.id}", vat, vat, o.location_id, f"ORDER-{o.id}")
    for p in db.scalars(select(models.SubPayment).where(models.SubPayment.paid_on >= a, models.SubPayment.paid_on <= b)): add(p.paid_on, "INCOME", f"Membership payment ({p.method})", p.amount_cents, 0, p.location_id, f"SUB-{p.subscription_id}")
    for e in db.scalars(select(models.Expense).where(models.Expense.spent_on >= a, models.Expense.spent_on <= b)):
        add(e.spent_on, "BANK_FEE" if e.category == "Bank fees" else "EXPENSE", f"{e.category}: {e.description}", -e.amount_cents, 0, e.location_id, f"EXP-{e.id}")
        if e.vat_cents: add(e.spent_on, "VAT", f"Input VAT on expense #{e.id}", -e.vat_cents, -e.vat_cents, e.location_id, f"EXP-{e.id}")
    for i in db.scalars(select(models.Invoice).where(models.Invoice.issue_date >= a, models.Invoice.issue_date <= b)):
        s = db.get(models.Supplier, i.supplier_id)
        add(i.issue_date, "EXPENSE", f"Supplier invoice {i.number} - {s.name if s else ''}", -i.total_cents, 0, i.location_id, f"INV-{i.number}")
        if i.vat_cents: add(i.issue_date, "VAT", f"Input VAT on invoice {i.number}", -i.vat_cents, -i.vat_cents, i.location_id, f"INV-{i.number}")
    for i in db.scalars(select(models.Invoice).where(models.Invoice.paid_on >= a, models.Invoice.paid_on <= b)):
        s = db.get(models.Supplier, i.supplier_id); add(i.paid_on, "PAYMENT", f"Paid invoice {i.number} - {s.name if s else ''} ({i.paid_method})", -i.total_cents, 0, i.location_id, f"INV-{i.number}")
    for r in db.scalars(select(models.Refund).where(models.Refund.created_at >= a, models.Refund.created_at < datetime.combine(b, datetime.max.time()))):
        o = db.get(models.Order, r.order_id); add(r.created_at.date(), "REFUND", f"Refund on order #{r.order_id}: {r.reason}", -r.amount_cents, 0, o.location_id if o else None, f"ORDER-{r.order_id}")
    for t in db.scalars(select(models.BankTransaction).where(models.BankTransaction.booked_on >= a, models.BankTransaction.booked_on <= b, models.BankTransaction.category.in_(["TRANSFER", "OTHER_INCOME", "REFUND"]))):
        add(t.booked_on, {"TRANSFER": "TRANSFER", "OTHER_INCOME": "INCOME", "REFUND": "REFUND"}[t.category], f"Bank: {t.reference or t.counterparty}", t.amount_cents, 0, None, f"BANK-{t.id}")
    return sorted(out, key=lambda r: (r[0], r[1]))
