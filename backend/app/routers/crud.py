"""Generic list/create/update/delete for simple master-data tables (locations, customers, suppliers, products, categories)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import require
from .. import models, audit

def row(o): return {c.name: getattr(o, c.name) for c in o.__table__.columns}

def make_router(prefix: str, model, area: str, fields: set[str]):
    r = APIRouter(prefix=f"/api/{prefix}", tags=[prefix])

    def clean(data: dict):
        bad = set(data) - fields
        if bad: raise HTTPException(422, f"Unknown fields: {sorted(bad)}")
        return data

    @r.get("")
    def list_(db: Session = Depends(get_db), user=Depends(require(area))):
        return [row(o) for o in db.scalars(select(model).order_by(model.id))]

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
    make_router("locations", models.Location, "settings_dummy", {"name", "kind"}),  # owner/admin only (not in any other role's perms)
    make_router("customers", models.Customer, "customers", {"name", "email", "phone"}),
    make_router("suppliers", models.Supplier, "suppliers", {"name", "email", "phone", "vat_number", "iban", "notes"}),
    make_router("categories", models.Category, "products", {"name"}),
    make_router("products", models.Product, "products", {"sku", "name", "category_id", "supplier_id", "purchase_cents", "sell_cents", "vat_percent", "min_stock", "max_stock"}),
]
