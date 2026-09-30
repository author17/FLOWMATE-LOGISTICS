from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import require, scope_location
from .. import models, audit
from .crud import row

router = APIRouter(prefix="/api/shifts", tags=["shifts"])

class OpenIn(BaseModel): location_id: int; opening_float_cents: int = 0
class CloseIn(BaseModel):
    cash_sales_cents: int; card_sales_cents: int = 0; cash_expenses_cents: int = 0
    counted_cash_cents: int; z_report_document_id: int | None = None; notes: str | None = None

@router.post("/open", status_code=201)
def open_shift(d: OpenIn, db: Session = Depends(get_db), u=Depends(require("shifts"))):
    if db.scalar(select(models.Shift).where(models.Shift.cashier_id == u.id, models.Shift.status == "OPEN")):
        raise HTTPException(409, "You already have an open shift")
    d.location_id = scope_location(u, d.location_id) or d.location_id
    s = models.Shift(location_id=d.location_id, cashier_id=u.id, opening_float_cents=d.opening_float_cents)
    db.add(s); db.flush(); audit.log(db, u, "open_shift", "shift", s.id); db.commit(); return row(s)

@router.post("/{id}/close")
def close_shift(id: int, d: CloseIn, db: Session = Depends(get_db), u=Depends(require("shifts"))):
    s = db.get(models.Shift, id)
    if not s or s.status != "OPEN": raise HTTPException(404, "No such open shift")
    if s.cashier_id != u.id and u.role not in ("owner", "manager", "admin"): raise HTTPException(403, "Not your shift")
    expected = s.opening_float_cents + d.cash_sales_cents - d.cash_expenses_cents
    for k in ("cash_sales_cents", "card_sales_cents", "cash_expenses_cents", "counted_cash_cents", "z_report_document_id", "notes"): setattr(s, k, getattr(d, k))
    s.difference_cents = d.counted_cash_cents - expected
    s.status, s.closed_at = "CLOSED", datetime.utcnow()
    audit.log(db, u, "close_shift", "shift", s.id, None, {"expected_cents": expected, "counted_cents": d.counted_cash_cents, "difference_cents": s.difference_cents})
    if s.difference_cents != 0:
        audit.notify(db, "cash_difference", f"Shift #{s.id}: cash difference of {s.difference_cents/100:+.2f} EUR at location {s.location_id}")
    db.commit(); return {**row(s), "expected_cash_cents": expected}

@router.get("")
def list_shifts(location_id: int | None = None, db: Session = Depends(get_db), u=Depends(require("shifts"))):
    q = select(models.Shift).order_by(models.Shift.id.desc())
    location_id = scope_location(u, location_id)
    if location_id: q = q.where(models.Shift.location_id == location_id)
    if u.role == "employee": q = q.where(models.Shift.cashier_id == u.id)
    return [row(s) for s in db.scalars(q)]
