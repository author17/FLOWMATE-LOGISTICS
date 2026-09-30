import csv, io
from datetime import date, timedelta
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import require
from .. import models
from .crud import row

router = APIRouter(prefix="/api", tags=["reports"])
REVENUE = ("COMPLETED", "PAID", "PROCESSING", "NEW")

def _sum(db, col, *where): return db.scalar(select(func.coalesce(func.sum(col), 0)).where(*where)) or 0

@router.get("/dashboard")
def dashboard(location_id: int | None = None, db: Session = Depends(get_db), u=Depends(require("reports"))):
    today, m0 = date.today(), date.today().replace(day=1)
    O, E, I = models.Order, models.Expense, models.Invoice
    of = [O.location_id == location_id] if location_id else []
    ef = [E.location_id == location_id] if location_id else []
    sales_today = _sum(db, O.total_cents, func.date(O.created_at) == today.isoformat(), O.status != "CANCELLED", *of)
    sales_month = _sum(db, O.total_cents, func.date(O.created_at) >= m0.isoformat(), O.status != "CANCELLED", *of)
    exp_today = _sum(db, E.amount_cents, E.spent_on == today, *ef)
    exp_month = _sum(db, E.amount_cents, E.spent_on >= m0, *ef)
    unpaid = db.execute(select(func.count(), func.coalesce(func.sum(I.total_cents), 0)).where(I.status != "PAID")).one()
    low = db.scalar(select(func.count()).select_from(models.Stock).join(models.Product, models.Stock.product_id == models.Product.id).where(models.Stock.quantity <= models.Product.min_stock))
    bal = _sum(db, models.BankAccount.balance_cents)
    recent = [row(t) for t in db.scalars(select(models.BankTransaction).order_by(models.BankTransaction.booked_on.desc()).limit(8))]
    by_loc = []
    for l in db.scalars(select(models.Location)):
        s = _sum(db, O.total_cents, func.date(O.created_at) >= m0.isoformat(), O.status != "CANCELLED", O.location_id == l.id)
        e = _sum(db, E.amount_cents, E.spent_on >= m0, E.location_id == l.id)
        by_loc.append({"location": l.name, "sales_cents": s, "expenses_cents": e, "profit_cents": s - e})
    return {"sales_today_cents": sales_today, "expenses_today_cents": exp_today, "sales_month_cents": sales_month, "expenses_month_cents": exp_month,
            "profit_estimate_month_cents": sales_month - exp_month, "unpaid_invoices": unpaid[0], "unpaid_total_cents": unpaid[1], "low_stock_items": low,
            "bank_balance_cents": bal, "orders_waiting": db.scalar(select(func.count()).select_from(O).where(O.status.in_(["NEW", "PROCESSING"]))),
            "documents_to_verify": db.scalar(select(func.count()).select_from(models.Document).where(models.Document.status == "NEEDS_REVIEW")),
            "unmatched_payments": db.scalar(select(func.count()).select_from(models.BankTransaction).where(models.BankTransaction.match_status != "RECONCILED")),
            "deliveries_active": db.scalar(select(func.count()).select_from(models.Delivery).where(models.Delivery.status.in_(["PREPARED", "ON_THE_WAY"]))),
            "deliveries_failed": db.scalar(select(func.count()).select_from(models.Delivery).where(models.Delivery.status == "FAILED")),
            "recent_transactions": recent, "by_location": by_loc}

@router.get("/notifications")
def notes(db: Session = Depends(get_db), u=Depends(require("reports"))):
    return [row(n) for n in db.scalars(select(models.Notification).order_by(models.Notification.id.desc()).limit(50))]

@router.get("/audit")
def audit_log(limit: int = 200, db: Session = Depends(get_db), u=Depends(require("reports"))):
    return [row(a) for a in db.scalars(select(models.AuditLog).order_by(models.AuditLog.id.desc()).limit(min(limit, 1000)))]

EXPORTS = {"orders": models.Order, "invoices": models.Invoice, "expenses": models.Expense, "suppliers": models.Supplier, "customers": models.Customer,
           "products": models.Product, "bank_transactions": models.BankTransaction, "shifts": models.Shift, "payments": models.PaymentRequest, "deliveries": models.Delivery}

@router.get("/export/{name}.csv")
def export(name: str, db: Session = Depends(get_db), u=Depends(require("reports"))):
    """Data ownership: every table can be exported to CSV (opens in Excel)."""
    model = EXPORTS[name]
    buf = io.StringIO(); w = csv.writer(buf)
    cols = [c.name for c in model.__table__.columns]; w.writerow(cols)
    for o in db.scalars(select(model)): w.writerow([getattr(o, c) for c in cols])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={name}.csv"})
