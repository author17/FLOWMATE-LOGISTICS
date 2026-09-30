"""Generic list/create/update/delete for simple master-data tables (locations, customers, suppliers, products, categories)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import require, current_user
from .. import models, audit

def valid_iban(iban: str) -> str:
    x = "".join(iban.split()).upper()
    if not (15 <= len(x) <= 34) or not x[:2].isalpha() or not x[2:4].isdigit() or not x.isalnum(): raise HTTPException(422, "IBAN looks wrong (check letters/digits)")
    n = "".join(str(int(ch, 36)) for ch in x[4:] + x[:4])
    if int(n) % 97 != 1: raise HTTPException(422, "IBAN checksum failed - a digit is probably mistyped")
    return x

def row(o): return {c.name: getattr(o, c.name) for c in o.__table__.columns}

def make_router(prefix: str, model, area: str, fields: set[str], read_area: str | None = None):
    r = APIRouter(prefix=f"/api/{prefix}", tags=[prefix])

    def clean(data: dict):
        bad = set(data) - fields
        if bad: raise HTTPException(422, f"Unknown fields: {sorted(bad)}")
        if prefix == "suppliers" and data.get("iban"): data["iban"] = valid_iban(data["iban"])
        return data

    @r.get("")
    def list_(q: str | None = None, db: Session = Depends(get_db), user=Depends(current_user if read_area == "any" else require(read_area or area))):
        qry = select(model).order_by(model.id)
        if q and hasattr(model, "name"): qry = qry.where(model.name.ilike(f"%{q}%"))
        return [row(o) for o in db.scalars(qry)]

    @r.post("", status_code=201)
    def create(data: dict, db: Session = Depends(get_db), user=Depends(require(area))):
        o = model(**clean(data)); db.add(o); db.flush()
        audit.log(db, user, "create", prefix, o.id, None, clean(data)); db.commit()
        return row(o)

    @r.put("/{id}")
    def update(id: int, data: dict, db: Session = Depends(get_db), user=Depends(require(area))):
        o = db.get(model, id)
        if not o: raise HTTPException(404)
        old = row(o)
        for k, v in clean(data).items(): setattr(o, k, v)
        audit.log(db, user, "update", prefix, id, old, data); db.commit()
        return row(o)

    @r.delete("/{id}")
    def delete(id: int, db: Session = Depends(get_db), user=Depends(require(area))):
        o = db.get(model, id)
        if not o: raise HTTPException(404)
        audit.log(db, user, "delete", prefix, id, row(o), None)
        db.delete(o); db.commit()
        return {"ok": True}
    return r

routers = [
    make_router("locations", models.Location, "settings_dummy", {"name", "kind"}, read_area="any"),  # owner/admin only (not in any other role's perms)
    make_router("customers", models.Customer, "orders", {"name", "email", "phone"}),
    make_router("suppliers", models.Supplier, "suppliers", {"name", "email", "phone", "vat_number", "iban", "notes"}, read_area="invoices"),
    make_router("categories", models.Category, "products", {"name"}, read_area="stock_read"),
    make_router("products", models.Product, "products", {"sku", "name", "category_id", "supplier_id", "purchase_cents", "sell_cents", "vat_percent", "min_stock", "max_stock", "show_online"}, read_area="stock_read"),
    make_router("plans", models.Plan, "memberships_admin", {"name", "kind", "duration_days", "sessions", "price_cents", "active"}, read_area="memberships"),
]
