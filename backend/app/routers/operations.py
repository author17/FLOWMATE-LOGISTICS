from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import require
from .. import models, audit
from .crud import row

router = APIRouter(prefix="/api", tags=["operations"])

def adjust_stock(db, product_id, location_id, change, reason, ref=""):
    s = db.scalar(select(models.Stock).where(models.Stock.product_id == product_id, models.Stock.location_id == location_id))
    if not s:
        s = models.Stock(product_id=product_id, location_id=location_id, quantity=0); db.add(s)
    s.quantity += change
    db.add(models.StockMovement(product_id=product_id, location_id=location_id, change=change, reason=reason, ref=ref))
    p = db.get(models.Product, product_id)
    if p and s.quantity <= p.min_stock:
        audit.notify(db, "low_stock", f"Low stock: {p.name} ({s.quantity} left, minimum {p.min_stock})")

# ---------------- Orders ----------------
class Item(BaseModel):
    product_id: int | None = None; description: str = ""; quantity: int = 1; unit_cents: int | None = None

class OrderIn(BaseModel):
    location_id: int; customer_id: int | None = None; source: str = "manual"; payment_method: str = "BANK_TRANSFER"; items: list[Item]

def order_out(o): return {**row(o), "items": [row(i) for i in o.items]}

@router.get("/orders")
def orders(location_id: int | None = None, db: Session = Depends(get_db), u=Depends(require("orders"))):
    q = select(models.Order).order_by(models.Order.id.desc())
    if location_id: q = q.where(models.Order.location_id == location_id)
    return [order_out(o) for o in db.scalars(q)]

@router.post("/orders", status_code=201)
def create_order(d: OrderIn, db: Session = Depends(get_db), u=Depends(require("orders"))):
    o = models.Order(location_id=d.location_id, customer_id=d.customer_id, source=d.source, payment_method=d.payment_method)
    total = 0
    for it in d.items:
        p = db.get(models.Product, it.product_id) if it.product_id else None
        price = it.unit_cents if it.unit_cents is not None else (p.sell_cents if p else 0)
        o.items.append(models.OrderItem(product_id=it.product_id, description=it.description or (p.name if p else "Item"), quantity=it.quantity, unit_cents=price))
        total += price * it.quantity
    o.total_cents = total; db.add(o); db.flush()
    for it in o.items:
        if it.product_id: adjust_stock(db, it.product_id, o.location_id, -it.quantity, "sale", f"ORDER-{o.id}")
    audit.log(db, u, "create", "order", o.id, None, {"total_cents": total}); audit.notify(db, "new_order", f"New order #{o.id}")
    db.commit(); return order_out(o)

class StatusIn(BaseModel): status: str

@router.put("/orders/{id}/status")
def order_status(id: int, d: StatusIn, db: Session = Depends(get_db), u=Depends(require("orders"))):
    if d.status not in {"NEW", "PROCESSING", "COMPLETED", "PAID", "CANCELLED"}: raise HTTPException(422, "Bad status")
    o = db.get(models.Order, id)
    if not o: raise HTTPException(404)
    old = o.status; o.status = d.status
    audit.log(db, u, "status", "order", id, {"status": old}, {"status": d.status}); db.commit(); return order_out(o)

# ---------------- Invoices ----------------
class InvoiceIn(BaseModel):
    supplier_id: int; number: str; issue_date: date; due_date: date | None = None
    total_cents: int; vat_cents: int = 0; location_id: int | None = None; document_id: int | None = None
    items: list[Item] = []; add_to_stock: bool = False

def invoice_out(i, db):
    s = db.get(models.Supplier, i.supplier_id)
    return {**row(i), "supplier_name": s.name if s else "", "items": [row(x) for x in i.items]}

@router.get("/invoices")
def invoices(status: str | None = None, db: Session = Depends(get_db), u=Depends(require("invoices"))):
    q = select(models.Invoice).order_by(models.Invoice.due_date)
    if status: q = q.where(models.Invoice.status == status)
    return [invoice_out(i, db) for i in db.scalars(q)]

@router.post("/invoices", status_code=201)
def create_invoice(d: InvoiceIn, db: Session = Depends(get_db), u=Depends(require("invoices"))):
    dup = db.scalar(select(models.Invoice).where(models.Invoice.supplier_id == d.supplier_id, models.Invoice.number == d.number))
    if dup: raise HTTPException(409, "This supplier invoice number already exists (duplicate?)")
    i = models.Invoice(**d.model_dump(exclude={"items", "add_to_stock"}))
    for it in d.items:
        i.items.append(models.InvoiceItem(product_id=it.product_id, description=it.description, quantity=it.quantity, unit_cents=it.unit_cents or 0))
    db.add(i); db.flush()
    if d.add_to_stock and d.location_id:
        for it in i.items:
            if it.product_id: adjust_stock(db, it.product_id, d.location_id, it.quantity, "purchase", f"INV-{i.number}")
    if d.document_id:
        doc = db.get(models.Document, d.document_id)
        if doc: doc.status = "VERIFIED"
    audit.log(db, u, "create", "invoice", i.id, None, {"number": i.number, "total_cents": i.total_cents}); audit.notify(db, "invoice", f"Invoice {i.number} received")
    db.commit(); return invoice_out(i, db)

# ---------------- Expenses ----------------
class ExpenseIn(BaseModel):
    category: str; amount_cents: int; spent_on: date; description: str = ""; vat_cents: int = 0
    location_id: int | None = None; payment_method: str = "CASH"; document_id: int | None = None

@router.get("/expenses")
def expenses(db: Session = Depends(get_db), u=Depends(require("expenses"))):
    return [row(e) for e in db.scalars(select(models.Expense).order_by(models.Expense.spent_on.desc()))]

@router.post("/expenses", status_code=201)
def add_expense(d: ExpenseIn, db: Session = Depends(get_db), u=Depends(require("expenses"))):
    e = models.Expense(**d.model_dump()); db.add(e); db.flush()
    if d.document_id:
        doc = db.get(models.Document, d.document_id)
        if doc: doc.status = "VERIFIED"
    audit.log(db, u, "create", "expense", e.id, None, d.model_dump(mode="json")); db.commit(); return row(e)

# ---------------- Stock & purchase orders ----------------
@router.get("/stock")
def stock(location_id: int | None = None, db: Session = Depends(get_db), u=Depends(require("stock_read"))):
    q = select(models.Stock, models.Product).join(models.Product, models.Stock.product_id == models.Product.id)
    if location_id: q = q.where(models.Stock.location_id == location_id)
    return [{"product_id": p.id, "sku": p.sku, "name": p.name, "location_id": s.location_id, "quantity": s.quantity, "min_stock": p.min_stock, "low": s.quantity <= p.min_stock} for s, p in db.execute(q)]

class AdjustIn(BaseModel): product_id: int; location_id: int; change: int; reason: str = "adjustment"

@router.post("/stock/adjust")
def adjust(d: AdjustIn, db: Session = Depends(get_db), u=Depends(require("stock"))):
    adjust_stock(db, d.product_id, d.location_id, d.change, d.reason, f"user-{u.id}")
    audit.log(db, u, "stock_adjust", "product", d.product_id, None, d.model_dump()); db.commit(); return {"ok": True}

@router.post("/purchase-orders/from-low-stock/{location_id}", status_code=201)
def po_from_low_stock(location_id: int, db: Session = Depends(get_db), u=Depends(require("purchase"))):
    """Creates one DRAFT purchase order per supplier for every product at/below minimum (order up to max)."""
    rows = db.execute(select(models.Stock, models.Product).join(models.Product, models.Stock.product_id == models.Product.id)
                      .where(models.Stock.location_id == location_id)).all()
    by_sup: dict[int, models.PurchaseOrder] = {}
    for s, p in rows:
        if s.quantity <= p.min_stock and p.supplier_id:
            po = by_sup.setdefault(p.supplier_id, models.PurchaseOrder(supplier_id=p.supplier_id, location_id=location_id))
            po.items.append(models.PurchaseOrderItem(product_id=p.id, quantity=max((p.max_stock or p.min_stock * 3) - s.quantity, 1), unit_cents=p.purchase_cents))
    for po in by_sup.values(): db.add(po)
    db.flush()
    for po in by_sup.values(): audit.log(db, u, "create_from_low_stock", "purchase_order", po.id)
    db.commit()
    return [{"id": po.id, "supplier_id": po.supplier_id, "items": [row(i) for i in po.items]} for po in by_sup.values()]

@router.get("/purchase-orders")
def pos(db: Session = Depends(get_db), u=Depends(require("purchase"))):
    return [{**row(p), "items": [row(i) for i in p.items]} for p in db.scalars(select(models.PurchaseOrder))]

@router.put("/purchase-orders/{id}/status")
def po_status(id: int, d: StatusIn, db: Session = Depends(get_db), u=Depends(require("purchase"))):
    if d.status not in {"DRAFT", "SENT", "CONFIRMED", "RECEIVED", "INVOICED", "PAID"}: raise HTTPException(422, "Bad status")
    p = db.get(models.PurchaseOrder, id)
    if not p: raise HTTPException(404)
    old = p.status
    if d.status == "RECEIVED" and old != "RECEIVED":
        for i in p.items: adjust_stock(db, i.product_id, p.location_id, i.quantity, "purchase", f"PO-{p.id}")
    p.status = d.status; audit.log(db, u, "status", "purchase_order", id, {"status": old}, {"status": d.status}); db.commit(); return row(p)
