import json
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .. import config, models, audit
from ..db import get_db
from ..security import require
from ..services import stripe_service as st
from .crud import row

router = APIRouter(prefix="/api/stripe", tags=["stripe"])

@router.get("/status")
def status(u=Depends(require("orders"))): return {"configured": st.configured(), "mode": st.mode(), "webhook_configured": bool(config.STRIPE_WEBHOOK_SECRET), "webhook_url": f"{config.APP_BASE_URL}/api/stripe/webhook"}

class CheckoutIn(BaseModel): target_type: str; target_id: int; amount_cents: int | None = None

@router.post("/checkout", status_code=201)
def checkout(d: CheckoutIn, db: Session = Depends(get_db), u=Depends(require("orders"))):
    if not st.configured(): raise HTTPException(422, "Stripe is not set up yet (missing STRIPE_SECRET_KEY)")
    if d.target_type == "order":
        o = db.get(models.Order, d.target_id)
        if not o: raise HTTPException(404, "Order not found")
        if o.status in ("PAID", "CANCELLED"): raise HTTPException(409, f"Order is already {o.status}")
        amount, name = o.total_cents, f"Order #{o.id}"
        c = db.get(models.Customer, o.customer_id) if o.customer_id else None; email = c.email if c else None
    elif d.target_type == "subscription":
        from .memberships import paid
        s = db.get(models.Subscription, d.target_id)
        if not s: raise HTTPException(404, "Subscription not found")
        bal = s.price_cents - paid(db, s.id)
        if bal <= 0: raise HTTPException(409, "Nothing left to pay")
        amount = d.amount_cents or bal
        if amount > bal or amount <= 0: raise HTTPException(422, "Amount must be between 0.01 and the outstanding balance")
        m, p = db.get(models.Member, s.member_id), db.get(models.Plan, s.plan_id); name = f"{p.name} - {m.name}"; email = m.email
    else: raise HTTPException(422, "target_type must be order or subscription")
    if amount < 50: raise HTTPException(422, "Stripe minimum is about 0.50 EUR")
    try: sess = st.create_checkout(amount, name, d.target_type, d.target_id, email)
    except Exception as e: raise HTTPException(502, f"Stripe refused: {e}")
    op = models.OnlinePayment(session_id=sess["id"], target_type=d.target_type, target_id=d.target_id, amount_cents=amount, url=sess["url"], created_by=u.id)
    db.add(op); db.flush(); audit.log(db, u, "create_payment_link", "online_payment", op.id, None, {"target": f"{d.target_type}-{d.target_id}", "amount_cents": amount}); db.commit()
    return {**row(op), "session_id": op.session_id}

@router.get("/payments")
def payments(db: Session = Depends(get_db), u=Depends(require("orders"))):
    return [row(p) for p in db.scalars(select(models.OnlinePayment).order_by(models.OnlinePayment.id.desc()).limit(200))]

@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Called by Stripe. Trusted ONLY if the signature matches our webhook secret."""
    payload = await request.body()
    if not config.STRIPE_WEBHOOK_SECRET or not st.verify_signature(payload, request.headers.get("stripe-signature", ""), config.STRIPE_WEBHOOK_SECRET):
        raise HTTPException(400, "Bad signature")
    ev = json.loads(payload); obj = ev.get("data", {}).get("object", {})
    op = db.scalar(select(models.OnlinePayment).where(models.OnlinePayment.session_id == obj.get("id", "")))
    if not op: return {"ignored": "unknown session"}
    if ev["type"] == "checkout.session.expired" and op.status == "PENDING": op.status = "EXPIRED"
    elif ev["type"] in ("checkout.session.completed", "checkout.session.async_payment_succeeded") and op.status == "PENDING":
        if obj.get("payment_status") != "paid": return {"waiting": True}
        if obj.get("amount_total") != op.amount_cents or obj.get("currency") != "eur":
            op.status = "AMOUNT_MISMATCH"; audit.notify(db, "stripe_mismatch", f"Stripe payment {op.session_id} amount does not match - check manually")
        else:
            op.status, op.paid_at = "PAID", datetime.utcnow()
            if op.target_type == "order":
                o = db.get(models.Order, op.target_id); old = o.status; o.status = "PAID"; o.payment_method = "ONLINE"
                audit.log(db, None, "order_paid_online", "order", o.id, {"status": old}, {"status": "PAID", "stripe": op.session_id}); audit.notify(db, "payment", f"Order #{o.id} paid online")
            else:
                s = db.get(models.Subscription, op.target_id)
                db.add(models.SubPayment(subscription_id=s.id, amount_cents=op.amount_cents, method="ONLINE", location_id=s.location_id))
                audit.log(db, None, "subscription_paid_online", "subscription", s.id, None, {"amount_cents": op.amount_cents, "stripe": op.session_id}); audit.notify(db, "payment", f"Membership payment {op.amount_cents/100:.2f} EUR received online")
    db.commit(); return {"ok": True}
