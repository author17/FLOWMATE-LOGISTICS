"""The control-room dashboard: what needs attention, with the action attached; pulses for money, bank and logistics; activity feed."""
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import require, scope_location
from .. import models
from .crud import row
from ..dates import on_day, since, before

router = APIRouter(prefix="/api", tags=["cockpit"])
S = lambda db, col, *w: db.scalar(select(func.coalesce(func.sum(col), 0)).where(*w)) or 0
N = lambda db, model, *w: db.scalar(select(func.count()).select_from(model).where(*w)) or 0

@router.get("/cockpit")
def cockpit(location_id: int | None = None, db: Session = Depends(get_db), u=Depends(require("reports"))):
    location_id = scope_location(u, location_id)
    today, m0 = date.today(), date.today().replace(day=1); prev0 = (m0 - timedelta(days=1)).replace(day=1)
    O, E, I, D, T, SP = models.Order, models.Expense, models.Invoice, models.Delivery, models.BankTransaction, models.SubPayment
    of = [O.location_id == location_id] if location_id else []
    def sales(a, b):
        return S(db, O.total_cents, since(O.created_at, a), before(O.created_at, b), O.status.in_(["PAID", "COMPLETED"]), *of) + S(db, SP.amount_cents, SP.paid_on >= a, SP.paid_on < b) \
               - S(db, models.Refund.amount_cents, since(models.Refund.created_at, a), before(models.Refund.created_at, b))
    tomorrow = today + timedelta(days=1)
    received_m, received_prev = sales(m0, tomorrow), sales(prev0, m0)
    exp_m = S(db, E.amount_cents, E.spent_on >= m0, *([E.location_id == location_id] if location_id else []))
    unpaid_orders = S(db, O.total_cents, O.status.in_(["NEW", "PROCESSING", "COMPLETED"]), *of)
    unpaid = db.execute(select(func.count(), func.coalesce(func.sum(I.total_cents), 0)).where(I.status != "PAID")).one()
    sup_paid = S(db, I.total_cents, I.status == "PAID", I.paid_on >= m0)
    weeks = []
    for k in range(3, -1, -1):
        a = today - timedelta(days=7 * k + 6); b = today - timedelta(days=7 * k - 1)
        weeks.append({"label": f"{a:%d/%m}", "sales_cents": sales(a, b)})

    # ---- bank
    conns = db.scalars(select(models.BankConnection).where(models.BankConnection.status != "DISCONNECTED")).all()
    active = [c for c in conns if c.status == "ACTIVE"]
    todays = [row(t) for t in db.scalars(select(T).where(T.booked_on == today).order_by(T.id.desc()).limit(6))]
    matched_today = db.scalar(select(func.count()).select_from(models.PaymentMatch).join(T, T.id == models.PaymentMatch.transaction_id).where(T.booked_on == today, models.PaymentMatch.confirmed == True)) or 0
    bank = {"connected": bool(active), "institution": active[0].institution if active else None, "balance_cents": S(db, models.BankAccount.balance_cents),
            "needs_renewal": any(c.status in ("EXPIRED", "ERROR") or (c.consent_expires_at and (c.consent_expires_at - datetime.utcnow()).days < 14) for c in conns), "today": todays, "matched_today": matched_today,
            "last_sync": max((c.last_sync_at for c in active if c.last_sync_at), default=None)}

    # ---- logistics
    dl = lambda *w: N(db, D, *w)
    ds = db.scalars(select(D).where(D.status.in_(["PREPARED", "ON_THE_WAY", "FAILED"])).order_by(D.id.desc()).limit(8)).all(); drivers = {x.id: x.name for x in db.scalars(select(models.User))}; phones = {x.id: x.phone for x in db.scalars(select(models.User))}; out_d = []
    for d in ds:
        o = db.get(models.Order, d.order_id); c = db.get(models.Customer, o.customer_id) if o and o.customer_id else None
        out_d.append({**row(d), "customer": c.name if c else "Walk-in", "packages": sum(i.quantity for i in o.items) if o else 0, "driver_name": drivers.get(d.driver_id, ""), "phone": c.phone if c else None, "driver_phone": phones.get(d.driver_id)})
    logistics = {"ready": dl(D.status == "PREPARED"), "in_transit": dl(D.status == "ON_THE_WAY"), "delivered_today": dl(D.status == "DELIVERED", on_day(D.delivered_at, today)),
                 "delayed": dl(D.status == "FAILED") + dl(D.status == "PREPARED", D.scheduled_for < today), "active": out_d}

    # ---- low stock with the action attached
    low = []
    for s, p in db.execute(select(models.Stock, models.Product).join(models.Product, models.Stock.product_id == models.Product.id).where(models.Stock.quantity <= models.Product.min_stock, *([models.Stock.location_id == location_id] if location_id else []))).all()[:12]:
        sup = db.get(models.Supplier, p.supplier_id) if p.supplier_id else None
        low.append({"product_id": p.id, "name": p.name, "quantity": s.quantity, "min_stock": p.min_stock, "location_id": s.location_id, "suggested": max((p.max_stock or p.min_stock * 3) - s.quantity, 1), "supplier_id": p.supplier_id, "supplier": sup.name if sup else None, "last_price_cents": p.purchase_cents})

    # ---- attention list (each with the screen that solves it)
    pend = N(db, models.PaymentRequest, models.PaymentRequest.status == "PENDING")
    verify = N(db, models.Document, models.Document.status == "NEEDS_REVIEW")
    overdue = N(db, I, I.status != "PAID", I.due_date < today)
    suggested = N(db, T, T.match_status == "SUGGESTED"); unmatched = N(db, T, T.match_status == "UNMATCHED")
    ready_orders = logistics["ready"]; failed = N(db, D, D.status == "FAILED")
    att = []
    def add(level, n, text, tab, label):
        if n: att.append({"level": level, "count": n, "text": text, "tab": tab, "action": label})
    add("red", pend, f"{pend} supplier payment(s) awaiting your approval", "Banking", "REVIEW")
    add("red", overdue, f"{overdue} supplier invoice(s) overdue", "Invoices", "PAY")
    add("red", failed, f"{failed} failed delivery(ies)", "Delivery", "FIX")
    add("red", 1 if bank["needs_renewal"] else 0, "Bank access needs renewing", "Settings", "RENEW")
    add("orange", verify, f"{verify} document(s) need verification", "Scan", "OPEN")
    add("orange", len(low), f"{len(low)} product(s) below minimum stock", "Stock", "STOCK")
    add("orange", suggested + unmatched, f"{suggested + unmatched} bank line(s) not matched yet", "Banking", "MATCH")
    add("blue", ready_orders, f"{ready_orders} order(s) ready for delivery", "Delivery", "LOGISTICS")
    add("green", matched_today, f"{matched_today} bank transaction(s) matched automatically today", "Banking", "VIEW")

    # ---- activity feed
    act = [{"kind": n.kind, "message": n.message, "at": str(n.created_at)} for n in db.scalars(select(models.Notification).order_by(models.Notification.id.desc()).limit(12))]
    return {"today": str(today), "attention": att, "low_stock": low, "logistics": logistics, "bank": bank, "activity": act,
            "kpi": {"orders_today": N(db, O, on_day(O.created_at, today), *of), "orders_open": N(db, O, O.status.in_(["NEW", "PROCESSING"]), *of), "received_cents": received_m,
                    "received_change_pct": round((received_m - received_prev) * 100 / received_prev, 1) if received_prev else None, "to_pay_cents": unpaid[1], "to_pay_count": unpaid[0], "stock_alerts": len(low),
                    "deliveries_today": logistics["in_transit"] + logistics["delivered_today"], "deliveries_pending": logistics["ready"]},
            "finance": {"sales_cents": received_m, "expenses_cents": exp_m, "net_cents": received_m - exp_m, "outstanding_cents": unpaid_orders, "supplier_paid_cents": sup_paid, "weeks": weeks}}
