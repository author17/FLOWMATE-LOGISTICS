"""Delivery: order -> delivery job -> driver -> status -> proof. Completing a delivery completes the order."""
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import require
from .. import models, audit
from .crud import row

router = APIRouter(prefix="/api/deliveries", tags=["delivery"])
NEXT = {"PREPARED": {"ON_THE_WAY", "CANCELLED"}, "ON_THE_WAY": {"DELIVERED", "FAILED"}, "FAILED": {"PREPARED", "CANCELLED"}}

def out(d, db):
    o = db.get(models.Order, d.order_id); drv = db.get(models.User, d.driver_id) if d.driver_id else None
    c = db.get(models.Customer, o.customer_id) if o and o.customer_id else None
    return {**row(d), "order_total_cents": o.total_cents if o else 0, "customer": c.name if c else "", "driver_name": drv.name if drv else ""}

class NewDelivery(BaseModel): order_id: int; address: str = ""; driver_id: int | None = None; scheduled_for: date | None = None
class StatusIn(BaseModel): status: str; reason: str | None = None; proof_document_id: int | None = None
class AssignIn(BaseModel): driver_id: int

@router.get("/drivers")
def drivers(db: Session = Depends(get_db), u=Depends(require("delivery"))):
    return [{"id": x.id, "name": x.name} for x in db.scalars(select(models.User).where(models.User.role == "driver", models.User.active == True))]

@router.get("")
def list_(status: str | None = None, db: Session = Depends(get_db), u=Depends(require("delivery"))):
    q = select(models.Delivery).order_by(models.Delivery.id.desc())
    if status: q = q.where(models.Delivery.status == status)
    if u.role == "driver": q = q.where(models.Delivery.driver_id == u.id)  # drivers see only their own jobs
    return [out(d, db) for d in db.scalars(q)]

@router.post("", status_code=201)
def create(d: NewDelivery, db: Session = Depends(get_db), u=Depends(require("delivery"))):
    if u.role == "driver": raise HTTPException(403, "Drivers cannot create deliveries")
    o = db.get(models.Order, d.order_id)
    if not o: raise HTTPException(404, "Order not found")
    if o.status == "CANCELLED": raise HTTPException(409, "Order is cancelled")
    if db.scalar(select(models.Delivery).where(models.Delivery.order_id == d.order_id)): raise HTTPException(409, "This order already has a delivery")
    x = models.Delivery(**d.model_dump()); db.add(x); db.flush()
    if o.status == "NEW": o.status = "PROCESSING"
    audit.log(db, u, "create", "delivery", x.id, None, d.model_dump(mode="json")); db.commit(); return out(x, db)

@router.put("/{id}/assign")
def assign(id: int, d: AssignIn, db: Session = Depends(get_db), u=Depends(require("delivery"))):
    if u.role == "driver": raise HTTPException(403, "Only staff can assign drivers")
    x = db.get(models.Delivery, id); drv = db.get(models.User, d.driver_id)
    if not x or not drv or drv.role != "driver": raise HTTPException(404, "Delivery or driver not found")
    old = x.driver_id; x.driver_id = d.driver_id
    audit.log(db, u, "assign_driver", "delivery", id, {"driver_id": old}, {"driver_id": d.driver_id}); db.commit(); return out(x, db)

@router.put("/{id}/status")
def status(id: int, d: StatusIn, db: Session = Depends(get_db), u=Depends(require("delivery"))):
    x = db.get(models.Delivery, id)
    if not x: raise HTTPException(404)
    if u.role == "driver" and x.driver_id != u.id: raise HTTPException(403, "Not your delivery")
    if d.status not in NEXT.get(x.status, set()): raise HTTPException(409, f"Cannot go from {x.status} to {d.status}")
    if d.status == "ON_THE_WAY" and not x.driver_id: raise HTTPException(422, "Assign a driver first")
    if d.status == "FAILED" and not d.reason: raise HTTPException(422, "A reason is required for a failed delivery")
    old = x.status; x.status = d.status
    o = db.get(models.Order, x.order_id)
    if d.status == "DELIVERED":
        x.delivered_at = datetime.utcnow(); x.proof_document_id = d.proof_document_id
        if o.status in ("NEW", "PROCESSING"): o.status = "COMPLETED"
        audit.notify(db, "delivery", f"Order #{o.id} delivered")
    if d.status == "FAILED":
        x.failure_reason = d.reason; audit.notify(db, "delivery_failed", f"Delivery for order #{o.id} failed: {d.reason}")
    audit.log(db, u, "delivery_status", "delivery", id, {"status": old}, {"status": d.status, "reason": d.reason}); db.commit(); return out(x, db)
