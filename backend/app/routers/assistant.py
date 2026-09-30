"""Business assistant. Answers questions from the database using a fixed set of READ-ONLY tools; each tool checks the user's permissions.
Without ANTHROPIC_API_KEY it understands common questions by keywords. With a key, Claude picks the tool and words the answer - it never sees more than the tool returns."""
import json, re, httpx
from datetime import date, timedelta
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from ..config import ANTHROPIC_API_KEY
from ..db import get_db
from ..security import current_user, PERMS
from .. import models

router = APIRouter(prefix="/api/assistant", tags=["assistant"])
eur = lambda c: f"{(c or 0) / 100:,.2f} EUR"

def allowed(user, area): p = PERMS.get(user.role, set()); return "*" in p or area in p

def t_spend_category(db, a):
    m0 = date.today().replace(day=1); cat = (a.get("category") or "").lower()
    q = select(models.Expense.category, func.sum(models.Expense.amount_cents)).where(models.Expense.spent_on >= m0).group_by(models.Expense.category)
    rows = [(c, v) for c, v in db.execute(q) if not cat or cat in c.lower()]
    return {"period": "this month", "spending": {c: eur(v) for c, v in rows}, "total": eur(sum(v for _, v in rows))}

def t_supplier_owed(db, a):
    out = {}
    for i in db.scalars(select(models.Invoice).where(models.Invoice.status != "PAID")): out[i.supplier_id] = out.get(i.supplier_id, 0) + i.total_cents
    rows = sorted(((db.get(models.Supplier, k).name, v) for k, v in out.items()), key=lambda x: -x[1])
    return {"outstanding_by_supplier": [{"supplier": n, "owed": eur(v)} for n, v in rows]}

def t_low_stock(db, a):
    rows = db.execute(select(models.Stock, models.Product).join(models.Product, models.Stock.product_id == models.Product.id).where(models.Stock.quantity <= models.Product.min_stock)).all()
    return {"low_stock": [{"product": p.name, "quantity": s.quantity, "minimum": p.min_stock} for s, p in rows]}

def t_unpaid_invoices(db, a):
    return {"unpaid_invoices": [{"supplier": db.get(models.Supplier, i.supplier_id).name, "number": i.number, "due": str(i.due_date), "amount": eur(i.total_cents), "overdue": bool(i.due_date and i.due_date < date.today())} for i in db.scalars(select(models.Invoice).where(models.Invoice.status != "PAID"))]}

def t_sales(db, a):
    days = {"today": 0, "yesterday": 1, "week": 7, "month": 30}.get(a.get("period", "week"), 7); end = date.today(); start = end - timedelta(days=days)
    if a.get("period") == "yesterday": end = start
    o = sum(x.total_cents for x in db.scalars(select(models.Order).where(models.Order.status != "CANCELLED", func.date(models.Order.created_at) >= start.isoformat(), func.date(models.Order.created_at) <= end.isoformat())))
    m = db.scalar(select(func.coalesce(func.sum(models.SubPayment.amount_cents), 0)).where(models.SubPayment.paid_on >= start, models.SubPayment.paid_on <= end)) or 0
    return {"from": str(start), "to": str(end), "orders": eur(o), "memberships": eur(m), "total": eur(o + m)}

def t_unpaid_customers(db, a):
    agg = {}
    for o in db.scalars(select(models.Order).where(models.Order.status.in_(["NEW", "PROCESSING", "COMPLETED"]))):
        n = db.get(models.Customer, o.customer_id).name if o.customer_id else "(walk-in)"; agg[n] = agg.get(n, 0) + o.total_cents
    return {"customers_with_unpaid_orders": [{"customer": k, "unpaid": eur(v)} for k, v in agg.items()]}

def t_bank_today(db, a):
    rows = db.scalars(select(models.BankTransaction).where(models.BankTransaction.booked_on == date.today()))
    return {"today": [{"amount": eur(t.amount_cents), "reference": t.reference, "status": t.match_status} for t in rows]}

def t_members(db, a):
    from .memberships import summary
    return {"active_members": db.scalar(select(func.count()).select_from(models.Member)) or 0, "note": "see Members screen for expiring and unpaid lists"}

TOOLS = {  # name: (function, required permission area, description, keywords)
    "spend_by_category": (t_spend_category, "reports", "Spending this month, optionally for one category like food", ["spend", "spent", "expense", "cost"]),
    "supplier_balances": (t_supplier_owed, "invoices", "How much is owed to each supplier", ["supplier", "owe", "outstanding"]),
    "low_stock": (t_low_stock, "stock_read", "Products at or below minimum stock", ["low", "stock", "running out"]),
    "unpaid_invoices": (t_unpaid_invoices, "invoices", "Unpaid supplier invoices", ["unpaid invoice", "invoices", "overdue"]),
    "sales": (t_sales, "reports", "Sales for today, yesterday, week or month (arg period)", ["sales", "sold", "revenue", "takings"]),
    "unpaid_customers": (t_unpaid_customers, "orders", "Customers with unpaid orders", ["customers", "haven't paid", "not paid", "owe us"]),
    "bank_today": (t_bank_today, "banking_read", "Today's bank transactions", ["bank", "transactions"]),
}

def pick_by_keywords(q):
    ql = q.lower(); args = {}
    for w, p in (("yesterday", "yesterday"), ("today", "today"), ("last week", "week"), ("week", "week"), ("month", "month")):
        if w in ql: args["period"] = p; break
    m = re.search(r"on (\w+)", ql)
    if m and "spend" in ql or "spent" in ql:
        m2 = re.search(r"(?:on|for) ([a-z ]+?)(?: this| last|\?|$)", ql); args["category"] = (m2.group(1).strip() if m2 else "")
    order = ["unpaid_customers", "unpaid_invoices", "low_stock", "supplier_balances", "bank_today", "spend_by_category", "sales"]
    for name in order:
        if any(k in ql for k in TOOLS[name][3]): return name, args
    return None, args

class Ask(BaseModel): question: str

@router.post("")
def ask(d: Ask, db: Session = Depends(get_db), u=Depends(current_user)):
    avail = {n: t for n, t in TOOLS.items() if allowed(u, t[1])}
    if ANTHROPIC_API_KEY:
        try: return _llm(d.question, avail, db, u)
        except Exception: pass   # fall back to keywords
    name, args = pick_by_keywords(d.question)
    if not name: return {"answer": "I can answer things like: sales this week, spending on food, which supplier we owe most, low stock, unpaid invoices, customers who haven't paid, today's bank transactions.", "data": None}
    if name not in avail: return {"answer": "You don't have permission to see that information.", "data": None}
    data = avail[name][0](db, args); return {"answer": _plain(name, data), "data": data, "tool": name}

def _plain(name, d):
    if name == "sales": return f"Sales {d['from']} to {d['to']}: {d['total']} (orders {d['orders']}, memberships {d['memberships']})."
    if name == "spend_by_category": return f"Spending {d['period']}: {d['total']}. " + ", ".join(f"{k} {v}" for k, v in d["spending"].items())
    if name == "supplier_balances": return "Outstanding: " + ("; ".join(f"{x['supplier']} {x['owed']}" for x in d["outstanding_by_supplier"]) or "nothing owed.")
    if name == "low_stock": return "Low stock: " + (", ".join(f"{x['product']} ({x['quantity']}/{x['minimum']})" for x in d["low_stock"]) or "nothing is low.")
    if name == "unpaid_invoices": return f"{len(d['unpaid_invoices'])} unpaid invoice(s): " + "; ".join(f"{x['supplier']} {x['number']} {x['amount']} due {x['due']}" + (" OVERDUE" if x["overdue"] else "") for x in d["unpaid_invoices"])
    if name == "unpaid_customers": return "Unpaid orders: " + ("; ".join(f"{x['customer']} {x['unpaid']}" for x in d["customers_with_unpaid_orders"]) or "none.")
    if name == "bank_today": return "Today's bank transactions: " + ("; ".join(f"{x['amount']} {x['reference']} ({x['status']})" for x in d["today"]) or "none yet.")
    return json.dumps(d)

def _llm(question, avail, db, u):
    tools = [{"name": n, "description": t[2], "input_schema": {"type": "object", "properties": {"period": {"type": "string"}, "category": {"type": "string"}}}} for n, t in avail.items()]
    H = {"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"}; msgs = [{"role": "user", "content": question}]
    sys = "You are the FLOWMATE business assistant for a small business. Use tools to get facts; never invent numbers. Answer briefly. If no tool fits, say what you can answer."
    last = None
    for _ in range(3):
        r = httpx.post("https://api.anthropic.com/v1/messages", headers=H, timeout=40, json={"model": "claude-sonnet-4-5", "max_tokens": 600, "system": sys, "tools": tools, "messages": msgs}); r.raise_for_status(); j = r.json()
        if j["stop_reason"] != "tool_use": return {"answer": "".join(b.get("text", "") for b in j["content"]).strip(), "data": last}
        msgs.append({"role": "assistant", "content": j["content"]}); res = []
        for b in j["content"]:
            if b["type"] == "tool_use":
                out = avail[b["name"]][0](db, b["input"]) if b["name"] in avail else {"error": "not permitted"}; last = out
                res.append({"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(out)})
        msgs.append({"role": "user", "content": res})
    return {"answer": "Sorry, I couldn't finish that.", "data": last}
