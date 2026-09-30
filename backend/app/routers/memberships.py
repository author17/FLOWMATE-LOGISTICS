"""Gym memberships: members, plans (in crud.py), subscriptions, payments, check-in, expiring list."""
from datetime import date, timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import require
from .. import models, audit
from .crud import row

router = APIRouter(prefix="/api", tags=["memberships"])

def paid(db, sub_id): return db.scalar(select(func.coalesce(func.sum(models.SubPayment.amount_cents), 0)).where(models.SubPayment.subscription_id == sub_id)) or 0

def sub_out(db, s):
    p = db.get(models.Plan, s.plan_id); pd = paid(db, s.id); today = date.today()
    state = "CANCELLED" if s.status == "CANCELLED" else "EXPIRED" if s.end_on < today or (s.sessions_left is not None and s.sessions_left <= 0) else "ACTIVE"
    return {**row(s), "plan_name": p.name if p else "", "kind": p.kind if p else "", "paid_cents": pd, "balance_cents": s.price_cents - pd, "state": state,
            "days_left": (s.end_on - today).days}

def member_out(db, m):
    subs = [sub_out(db, s) for s in db.scalars(select(models.Subscription).where(models.Subscription.member_id == m.id).order_by(models.Subscription.end_on.desc()))]
    act = next((s for s in subs if s["state"] == "ACTIVE"), None)
    bal = sum(s["balance_cents"] for s in subs if s["state"] != "CANCELLED")
    return {**row(m), "status": "ACTIVE" if act else ("NO_PLAN" if not subs else "EXPIRED"), "current_plan": act["plan_name"] if act else (subs[0]["plan_name"] if subs else ""),
            "valid_until": (act or (subs[0] if subs else {})).get("end_on"), "balance_cents": bal, "subscriptions": subs}

class MemberIn(BaseModel): name: str; phone: str | None = None; email: str | None = None; location_id: int | None = None; notes: str | None = None

@router.get("/members")
def members(q: str | None = None, status: str | None = None, location_id: int | None = None, db: Session = Depends(get_db), u=Depends(require("memberships"))):
    qry = select(models.Member).where(models.Member.active == True).order_by(models.Member.name)
    if q: qry = qry.where(models.Member.name.ilike(f"%{q}%") | models.Member.phone.ilike(f"%{q}%"))
    if location_id: qry = qry.where(models.Member.location_id == location_id)
    out = [member_out(db, m) for m in db.scalars(qry)]
    if status == "OWING": out = [m for m in out if m["balance_cents"] > 0]
    elif status: out = [m for m in out if m["status"] == status]
    return out

@router.post("/members", status_code=201)
def add_member(d: MemberIn, db: Session = Depends(get_db), u=Depends(require("memberships"))):
    m = models.Member(**d.model_dump()); db.add(m); db.flush(); audit.log(db, u, "create", "member", m.id, None, d.model_dump()); db.commit(); return member_out(db, m)

@router.put("/members/{id}")
def edit_member(id: int, d: dict, db: Session = Depends(get_db), u=Depends(require("memberships"))):
    m = db.get(models.Member, id)
    if not m: raise HTTPException(404)
    for k in ("name", "phone", "email", "notes", "location_id", "active"):
        if k in d: setattr(m, k, d[k])
    audit.log(db, u, "update", "member", id, None, d); db.commit(); return member_out(db, m)

class SellIn(BaseModel): plan_id: int; start_on: date | None = None; price_cents: int | None = None; pay_cents: int = 0; method: str = "CASH"; location_id: int | None = None

@router.post("/members/{id}/subscriptions", status_code=201)
def sell(id: int, d: SellIn, db: Session = Depends(get_db), u=Depends(require("memberships"))):
    m, p = db.get(models.Member, id), db.get(models.Plan, d.plan_id)
    if not m or not p: raise HTTPException(404, "Member or plan not found")
    if d.pay_cents < 0: raise HTTPException(422, "Payment cannot be negative")
    start = d.start_on or date.today()
    # renewing early extends from the current end date so the member loses no days
    cur = db.scalar(select(models.Subscription).where(models.Subscription.member_id == id, models.Subscription.plan_id == p.id, models.Subscription.status == "ACTIVE", models.Subscription.end_on >= start).order_by(models.Subscription.end_on.desc()))
    if cur and p.kind == "membership": start = cur.end_on + timedelta(days=1)
    price = d.price_cents if d.price_cents is not None else p.price_cents
    if d.pay_cents > price: raise HTTPException(422, "Payment is larger than the price")
    s = models.Subscription(member_id=id, plan_id=p.id, location_id=d.location_id or m.location_id, start_on=start, end_on=start + timedelta(days=p.duration_days - 1), price_cents=price, sessions_left=p.sessions)
    db.add(s); db.flush()
    if d.pay_cents: db.add(models.SubPayment(subscription_id=s.id, amount_cents=d.pay_cents, method=d.method, location_id=s.location_id))
    audit.log(db, u, "sell_subscription", "subscription", s.id, None, {"member": m.name, "plan": p.name, "price_cents": price, "paid_cents": d.pay_cents})
    db.commit(); return sub_out(db, s)

class PayIn(BaseModel): amount_cents: int; method: str = "CASH"

@router.post("/subscriptions/{id}/payments", status_code=201)
def pay(id: int, d: PayIn, db: Session = Depends(get_db), u=Depends(require("memberships"))):
    s = db.get(models.Subscription, id)
    if not s: raise HTTPException(404)
    if d.amount_cents <= 0: raise HTTPException(422, "Amount must be positive")
    if d.amount_cents > s.price_cents - paid(db, id): raise HTTPException(422, "More than the outstanding balance")
    db.add(models.SubPayment(subscription_id=id, amount_cents=d.amount_cents, method=d.method, location_id=s.location_id))
    audit.log(db, u, "subscription_payment", "subscription", id, None, d.model_dump()); db.commit(); return sub_out(db, s)

@router.post("/subscriptions/{id}/cancel")
def cancel(id: int, db: Session = Depends(get_db), u=Depends(require("memberships_admin"))):
    s = db.get(models.Subscription, id)
    if not s: raise HTTPException(404)
    s.status = "CANCELLED"; audit.log(db, u, "cancel_subscription", "subscription", id); db.commit(); return sub_out(db, s)

class CheckInIn(BaseModel): location_id: int | None = None

@router.post("/members/{id}/checkin")
def checkin(id: int, d: CheckInIn, db: Session = Depends(get_db), u=Depends(require("memberships"))):
    m = db.get(models.Member, id)
    if not m: raise HTTPException(404)
    subs = [sub_out(db, s) for s in db.scalars(select(models.Subscription).where(models.Subscription.member_id == id))]
    act = [s for s in subs if s["state"] == "ACTIVE"]
    if not act: raise HTTPException(409, "No active membership - renew before entry")
    pack = next((s for s in act if s["sessions_left"] is not None), None)
    plain = next((s for s in act if s["sessions_left"] is None), None)
    if not plain and pack:
        sub = db.get(models.Subscription, pack["id"]); sub.sessions_left -= 1
    db.add(models.CheckIn(member_id=id, location_id=d.location_id or m.location_id))
    warn = [f"Unpaid balance {s['balance_cents']/100:.2f} EUR on {s['plan_name']}" for s in act if s["balance_cents"] > 0]
    db.commit(); return {"ok": True, "member": m.name, "warnings": warn, "sessions_left": (pack or {}).get("sessions_left") if not plain else None}

@router.get("/memberships/summary")
def summary(location_id: int | None = None, db: Session = Depends(get_db), u=Depends(require("memberships"))):
    ms = [member_out(db, m) for m in db.scalars(select(models.Member).where(models.Member.active == True))]
    if location_id: ms = [m for m in ms if m["location_id"] == location_id]
    soon = [m for m in ms if m["status"] == "ACTIVE" and m["valid_until"] and (m["valid_until"] if isinstance(m["valid_until"], date) else date.fromisoformat(str(m["valid_until"]))) <= date.today() + timedelta(days=7)]
    m0 = date.today().replace(day=1)
    rev = db.scalar(select(func.coalesce(func.sum(models.SubPayment.amount_cents), 0)).where(models.SubPayment.paid_on >= m0)) or 0
    today_in = db.scalar(select(func.count()).select_from(models.CheckIn).where(func.date(models.CheckIn.at) == date.today().isoformat())) or 0
    return {"active": sum(m["status"] == "ACTIVE" for m in ms), "expired": sum(m["status"] == "EXPIRED" for m in ms), "expiring_7d": [{"id": m["id"], "name": m["name"], "valid_until": str(m["valid_until"]), "plan": m["current_plan"]} for m in soon],
            "owing": [{"id": m["id"], "name": m["name"], "balance_cents": m["balance_cents"]} for m in ms if m["balance_cents"] > 0], "revenue_month_cents": rev, "checkins_today": today_in}
