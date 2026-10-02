"""Global search box: finds customers, suppliers, products, orders, invoices, documents and members the user is allowed to see."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import current_user, PERMS
from .. import models

router = APIRouter(prefix="/api", tags=["search"])
ok = lambda u, a: "*" in PERMS.get(u.role, set()) or a in PERMS.get(u.role, set())

@router.get("/search")
def search(q: str = "", db: Session = Depends(get_db), u=Depends(current_user)):
    q = q.strip()
    if len(q) < 2: return []
    like, out = f"%{q}%", []
    def add(kind, tab, label, sub=""): out.append({"kind": kind, "tab": tab, "label": label, "sub": sub})
    if ok(u, "orders"):
        for c in db.scalars(select(models.Customer).where(models.Customer.name.ilike(like) | models.Customer.phone.ilike(like) | models.Customer.email.ilike(like)).limit(5)): add("Customer", "Customers", c.name, c.phone or c.email or "")
        if q.lstrip("#").isdigit():
            o = db.get(models.Order, int(q.lstrip("#")))
            if o: add("Order", "Orders", f"Order #{o.id}", f"{o.total_cents/100:.2f} EUR · {o.status}")
    if ok(u, "invoices"):
        for s in db.scalars(select(models.Supplier).where(models.Supplier.name.ilike(like) | models.Supplier.vat_number.ilike(like)).limit(5)): add("Supplier", "Suppliers", s.name, s.vat_number or "")
        for i in db.scalars(select(models.Invoice).where(models.Invoice.number.ilike(like)).limit(5)): add("Invoice", "Invoices", f"Invoice {i.number}", f"{i.total_cents/100:.2f} EUR · {i.status}")
    if ok(u, "stock_read"):
        for p in db.scalars(select(models.Product).where(models.Product.name.ilike(like) | models.Product.sku.ilike(like)).limit(5)): add("Product", "Products", p.name, p.sku)
    if ok(u, "documents"):
        for d in db.scalars(select(models.Document).where(models.Document.filename.ilike(like) | models.Document.company.ilike(like) | models.Document.reference.ilike(like)).limit(5)): add("Document", "Scan", d.filename, d.company or "")
    if ok(u, "memberships"):
        for m in db.scalars(select(models.Member).where(models.Member.name.ilike(like) | models.Member.phone.ilike(like)).limit(5)): add("Member", "Members", m.name, m.phone or "")
    return out[:25]
