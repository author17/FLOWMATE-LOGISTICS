import io, json, zipfile, sqlite3
from datetime import date, timedelta
from test_flow import c, owner, cashier, payer, login, SessionLocal, get_provider
from app import models
from app.security import totp_code
from app.db import engine

def hdr(tok): return {"Authorization": "Bearer " + tok}

def test_mfa_full_cycle_and_reset():
    r = c.post("/api/users", headers=owner, json={"name": "M", "email": "mfa@demo.com", "role": "manager", "password": "demo12345xx"})
    assert r.status_code in (200, 201), r.text
    uid = r.json()["id"]
    tok = c.post("/api/auth/login", data={"username": "mfa@demo.com", "password": "demo12345xx"}).json()["access_token"]
    sec = c.post("/api/auth/mfa/setup", headers=hdr(tok)).json()["secret"]
    assert c.post("/api/auth/mfa/enable", headers=hdr(tok), json={"code": "000000"}).status_code == 422
    codes = c.post("/api/auth/mfa/enable", headers=hdr(tok), json={"code": totp_code(sec)}).json()["recovery_codes"]
    r = c.post("/api/auth/login", data={"username": "mfa@demo.com", "password": "demo12345xx"}); assert "MFA_REQUIRED" in r.text
    assert c.post("/api/auth/login", data={"username": "mfa@demo.com", "password": "demo12345xx", "otp": "123456"}).status_code == 401
    assert c.post("/api/auth/login", data={"username": "mfa@demo.com", "password": "demo12345xx", "otp": totp_code(sec)}).status_code == 200
    assert c.post("/api/auth/login", data={"username": "mfa@demo.com", "password": "demo12345xx", "otp": codes[0]}).status_code == 200
    assert c.post("/api/auth/login", data={"username": "mfa@demo.com", "password": "demo12345xx", "otp": codes[0]}).status_code == 401  # one-time
    assert c.post(f"/api/users/{uid}/reset-mfa", headers=owner).status_code == 200
    assert c.post("/api/auth/login", data={"username": "mfa@demo.com", "password": "demo12345xx"}).status_code == 200

def test_logout_all_revokes_tokens():
    t = c.post("/api/auth/login", data={"username": "driver@demo.com", "password": "demo12345"}).json()["access_token"]
    assert c.get("/api/auth/me", headers=hdr(t)).status_code == 200
    assert c.post("/api/auth/logout-all", headers=hdr(t)).status_code == 200
    assert c.get("/api/auth/me", headers=hdr(t)).status_code == 401

def test_iban_encrypted_at_rest():
    r = c.post("/api/suppliers", headers=owner, json={"name": "Enc Ltd", "iban": "CY17 0020 0128 0000 0012 0052 7600", "email": "enc@x.com"})
    assert r.status_code == 201, r.text
    assert r.json()["iban"] == "CY17002001280000001200527600"
    from sqlalchemy import text
    with engine.connect() as cn: raw = cn.execute(text("select iban from suppliers where id=:i"), {"i": r.json()["id"]}).scalar()
    assert raw.startswith("enc1:") and "CY17" not in raw
    assert c.post("/api/suppliers", headers=owner, json={"name": "Bad", "iban": "CY00 1234"}).status_code == 422

def test_location_scoping_for_cashier():
    me = c.get("/api/auth/me", headers=cashier).json(); loc = me["location_id"]; assert loc
    other = 1 if loc != 1 else 3
    prods = c.get("/api/products", headers=owner).json()
    o = c.post("/api/orders", headers=cashier, json={"location_id": other, "items": [{"product_id": prods[0]["id"], "quantity": 1}]}).json()
    assert o["location_id"] == loc                                   # forced to own location
    assert all(x["location_id"] == loc for x in c.get("/api/orders", headers=cashier, params={"location_id": other}).json())
    assert all(x["location_id"] == loc for x in c.get("/api/stock", headers=cashier, params={"location_id": other}).json())
    m = c.post("/api/members", headers=owner, json={"name": "Other Site", "location_id": other}).json()
    assert c.post(f"/api/members/{m['id']}/checkin", headers=cashier, json={}).status_code == 403
    assert all(x["location_id"] in (loc, None) for x in c.get("/api/members", headers=cashier).json())

def test_stock_transfer_and_movements():
    p = c.get("/api/products", headers=owner).json()[0]
    c.post("/api/stock/adjust", headers=owner, json={"product_id": p["id"], "location_id": 1, "change": 50, "reason": "count"})
    assert c.post("/api/stock/transfer", headers=owner, json={"product_id": p["id"], "from_location_id": 1, "to_location_id": 1, "quantity": 5}).status_code == 422
    assert c.post("/api/stock/transfer", headers=owner, json={"product_id": p["id"], "from_location_id": 1, "to_location_id": 2, "quantity": 10**6}).status_code == 409
    assert c.post("/api/stock/transfer", headers=owner, json={"product_id": p["id"], "from_location_id": 1, "to_location_id": 2, "quantity": 5}).status_code == 200
    mv = c.get("/api/stock/movements", headers=owner, params={"product_id": p["id"]}).json()
    assert {"transfer_out", "transfer_in"} <= {m["reason"] for m in mv}

def test_purchase_order_create_pdf_send_and_invoice_link():
    sup = c.get("/api/suppliers", headers=owner).json()[0]; p = c.get("/api/products", headers=owner).json()[0]
    assert c.post("/api/purchase-orders", headers=owner, json={"supplier_id": sup["id"], "location_id": 1, "items": []}).status_code == 422
    po = c.post("/api/purchase-orders", headers=owner, json={"supplier_id": sup["id"], "location_id": 1, "items": [{"product_id": p["id"], "quantity": 10}]}).json()
    assert po["total_cents"] == 10 * p["purchase_cents"]
    pdf = c.get(f"/api/purchase-orders/{po['id']}/pdf", headers=owner); assert pdf.content[:4] == b"%PDF"
    assert c.post(f"/api/purchase-orders/{po['id']}/send", headers=owner).status_code == 409   # no smtp in tests
    before = {(s["product_id"], s["location_id"]): s["quantity"] for s in c.get("/api/stock", headers=owner).json()}
    c.put(f"/api/purchase-orders/{po['id']}/status", headers=owner, json={"status": "RECEIVED"})
    mid = {(s["product_id"], s["location_id"]): s["quantity"] for s in c.get("/api/stock", headers=owner).json()}
    assert mid[(p["id"], 1)] == before.get((p["id"], 1), 0) + 10
    inv = c.post("/api/invoices", headers=owner, json={"supplier_id": sup["id"], "number": "PO-LINK-1", "issue_date": "2026-09-30", "total_cents": 1000, "location_id": 1, "purchase_order_id": po["id"], "add_to_stock": True,
                                                       "items": [{"product_id": p["id"], "quantity": 10, "unit_cents": 100}]})
    assert inv.status_code == 201, inv.text
    after = {(s["product_id"], s["location_id"]): s["quantity"] for s in c.get("/api/stock", headers=owner).json()}
    assert after[(p["id"], 1)] == mid[(p["id"], 1)]                               # no double stock
    assert [x for x in c.get("/api/purchase-orders/full", headers=owner).json() if x["id"] == po["id"]][0]["status"] == "INVOICED"

def test_till_csv_import_dedupes():
    csvt = "date,amount,method,description\n2026-09-29,1234.50,CARD,Z report\n29/09/2026,80,cash,Cash sales\nbroken,row,x\n"
    r = c.post("/api/orders/import-csv", headers=owner, data={"location_id": 1}, files={"file": ("z.csv", csvt)}).json()
    assert r["added"] == 2 and len(r["errors"]) == 1
    assert c.post("/api/orders/import-csv", headers=owner, data={"location_id": 1}, files={"file": ("z.csv", csvt)}).json()["added"] == 0

def test_public_orders():
    assert c.get("/api/public/menu").status_code == 404            # off by default
    assert c.get("/order").status_code == 200
    c.put("/api/settings", headers=owner, json={"public_orders_enabled": True})
    prod = c.get("/api/products", headers=owner).json()[0]
    c.put(f"/api/products/{prod['id']}", headers=owner, json={"show_online": True})
    menu = c.get("/api/public/menu").json(); assert any(m["id"] == prod["id"] for m in menu["products"])
    body = {"name": "Nick", "phone": "99", "location_id": 1, "items": [{"product_id": prod["id"], "quantity": 2}]}
    r = c.post("/api/public/orders", json=body); assert r.status_code == 201, r.text
    assert r.json()["total_cents"] == 2 * prod["sell_cents"]
    hidden = [p for p in c.get("/api/products", headers=owner).json() if p["id"] != prod["id"] and not p["show_online"]][0]
    assert c.post("/api/public/orders", json={**body, "items": [{"product_id": hidden["id"], "quantity": 1}]}).status_code == 422
    assert c.post("/api/public/orders", json={**body, "name": ""}).status_code == 422
    codes = [c.post("/api/public/orders", json=body).status_code for _ in range(12)]
    assert 429 in codes

def test_inbound_email_needs_token(monkeypatch):
    from app import config; monkeypatch.setattr(config, "INBOUND_EMAIL_TOKEN", "tok123")
    assert c.post("/api/inbound/email?token=nope", files={"a": ("i.pdf", b"%PDF")}).status_code == 403
    r = c.post("/api/inbound/email?token=tok123", data={"from": "sup@x.com"}, files={"a": ("i.pdf", b"%PDF-1"), "b": ("x.exe", b"MZ")})
    assert r.status_code == 201 and r.json()["documents"] == 1
    assert any(d["source"] == "email" for d in c.get("/api/documents", headers=owner).json())

def test_document_library_update_and_filters():
    d = c.post("/api/documents/scan", headers=owner, files={"file": ("lib.jpg", b"x")}, data={"doc_type": "delivery_note"}).json()
    assert d["doc_type"] == "delivery_note"
    u = c.put(f"/api/documents/{d['id']}", headers=owner, json={"company": "ACME", "amount_cents": 1234, "reference": "DN-9", "doc_date": "2026-09-01", "status": "VERIFIED"}).json()
    assert u["company"] == "ACME" and u["status"] == "VERIFIED"
    assert c.put(f"/api/documents/{d['id']}", headers=owner, json={"doc_type": "nonsense"}).status_code == 422
    assert [x["id"] for x in c.get("/api/documents", headers=owner, params={"q": "acme"}).json()] == [d["id"]]
    assert c.put(f"/api/documents/{d['id']}", headers=cashier, json={"company": "x"}).status_code in (200, 403)

def test_payment_reject_and_statement_completion():
    sup = c.get("/api/suppliers", headers=owner).json()[0]
    inv = c.post("/api/invoices", headers=owner, json={"supplier_id": sup["id"], "number": "PAY-2", "issue_date": "2026-09-30", "total_cents": 7777}).json()
    p = c.post("/api/payments", headers=payer, json={"invoice_id": inv["id"], "account_id": 1}).json()
    assert c.post(f"/api/payments/{p['id']}/reject", headers=payer, json={}).status_code == 403
    assert c.post(f"/api/payments/{p['id']}/reject", headers=owner, json={"reason": "wrong"}).json()["status"] == "CANCELLED"
    p2 = c.post("/api/payments", headers=payer, json={"invoice_id": inv["id"], "account_id": 1}).json()
    assert c.post(f"/api/payments/{p2['id']}/approve", headers=owner).json()["status"] in ("AUTHORIZATION_REQUIRED", "APPROVED")
    csvt = f"date,amount,reference,counterparty\n30/09/2026,-77.77,{sup['name']} PAY-2,{sup['name']}\n"
    c.post("/api/bank/accounts/1/import-csv", headers=owner, files={"file": ("s.csv", csvt)})
    pays = {x["id"]: x for x in c.get("/api/payments", headers=owner).json()}
    assert pays[p2["id"]]["status"] == "COMPLETED"

def test_due_reminders_and_email_jobs(monkeypatch):
    from app.services import notify_jobs, mailer
    sup = c.get("/api/suppliers", headers=owner).json()[0]
    c.post("/api/invoices", headers=owner, json={"supplier_id": sup["id"], "number": "OVR-1", "issue_date": "2026-08-01", "due_date": str(date.today() - timedelta(days=5)), "total_cents": 500})
    with SessionLocal() as db:
        assert notify_jobs.due_reminders(db) >= 1
        assert notify_jobs.due_reminders(db) == 0               # de-duplicated
        sent = []
        monkeypatch.setattr(mailer, "configured", lambda: True)
        monkeypatch.setattr(mailer, "send_email", lambda to, s, b, a=None: sent.append((to, s)) or True)
        assert notify_jobs.email_pending(db) >= 1 and sent and "owner@demo.com" in sent[0][0]
        assert notify_jobs.email_pending(db) == 0

def test_backup_and_exports_hide_secrets():
    r = c.post("/api/backups/run", headers=owner); assert r.status_code == 201
    name = r.json()["name"]; z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/backups/{name}", headers=owner).content))
    assert "data/users.csv" in z.namelist()
    users = z.read("data/users.csv").decode(); assert "password_hash" not in users.splitlines()[0] and "pbkdf2" not in users
    assert c.get("/api/backups/../../etc/passwd", headers=owner).status_code in (404, 422)
    assert c.get("/api/backups", headers=cashier).status_code == 403
    allz = zipfile.ZipFile(io.BytesIO(c.get("/api/export/all.zip", headers=owner).content)); assert "data/invoices.csv" in allz.namelist()
    assert c.get("/api/export/documents.zip", headers=owner).status_code == 200
    assert c.get("/api/export/all.zip", headers=payer).status_code == 403

def test_dashboard_extras():
    d = c.get("/api/dashboard", headers=owner).json()
    assert len(d["sales_by_day"]) == 14 and "pending_payments" in d and "incoming_today_cents" in d

def test_cockpit_has_actions():
    d = c.get("/api/cockpit", headers=owner).json()
    assert {"attention", "low_stock", "logistics", "bank", "activity", "kpi", "finance"} <= set(d)
    assert all({"level", "text", "tab", "action"} <= set(a) for a in d["attention"])
    assert len(d["finance"]["weeks"]) == 4
    assert c.get("/api/cockpit", headers=cashier).status_code == 403

def test_assistant_control_room_questions():
    a = lambda q: c.post("/api/assistant", headers=owner, json={"question": q}).json()["answer"]
    assert a("What needs my attention today?").startswith("Needs attention")
    assert a("What do I need to order?").startswith("To order")
    assert "ABC" in a("Did ABC Foods get paid?") or "No matching" in a("Did ABC Foods get paid?")
    assert "permission" in c.post("/api/assistant", headers=cashier, json={"question": "What needs my attention today?"}).json()["answer"]

def test_search_eta_and_driver_phone():
    r = c.get("/api/search", headers=owner, params={"q": "ABC"}).json(); assert any(x["kind"] == "Supplier" for x in r)
    assert c.get("/api/search", headers=cashier, params={"q": "ABC"}).json() == [] or all(x["kind"] != "Supplier" for x in c.get("/api/search", headers=cashier, params={"q": "ABC"}).json())
    drv = [u for u in c.get("/api/users", headers=owner).json() if u["role"] == "driver"][0]
    assert c.put(f"/api/users/{drv['id']}", headers=owner, json={"phone": "+35799111222"}).status_code == 200
    prods = c.get("/api/products", headers=owner).json()
    o = c.post("/api/orders", headers=owner, json={"location_id": 2, "items": [{"product_id": prods[0]["id"], "quantity": 1}]}).json()
    d = c.post("/api/deliveries", headers=owner, json={"order_id": o["id"], "address": "X", "eta": "14:30"}).json(); assert d["eta"] == "14:30"
    c.put(f"/api/deliveries/{d['id']}/assign", headers=owner, json={"driver_id": drv["id"]})
    assert c.put(f"/api/deliveries/{d['id']}/eta", headers=owner, json={"eta": "25:99"}).status_code == 422
    assert c.put(f"/api/deliveries/{d['id']}/eta", headers=owner, json={"eta": "15:10"}).json()["driver_phone"] == "+35799111222"
    assert [x for x in c.get("/api/cockpit", headers=owner).json()["logistics"]["active"] if x["id"] == d["id"]][0]["eta"] == "15:10"
