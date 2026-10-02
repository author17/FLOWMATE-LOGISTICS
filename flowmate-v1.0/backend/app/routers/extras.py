"""Stock movements/transfer, purchase orders (create/PDF/send/invoice link), till CSV import, public order page,
inbound e-mail, exports & backups."""
import csv, hashlib, hmac, io, json, re, time, uuid, zipfile
from datetime import date, datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import Response, HTMLResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from .. import config, models, audit
from ..db import get_db, engine
from ..security import require, scope_location
from ..tenancy import use_business, get_setting, all_settings
from ..services import mailer, stripe_service as st
from .crud import row
from .operations import adjust_stock, order_out

router = APIRouter(prefix="/api", tags=["extras"])

# ---------------- stock movements & transfer ----------------
@router.get("/stock/movements")
def movements(product_id: int | None = None, location_id: int | None = None, limit: int = 200, db: Session = Depends(get_db), u=Depends(require("stock_read"))):
    location_id = scope_location(u, location_id)
    q = select(models.StockMovement).order_by(models.StockMovement.id.desc()).limit(min(limit, 1000))
    if product_id: q = q.where(models.StockMovement.product_id == product_id)
    if location_id: q = q.where(models.StockMovement.location_id == location_id)
    names = {p.id: p.name for p in db.scalars(select(models.Product))}
    return [{**row(m), "product": names.get(m.product_id, "")} for m in db.scalars(q)]

class TransferIn(BaseModel): product_id: int; from_location_id: int; to_location_id: int; quantity: int

@router.post("/stock/transfer")
def transfer(d: TransferIn, db: Session = Depends(get_db), u=Depends(require("stock"))):
    if d.quantity <= 0 or d.from_location_id == d.to_location_id: raise HTTPException(422, "Pick two different locations and a positive quantity")
    s = db.scalar(select(models.Stock).where(models.Stock.product_id == d.product_id, models.Stock.location_id == d.from_location_id))
    if not s or s.quantity < d.quantity: raise HTTPException(409, "Not enough stock at the source location")
    ref = f"TRANSFER-{uuid.uuid4().hex[:6]}"
    adjust_stock(db, d.product_id, d.from_location_id, -d.quantity, "transfer_out", ref)
    adjust_stock(db, d.product_id, d.to_location_id, d.quantity, "transfer_in", ref)
    audit.log(db, u, "stock_transfer", "product", d.product_id, None, d.model_dump()); db.commit(); return {"ok": True, "ref": ref}

# ---------------- purchase orders ----------------
class POItem(BaseModel): product_id: int; quantity: int; unit_cents: int | None = None
class POIn(BaseModel): supplier_id: int; location_id: int; items: list[POItem]

def po_full(db, p):
    s = db.get(models.Supplier, p.supplier_id); names = {x.id: x.name for x in db.scalars(select(models.Product))}
    items = [{**row(i), "product": names.get(i.product_id, "")} for i in p.items]
    return {**row(p), "supplier": s.name if s else "", "items": items, "total_cents": sum(i["quantity"] * i["unit_cents"] for i in items)}

@router.post("/purchase-orders", status_code=201)
def po_create(d: POIn, db: Session = Depends(get_db), u=Depends(require("purchase"))):
    if not d.items or any(i.quantity <= 0 for i in d.items): raise HTTPException(422, "Add at least one item with a positive quantity")
    if not db.get(models.Supplier, d.supplier_id): raise HTTPException(404, "Supplier not found")
    po = models.PurchaseOrder(supplier_id=d.supplier_id, location_id=d.location_id)
    for i in d.items:
        p = db.get(models.Product, i.product_id)
        if not p: raise HTTPException(404, f"Product {i.product_id} not found")
        po.items.append(models.PurchaseOrderItem(product_id=i.product_id, quantity=i.quantity, unit_cents=i.unit_cents if i.unit_cents is not None else p.purchase_cents))
    db.add(po); db.flush(); audit.log(db, u, "create", "purchase_order", po.id); db.commit(); return po_full(db, po)

@router.get("/purchase-orders/full")
def po_list(db: Session = Depends(get_db), u=Depends(require("purchase"))):
    return [po_full(db, p) for p in db.scalars(select(models.PurchaseOrder).order_by(models.PurchaseOrder.id.desc()))]

def po_pdf(db, p) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    f = po_full(db, p); ss = all_settings(db); loc = db.get(models.Location, p.location_id)
    buf = io.BytesIO(); st_ = getSampleStyleSheet()
    els = [Paragraph(f"Purchase Order PO-{p.id}", st_["Title"]), Paragraph(f"From: {ss.get('company_name') or 'Our company'} {('- VAT ' + ss['vat_number']) if ss.get('vat_number') else ''}", st_["Normal"]),
           Paragraph(f"To: {f['supplier']}", st_["Normal"]), Paragraph(f"Deliver to: {loc.name if loc else ''}", st_["Normal"]), Paragraph(f"Date: {p.created_at:%d/%m/%Y}", st_["Normal"]), Spacer(1, 14)]
    data = [["Product", "Qty", "Unit price", "Total"]] + [[i["product"], i["quantity"], f"{i['unit_cents']/100:.2f}", f"{i['quantity']*i['unit_cents']/100:.2f}"] for i in f["items"]] + [["", "", "TOTAL", f"{f['total_cents']/100:.2f}"]]
    t = Table(data, repeatRows=1); t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f3d5e")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .25, colors.grey), ("ALIGN", (1, 0), (-1, -1), "RIGHT")]))
    SimpleDocTemplate(buf, pagesize=A4).build(els + [t]); return buf.getvalue()

@router.get("/purchase-orders/{id}/pdf")
def po_pdf_ep(id: int, db: Session = Depends(get_db), u=Depends(require("purchase"))):
    p = db.get(models.PurchaseOrder, id)
    if not p: raise HTTPException(404)
    return Response(po_pdf(db, p), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=PO-{id}.pdf"})

@router.post("/purchase-orders/{id}/send")
def po_send(id: int, db: Session = Depends(get_db), u=Depends(require("purchase"))):
    p = db.get(models.PurchaseOrder, id)
    if not p: raise HTTPException(404)
    s = db.get(models.Supplier, p.supplier_id)
    if not s or not s.email: raise HTTPException(409, "This supplier has no e-mail address. Add it on the supplier profile, or download the PDF and send it yourself.")
    if not mailer.configured(): raise HTTPException(409, "E-mail sending is not set up (SMTP_* variables). Download the PDF and send it yourself.")
    try: mailer.send_email([s.email], f"Purchase order PO-{p.id}", f"Dear {s.name},\n\nPlease find our purchase order PO-{p.id} attached.\n\nThank you.", [(f"PO-{p.id}.pdf", po_pdf(db, p), "application/pdf")])
    except Exception as e: raise HTTPException(502, f"E-mail failed: {e}")
    if p.status == "DRAFT": p.status = "SENT"
    audit.log(db, u, "send", "purchase_order", id, None, {"to": s.email}); db.commit(); return po_full(db, p)

# ---------------- till / POS sales CSV import ----------------
def _num(v):
    v = str(v).strip().replace("€", "").replace(" ", "")
    if "," in v and "." in v: v = v.replace(",", "") if v.rfind(".") > v.rfind(",") else v.replace(".", "").replace(",", ".")
    else: v = v.replace(",", ".")
    return round(float(v) * 100)

@router.post("/orders/import-csv")
async def import_sales(location_id: int = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db), u=Depends(require("orders"))):
    """Daily sales from the till / POS (columns: date, amount|total, optional method, reference/description). Re-importing the same file adds nothing."""
    location_id = scope_location(u, location_id) or location_id
    text = (await file.read()).decode("utf-8-sig"); first = text.splitlines()[0] if text.strip() else ""; delim = max(",;\t", key=first.count)
    rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
    added = skipped = 0; errors = []
    for n, r in enumerate(rows, 2):
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        try:
            amt = _num(r.get("amount") or r.get("total") or r.get("gross") or "")
            d = r.get("date") or r.get("day") or ""; dt = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"):
                try: dt = datetime.strptime(d, fmt); break
                except ValueError: pass
            if not dt or amt <= 0: raise ValueError("bad date/amount")
        except Exception: errors.append(f"line {n}: could not read"); continue
        meth = (r.get("method") or r.get("payment") or "CARD").upper(); meth = meth if meth in ("CASH", "CARD", "BANK_TRANSFER", "ONLINE") else "CARD"
        ref = hashlib.sha1(f"{location_id}|{dt.date()}|{amt}|{meth}|{r.get('reference') or r.get('description') or ''}".encode()).hexdigest()[:24]
        if db.scalar(select(models.Order.id).where(models.Order.external_ref == "till:" + ref)): skipped += 1; continue
        o = models.Order(location_id=location_id, source="till", payment_method=meth, status="PAID", total_cents=amt, external_ref="till:" + ref, created_at=dt)
        o.items.append(models.OrderItem(description=r.get("description") or "Till sales", quantity=1, unit_cents=amt)); db.add(o); added += 1
    audit.log(db, u, "import_sales", "order", "", None, {"added": added, "skipped": skipped}); db.commit()
    return {"added": added, "skipped_duplicates": skipped, "errors": errors}

# ---------------- public customer order page ----------------
_hits: dict[str, list[float]] = {}
def _limit(ip, n=10, per=3600):
    now = time.time(); h = [t for t in _hits.get(ip, []) if now - t < per]
    if len(h) >= n: raise HTTPException(429, "Too many orders from this connection. Please call us.")
    h.append(now); _hits[ip] = h

def _public_on(db): return get_setting(db, "public_orders_enabled") in ("1", "true", "yes")

def pub_db(slug: str = ""):
    """Public pages are not logged in: the business comes from the link (/order/<slug>). An empty slug means the original business (#1)."""
    from ..db import SessionLocal
    db = SessionLocal()
    try:
        b = db.scalar(select(models.Business).where(models.Business.slug == slug, models.Business.active == True)) if slug else db.get(models.Business, 1)
        if not b: raise HTTPException(404, "Online ordering is not available")
        use_business(db, b.id); yield db
    finally: db.close()

@router.get("/public/{slug}/menu")
@router.get("/public/menu")
def pub_menu(slug: str = "", db: Session = Depends(pub_db)):
    if not _public_on(db): raise HTTPException(404, "Online ordering is not enabled")
    return {"company": get_setting(db, "company_name"), "stripe": st.configured(db), "locations": [{"id": l.id, "name": l.name} for l in db.scalars(select(models.Location))],
            "products": [{"id": p.id, "name": p.name, "price_cents": p.sell_cents} for p in db.scalars(select(models.Product).where(models.Product.show_online == True))]}

class PubItem(BaseModel): product_id: int; quantity: int
class PubOrder(BaseModel): name: str; phone: str = ""; email: str = ""; location_id: int; note: str = ""; pay_online: bool = False; items: list[PubItem]

@router.post("/public/{slug}/orders", status_code=201)
@router.post("/public/orders", status_code=201)
def pub_order(d: PubOrder, request: Request, slug: str = "", db: Session = Depends(pub_db)):
    if not _public_on(db): raise HTTPException(404, "Online ordering is not enabled")
    _limit((request.client.host if request.client else "x") + "|" + str(db.info["business_id"]))
    if not d.name.strip() or not (d.phone.strip() or d.email.strip()): raise HTTPException(422, "Name and a phone or e-mail are required")
    if not d.items or len(d.items) > 40 or any(i.quantity < 1 or i.quantity > 99 for i in d.items): raise HTTPException(422, "Bad items")
    if not db.get(models.Location, d.location_id): raise HTTPException(422, "Pick a location")
    c = models.Customer(name=d.name.strip()[:200], phone=d.phone.strip()[:50] or None, email=d.email.strip()[:200] or None); db.add(c); db.flush()
    o = models.Order(location_id=d.location_id, customer_id=c.id, source="website", payment_method="ONLINE" if d.pay_online else "CASH", note=d.note[:300] or None); total = 0
    for i in d.items:
        p = db.get(models.Product, i.product_id)
        if not p or not p.show_online: raise HTTPException(422, "Product not available online")   # price always comes from the server
        o.items.append(models.OrderItem(product_id=p.id, description=p.name, quantity=i.quantity, unit_cents=p.sell_cents)); total += p.sell_cents * i.quantity
    o.total_cents = total; db.add(o); db.flush()
    audit.notify(db, "new_order", f"New ONLINE order #{o.id} from {c.name} ({total/100:.2f} EUR)")
    out = {"order_id": o.id, "total_cents": total, "pay_url": None}
    if d.pay_online and st.configured(db) and total >= 50:
        try:
            s = st.create_checkout(db, total, f"Order #{o.id}", "order", o.id, c.email)
            db.add(models.OnlinePayment(session_id=s["id"], target_type="order", target_id=o.id, amount_cents=total, url=s["url"], created_by=None)); out["pay_url"] = s["url"]
        except Exception: pass
    db.commit(); return out

PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Order</title>
<style>body{font-family:system-ui;margin:0;background:#f4f7fa}main{max-width:560px;margin:auto;padding:16px}h1{color:#0f3d5e}.r{display:flex;justify-content:space-between;align-items:center;background:#fff;border-radius:8px;padding:10px;margin:6px 0}
input,select,textarea,button{font:inherit;padding:10px;border:1px solid #ccd;border-radius:8px;width:100%;box-sizing:border-box;margin:4px 0}button{background:#0f3d5e;color:#fff;border:0}.r input{width:64px}</style>
<main><h1 id=t>Order</h1><div id=m>Loading...</div></main><script>
(async()=>{const m=document.getElementById('m');const slug=location.pathname.split('/')[2]||'';const base='/api/public/'+(slug?slug+'/':'');const r=await fetch(base+'menu');if(!r.ok){m.textContent='Online ordering is not available.';return}
const d=await r.json();document.getElementById('t').textContent=(d.company||'')+' - order online';
m.innerHTML='<select id=l>'+d.locations.map(l=>`<option value=${l.id}>${l.name}</option>`).join('')+'</select>'+d.products.map(p=>`<div class=r><span>${p.name}<br><b>${(p.price_cents/100).toFixed(2)} EUR</b></span><input type=number min=0 max=99 value=0 data-id=${p.id}></div>`).join('')+
'<input id=n placeholder="Your name"><input id=p placeholder="Phone"><input id=e placeholder="E-mail (optional)"><textarea id=o placeholder="Note"></textarea>'+(d.stripe?'<label><input type=checkbox id=pay style="width:auto"> Pay by card now</label>':'')+'<button id=go>Place order</button><p id=msg></p>';
document.getElementById('go').onclick=async()=>{const items=[...m.querySelectorAll('[data-id]')].filter(i=>+i.value>0).map(i=>({product_id:+i.dataset.id,quantity:+i.value}));
const x=await fetch(base+'orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n.value,phone:p.value,email:e.value,note:o.value,location_id:+l.value,pay_online:!!(document.getElementById('pay')&&pay.checked),items})});
const j=await x.json();if(!x.ok){msg.textContent=j.detail&&j.detail.map?'Please fill name, phone and items':j.detail;return}
if(j.pay_url){location=j.pay_url}else{m.innerHTML='<h2>Thank you! Order #'+j.order_id+' received.</h2>'}}})();</script>"""

page_router = APIRouter()
@page_router.get("/order", include_in_schema=False)
@page_router.get("/order/{slug}", include_in_schema=False)
def order_page(slug: str = ""): return HTMLResponse(PAGE)

# ---------------- inbound e-mail (forward supplier invoices to the app) ----------------
@router.post("/inbound/email", status_code=201)
async def inbound_email(request: Request, token: str = "", db: Session = Depends(get_db)):
    """Point an e-mail-to-webhook service (Mailgun/Postmark/Zapier) here. Each business has its own private token; attachments become documents to verify in THAT business."""
    b = db.scalar(select(models.Business).where(models.Business.inbound_token == token, models.Business.active == True)) if len(token) >= 16 else None
    if not b: raise HTTPException(403, "Bad token")
    use_business(db, b.id)
    form = await request.form(); made = 0
    for k, f in form.multi_items():
        if not hasattr(f, "filename") or not f.filename: continue
        ext = "." + f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in {".jpg", ".jpeg", ".png", ".pdf", ".webp"}: continue
        data = await f.read()
        if len(data) > 15 * 1024 * 1024: continue
        key = f"b{b.id}/invoice/{uuid.uuid4().hex}{ext}"; path = config.STORAGE_DIR / key; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        from ..ocr import get_ocr
        try: ex = get_ocr().extract(data, f.filename)
        except Exception as e: ex = {"error": str(e), "confidence": 0}
        db.add(models.Document(doc_type="invoice", filename=re.sub(r"[^\w.\- ]", "_", f.filename), storage_key=key, extracted=ex, source="email", company=str(form.get("from", ""))[:200] or None)); made += 1
    if made: audit.notify(db, "doc_to_verify", f"{made} document(s) arrived by e-mail and need checking")
    db.commit(); return {"documents": made}

# ---------------- exports & backups ----------------
SECRET_COLS = {"password_hash", "totp_secret", "recovery_codes", "state", "authorization_id", "session_id", "sms_hash", "inbound_token"}
SECRET_SETTINGS = ("eb_", "stripe_")

def _dump_zip(db_engine, include_files: bool, only_files=False, business_id: int | None = None) -> bytes:
    """business_id=None is the platform-wide backup (all businesses). A business id exports ONLY that business."""
    buf = io.BytesIO(); keys = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        with db_engine.connect() as cn:
            if not only_files:
                for t in models.Base.metadata.sorted_tables:
                    cols = [c.name for c in t.columns if c.name not in SECRET_COLS]; sio = io.StringIO(); w = csv.writer(sio); w.writerow(cols)
                    q = select(*[t.c[c] for c in cols])
                    if business_id is not None: q = q.where(t.c.id == business_id) if t.name == "businesses" else q.where(t.c.business_id == business_id)
                    for r in cn.execute(q):
                        if t.name == "settings" and any(str(r[0]).split(":", 1)[-1].startswith(p) for p in SECRET_SETTINGS): continue
                        w.writerow(["" if v is None else v for v in r])
                    z.writestr(f"data/{t.name}.csv", sio.getvalue())
            if business_id is not None:
                keys = [r[0] for r in cn.execute(select(models.Document.__table__.c.storage_key).where(models.Document.__table__.c.business_id == business_id))]
        if include_files or only_files:
            if business_id is None:
                for p in config.STORAGE_DIR.rglob("*"):
                    if p.is_file() and "backups" not in p.relative_to(config.STORAGE_DIR).parts: z.write(p, "files/" + p.relative_to(config.STORAGE_DIR).as_posix())
            else:
                for k in keys:
                    p = config.STORAGE_DIR / k
                    if p.is_file(): z.write(p, "files/" + k)
    return buf.getvalue()

BK = lambda: (config.STORAGE_DIR / "backups")

def run_backup(keep=14) -> str:
    """Platform backup of ALL businesses (for disaster recovery). Never reachable by a normal business owner."""
    BK().mkdir(parents=True, exist_ok=True); name = f"flowmate-backup-{datetime.utcnow():%Y%m%d-%H%M%S}.zip"
    (BK() / name).write_bytes(_dump_zip(engine, True))
    for old in sorted(BK().glob("flowmate-backup-*.zip"))[:-keep]: old.unlink()
    return name

def platform_admin(u=Depends(require("users_dummy"))):
    if u.email.lower() not in config.PLATFORM_ADMIN_EMAILS: raise HTTPException(403, "Only the platform operator can use backups of the whole system")
    return u

@router.get("/export")
def export_list(u=Depends(require("reports"))):
    from .reports import EXPORTS
    return {"tables": sorted(EXPORTS), "bundles": ["all.zip", "documents.zip"]}

@router.get("/export/all.zip")
def export_all(db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    audit.log(db, u, "export_all", "system", ""); db.commit()
    return Response(_dump_zip(engine, False, business_id=u.business_id), media_type="application/zip", headers={"Content-Disposition": "attachment; filename=flowmate-data.zip"})

@router.get("/export/documents.zip")
def export_docs(db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    audit.log(db, u, "export_documents", "system", ""); db.commit()
    return Response(_dump_zip(engine, True, only_files=True, business_id=u.business_id), media_type="application/zip", headers={"Content-Disposition": "attachment; filename=flowmate-documents.zip"})

@router.get("/backups")
def backups(u=Depends(platform_admin)):
    return [{"name": p.name, "bytes": p.stat().st_size, "at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")} for p in sorted(BK().glob("flowmate-backup-*.zip"), reverse=True)] if BK().exists() else []

@router.post("/backups/run", status_code=201)
def backups_run(db: Session = Depends(get_db), u=Depends(platform_admin)):
    n = run_backup(); audit.log(db, u, "backup", "system", n); db.commit(); return {"name": n}

@router.get("/backups/{name}")
def backup_get(name: str, u=Depends(platform_admin)):
    if not re.fullmatch(r"flowmate-backup-\d{8}-\d{6}\.zip", name) or not (BK() / name).exists(): raise HTTPException(404)
    return FileResponse(BK() / name, filename=name)
