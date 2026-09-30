"""All business reports as JSON / CSV / Excel / PDF. Each report = (title, columns, rows)."""
import csv, io
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import require
from .. import models

router = APIRouter(prefix="/api/reports", tags=["reports"])
eur = lambda c: round((c or 0) / 100, 2)

def _rng(a, b):
    b = b or date.today(); a = a or b.replace(day=1); return a, b

def _orders(db, a, b, loc=None):
    q = select(models.Order).where(models.Order.status != "CANCELLED", models.Order.created_at >= a, models.Order.created_at < b + timedelta(days=1))
    if loc: q = q.where(models.Order.location_id == loc)
    return db.scalars(q).all()

def _locname(db): return {l.id: l.name for l in db.scalars(select(models.Location))}

def r_sales(db, a, b, loc, period="day"):
    names, agg = _locname(db), {}
    key = lambda d: d.isoformat() if period == "day" else (d - timedelta(days=d.weekday())).isoformat() if period == "week" else d.strftime("%Y-%m")
    for o in _orders(db, a, b, loc):
        k = (key(o.created_at.date()), names.get(o.location_id, "")); agg[k] = agg.get(k, 0) + o.total_cents
    for p in db.scalars(select(models.SubPayment).where(models.SubPayment.paid_on >= a, models.SubPayment.paid_on <= b)):
        if loc and p.location_id != loc: continue
        k = (key(p.paid_on), names.get(p.location_id, "") + " (memberships)"); agg[k] = agg.get(k, 0) + p.amount_cents
    rows = [[k[0], k[1], eur(v)] for k, v in sorted(agg.items())]
    return f"Sales by {period}", ["Period", "Location", "Sales EUR"], rows + [["TOTAL", "", round(sum(r[2] for r in rows), 2)]]

def r_expenses(db, a, b, loc):
    agg = {}
    for e in db.scalars(select(models.Expense).where(models.Expense.spent_on >= a, models.Expense.spent_on <= b)):
        if loc and e.location_id != loc: continue
        agg[e.category] = agg.get(e.category, 0) + e.amount_cents
    rows = [[k, eur(v)] for k, v in sorted(agg.items(), key=lambda x: -x[1])]
    return "Expenses by category", ["Category", "EUR"], rows + [["TOTAL", round(sum(r[1] for r in rows), 2)]]

def r_suppliers(db, a, b, loc):
    rows = []
    for s in db.scalars(select(models.Supplier)):
        inv = db.scalars(select(models.Invoice).where(models.Invoice.supplier_id == s.id, models.Invoice.issue_date >= a, models.Invoice.issue_date <= b)).all()
        tot = sum(i.total_cents for i in inv); out = sum(i.total_cents for i in db.scalars(select(models.Invoice).where(models.Invoice.supplier_id == s.id, models.Invoice.status != "PAID")))
        if tot or out: rows.append([s.name, len(inv), eur(tot), eur(out)])
    return "Supplier spending", ["Supplier", "Invoices in period", "Invoiced EUR", "Outstanding EUR (all time)"], sorted(rows, key=lambda r: -r[2])

def r_outstanding(db, a, b, loc):
    rows = []; today = date.today()
    for i in db.scalars(select(models.Invoice).where(models.Invoice.status != "PAID").order_by(models.Invoice.due_date)):
        s = db.get(models.Supplier, i.supplier_id)
        rows.append([s.name if s else "", i.number, str(i.due_date or ""), eur(i.total_cents), "OVERDUE" if i.due_date and i.due_date < today else i.status])
    return "Outstanding supplier invoices", ["Supplier", "Invoice", "Due", "EUR", "Status"], rows

def r_customers(db, a, b, loc):
    agg = {}
    for o in _orders(db, a, b, loc):
        c = db.get(models.Customer, o.customer_id).name if o.customer_id else "(walk-in)"
        x = agg.setdefault(c, [0, 0]); x[0 if o.status == "PAID" else 1] += o.total_cents
    return "Customer payments", ["Customer", "Paid EUR", "Unpaid EUR"], [[k, eur(v[0]), eur(v[1])] for k, v in sorted(agg.items())]

def r_bank(db, a, b, loc):
    rows = [[str(t.booked_on), eur(t.amount_cents), t.reference, t.counterparty, t.match_status] for t in db.scalars(select(models.BankTransaction).where(models.BankTransaction.booked_on >= a, models.BankTransaction.booked_on <= b).order_by(models.BankTransaction.booked_on))]
    return "Bank transactions", ["Date", "EUR", "Reference", "Counterparty", "Status"], rows

def r_cashflow(db, a, b, loc):
    agg = {}
    for t in db.scalars(select(models.BankTransaction).where(models.BankTransaction.booked_on >= a, models.BankTransaction.booked_on <= b)):
        m = t.booked_on.strftime("%Y-%m"); x = agg.setdefault(m, [0, 0]); x[0 if t.amount_cents > 0 else 1] += abs(t.amount_cents)
    return "Cash flow (bank)", ["Month", "Money in EUR", "Money out EUR", "Net EUR"], [[m, eur(v[0]), eur(v[1]), eur(v[0] - v[1])] for m, v in sorted(agg.items())]

def r_vat(db, a, b, loc):
    out = 0.0; out_by = {}
    for o in _orders(db, a, b, loc):
        for it in o.items:
            p = db.get(models.Product, it.product_id) if it.product_id else None; rate = p.vat_percent if p else 19
            v = it.unit_cents * it.quantity * rate / (100 + rate); out_by[rate] = out_by.get(rate, 0) + v; out += v
    inp = sum(i.vat_cents for i in db.scalars(select(models.Invoice).where(models.Invoice.issue_date >= a, models.Invoice.issue_date <= b))) + \
          sum(e.vat_cents for e in db.scalars(select(models.Expense).where(models.Expense.spent_on >= a, models.Expense.spent_on <= b)))
    rows = [[f"Output VAT on sales @ {r}%", eur(v)] for r, v in sorted(out_by.items())] + [["Total output VAT (on sales)", eur(out)], ["Input VAT (supplier invoices + expenses)", eur(inp)], ["Estimated VAT payable", eur(out - inp)],
            ["NOTE: estimate only - prices assumed VAT-inclusive; confirm rates and filing with your accountant", ""]]
    return "VAT summary (estimate)", ["Item", "EUR"], rows

def r_stockvalue(db, a, b, loc):
    rows = []; tot = 0
    for s, p in db.execute(select(models.Stock, models.Product).join(models.Product, models.Stock.product_id == models.Product.id)):
        if loc and s.location_id != loc: continue
        v = s.quantity * p.purchase_cents; tot += v; rows.append([p.name, _locname(db).get(s.location_id, ""), s.quantity, eur(p.purchase_cents), eur(v)])
    return "Stock value (at purchase price)", ["Product", "Location", "Qty", "Unit cost EUR", "Value EUR"], rows + [["TOTAL", "", "", "", eur(tot)]]

def r_products(db, a, b, loc):
    agg = {}
    for o in _orders(db, a, b, loc):
        for it in o.items:
            x = agg.setdefault(it.description, [0, 0]); x[0] += it.quantity; x[1] += it.quantity * it.unit_cents
    return "Product sales", ["Product", "Units", "Sales EUR"], [[k, v[0], eur(v[1])] for k, v in sorted(agg.items(), key=lambda x: -x[1][1])]

def r_pnl(db, a, b, loc):
    sales = sum(o.total_cents for o in _orders(db, a, b, loc)) + sum(p.amount_cents for p in db.scalars(select(models.SubPayment).where(models.SubPayment.paid_on >= a, models.SubPayment.paid_on <= b)) if not loc or p.location_id == loc)
    exp = sum(e.amount_cents for e in db.scalars(select(models.Expense).where(models.Expense.spent_on >= a, models.Expense.spent_on <= b)) if not loc or e.location_id == loc)
    inv = sum(i.total_cents for i in db.scalars(select(models.Invoice).where(models.Invoice.issue_date >= a, models.Invoice.issue_date <= b)) if not loc or i.location_id == loc)
    rows = [["Revenue (orders + memberships paid)", eur(sales)], ["Expenses", eur(exp)], ["Supplier invoices received", eur(inv)], ["Profit / loss ESTIMATE", eur(sales - exp - inv)],
            ["NOTE: management estimate, not accounts. Cash-basis for memberships, invoice-date basis for purchases.", ""]]
    return "Profit / loss estimate", ["Item", "EUR"], rows

def r_shifts(db, a, b, loc):
    names = _locname(db); rows = []
    for s in db.scalars(select(models.Shift).where(models.Shift.status == "CLOSED", models.Shift.opened_at >= a, models.Shift.opened_at < b + timedelta(days=1))):
        if loc and s.location_id != loc: continue
        rows.append([str(s.opened_at)[:16], names.get(s.location_id, ""), eur(s.cash_sales_cents), eur(s.card_sales_cents), eur(s.difference_cents)])
    return "Cashier cash-up differences", ["Opened", "Location", "Cash sales EUR", "Card sales EUR", "Difference EUR"], rows

REPORTS = {"sales": r_sales, "expenses": r_expenses, "suppliers": r_suppliers, "outstanding": r_outstanding, "customers": r_customers, "bank": r_bank, "cashflow": r_cashflow,
           "vat": r_vat, "stock": r_stockvalue, "products": r_products, "pnl": r_pnl, "shifts": r_shifts}

def _xlsx(title, cols, rows):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook(); ws = wb.active; ws.title = title[:30]; ws.append(cols)
    for c in ws[1]: c.font = Font(bold=True)
    for r in rows: ws.append(r)
    for i, col in enumerate(ws.columns): ws.column_dimensions[col[0].column_letter].width = max(12, min(50, max(len(str(c.value or "")) for c in col) + 2))
    b = io.BytesIO(); wb.save(b); return b.getvalue()

def _pdf(title, cols, rows, sub):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    st = getSampleStyleSheet(); b = io.BytesIO(); doc = SimpleDocTemplate(b, pagesize=landscape(A4), leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30)
    cell = lambda v: Paragraph(str(v), st["BodyText"])
    data = [cols] + [[cell(v) for v in r] for r in rows]
    t = Table(data, repeatRows=1); t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f6feb")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .3, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    doc.build([Paragraph(f"FLOWMATE LOGISTICS - {title}", st["Title"]), Paragraph(sub, st["Normal"]), Spacer(1, 12), t]); return b.getvalue()

@router.get("/{name}")
def report(name: str, fmt: str = "json", date_from: date | None = None, date_to: date | None = None, location_id: int | None = None, period: str = "day",
           db: Session = Depends(get_db), u=Depends(require("reports"))):
    if name not in REPORTS: raise HTTPException(404, "Unknown report")
    a, b = _rng(date_from, date_to)
    fn = REPORTS[name]; title, cols, rows = fn(db, a, b, location_id, period) if name == "sales" else fn(db, a, b, location_id)
    if fmt == "json": return {"title": title, "columns": cols, "rows": rows, "from": str(a), "to": str(b)}
    fname = f"{name}_{a}_{b}"
    if fmt == "csv":
        buf = io.StringIO(); w = csv.writer(buf); w.writerow(cols); w.writerows(rows)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={fname}.csv"})
    if fmt == "xlsx":
        return StreamingResponse(iter([_xlsx(title, cols, rows)]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={fname}.xlsx"})
    if fmt == "pdf":
        return StreamingResponse(iter([_pdf(title, cols, rows, f"Period {a} to {b}")]), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={fname}.pdf"})
    raise HTTPException(422, "fmt must be json, csv, xlsx or pdf")
