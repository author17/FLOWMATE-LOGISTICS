import os, tempfile
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tempfile.mkdtemp()}/t.db"
os.environ["STORAGE_DIR"] = tempfile.mkdtemp()
os.environ["DEMO_MODE"] = "1"; os.environ["DISABLE_SCHEDULER"] = "1"
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.banking import get_provider
import seed as seedmod

seedmod.seed(SessionLocal())
c = TestClient(app)

def login(email):
    r = c.post("/api/auth/login", data={"username": email, "password": "demo12345"}); assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}

owner, cashier, payer = login("owner@demo.com"), login("cashier@demo.com"), login("payer@demo.com")

def test_bad_login():
    assert c.post("/api/auth/login", data={"username": "owner@demo.com", "password": "x"}).status_code == 401

def test_permissions():
    assert c.get("/api/invoices", headers=cashier).status_code == 403
    assert c.get("/api/users", headers=cashier).status_code == 403
    assert c.get("/api/orders", headers=cashier).status_code == 200

def test_order_reduces_stock_and_bank_match():
    prods = {p["sku"]: p for p in c.get("/api/products", headers=owner).json()}
    o = c.post("/api/orders", headers=owner, json={"location_id": 2, "items": [{"product_id": prods["COF1"]["id"], "quantity": 20}, {"product_id": prods["WAT1"]["id"], "quantity": 12}]}).json()
    assert o["total_cents"] == 20 * 250 + 12 * 100
    st = {s["sku"]: s for s in c.get("/api/stock", headers=owner).json()}
    assert st["COF1"]["quantity"] == 20
    csv = f"date,amount,reference,counterparty\n30/09/2026,{o['total_cents']/100:.2f},ORDER-{o['id']},Maria\n30/09/2026,12.34,random thing,Someone\n"
    r = c.post("/api/bank/accounts/1/import-csv", headers=owner, files={"file": ("s.csv", csv)}).json()
    assert r["added"] == 2 and r["matching"]["reconciled"] == 1 and r["matching"]["unmatched"] == 1
    assert [x for x in c.get("/api/orders", headers=owner).json() if x["id"] == o["id"]][0]["status"] == "PAID"
    # re-import same file: duplicates skipped
    assert c.post("/api/bank/accounts/1/import-csv", headers=owner, files={"file": ("s.csv", csv)}).json()["added"] == 0

def test_cashup_difference():
    s = c.post("/api/shifts/open", headers=cashier, json={"location_id": 2, "opening_float_cents": 10000}).json()
    r = c.post(f"/api/shifts/{s['id']}/close", headers=cashier, json={"cash_sales_cents": 50000, "counted_cash_cents": 59500}).json()
    assert r["expected_cash_cents"] == 60000 and r["difference_cents"] == -500
    assert any("cash difference" in n["message"] for n in c.get("/api/notifications", headers=owner).json())

def test_payment_never_completed_without_bank():
    inv = [i for i in c.get("/api/invoices", headers=owner).json() if i["number"] == "INV-5521"][0]
    p = c.post("/api/payments", headers=payer, json={"invoice_id": inv["id"], "account_id": 1}).json()
    assert p["status"] == "PENDING"
    assert c.post(f"/api/payments/{p['id']}/approve", headers=payer).status_code == 403   # preparer cannot approve
    p = c.post(f"/api/payments/{p['id']}/approve", headers=owner).json()
    assert p["status"] == "AUTHORIZATION_REQUIRED" and p["authorization_url"]
    assert c.post(f"/api/payments/{p['id']}/refresh", headers=payer).json()["status"] == "AUTHORIZATION_REQUIRED"
    get_provider("sandbox").simulate_bank_approval(p["provider_ref"])
    assert c.post(f"/api/payments/{p['id']}/refresh", headers=payer).json()["status"] == "COMPLETED"
    assert [i for i in c.get("/api/invoices", headers=owner).json() if i["id"] == inv["id"]][0]["status"] == "PAID"
    assert any(a["action"] == "payment_status_change" for a in c.get("/api/audit", headers=owner).json())

def test_duplicate_invoice_blocked_and_low_stock_po():
    body = {"supplier_id": 1, "number": "INV-5521", "issue_date": "2026-09-01", "total_cents": 1}
    assert c.post("/api/invoices", headers=owner, json=body).status_code == 409
    po = c.post("/api/purchase-orders/from-low-stock/2", headers=owner).json()
    assert any(i["quantity"] > 0 for p in po for i in p["items"])  # milk is below min after stock drops? at least endpoint works

def test_scan_and_export_and_dashboard():
    r = c.post("/api/documents/scan", headers=owner, files={"file": ("r.jpg", b"\xff\xd8\xff fakejpg")}, data={"doc_type": "receipt"})
    assert r.status_code == 201 and r.json()["status"] == "NEEDS_REVIEW"
    assert c.post("/api/documents/scan", headers=owner, files={"file": ("r.exe", b"x")}).status_code == 415
    assert c.get("/api/export/invoices.csv", headers=owner).text.startswith("id,")
    d = c.get("/api/dashboard", headers=owner).json()
    assert d["documents_to_verify"] == 1 and len(d["by_location"]) == 4

def test_delivery_flow():
    driver = login("driver@demo.com")
    prods = c.get("/api/products", headers=owner).json()
    o = c.post("/api/orders", headers=owner, json={"location_id": 2, "items": [{"product_id": prods[1]["id"], "quantity": 1}]}).json()
    d = c.post("/api/deliveries", headers=owner, json={"order_id": o["id"], "address": "Main St 1, Limassol"}).json()
    assert c.post("/api/deliveries", headers=owner, json={"order_id": o["id"]}).status_code == 409   # one delivery per order
    assert c.put(f"/api/deliveries/{d['id']}/status", headers=owner, json={"status": "ON_THE_WAY"}).status_code == 422  # no driver yet
    drv = c.get("/api/deliveries/drivers", headers=owner).json()[0]
    assert c.put(f"/api/deliveries/{d['id']}/assign", headers=owner, json={"driver_id": drv["id"]}).status_code == 200
    assert c.put(f"/api/deliveries/{d['id']}/status", headers=driver, json={"status": "DELIVERED"}).status_code == 409  # must be on the way first
    assert c.put(f"/api/deliveries/{d['id']}/status", headers=driver, json={"status": "ON_THE_WAY"}).status_code == 200
    assert len(c.get("/api/deliveries", headers=driver).json()) == 1      # driver sees only own jobs
    assert c.get("/api/orders", headers=driver).status_code == 403        # and nothing else
    assert c.get("/api/invoices", headers=driver).status_code == 403
    r = c.put(f"/api/deliveries/{d['id']}/status", headers=driver, json={"status": "DELIVERED"}).json()
    assert r["status"] == "DELIVERED" and r["delivered_at"]
    assert [x for x in c.get("/api/orders", headers=owner).json() if x["id"] == o["id"]][0]["status"] == "COMPLETED"
    assert c.get("/api/dashboard", headers=owner).json()["deliveries_active"] == 0

def test_password_change_and_lockout():
    h = login("manager@demo.com")
    assert c.post("/api/auth/change-password", headers=h, json={"old_password": "wrong", "new_password": "longenough123"}).status_code == 401
    assert c.post("/api/auth/change-password", headers=h, json={"old_password": "demo12345", "new_password": "short"}).status_code == 422
    assert c.post("/api/auth/change-password", headers=h, json={"old_password": "demo12345", "new_password": "a-better-pass-99"}).status_code == 200
    assert c.post("/api/auth/login", data={"username": "manager@demo.com", "password": "demo12345"}).status_code == 401
    for _ in range(5): c.post("/api/auth/login", data={"username": "accountant@demo.com", "password": "bad"})
    assert c.post("/api/auth/login", data={"username": "accountant@demo.com", "password": "demo12345"}).status_code == 429

def test_bootstrap_creates_owner_once():
    import os
    from app.bootstrap import bootstrap
    from app import models
    from app.db import engine, Base
    os.environ.update({"BOOTSTRAP_OWNER_EMAIL": "Real@Owner.com", "BOOTSTRAP_OWNER_PASSWORD": "Temp-Pass-12345"})
    db = SessionLocal(); before = db.query(models.User).count(); bootstrap()
    assert db.query(models.User).count() == before   # users exist -> does nothing

# ---------------- v0.4 ----------------
def test_memberships_flow():
    plans = c.get("/api/plans", headers=owner).json(); monthly = [p for p in plans if p["name"] == "Monthly membership"][0]; pack = [p for p in plans if p["kind"] == "class_pack"][0]
    m = c.post("/api/members", headers=cashier, json={"name": "Test Member", "location_id": 1}).json()
    assert m["status"] == "NO_PLAN"
    assert c.post(f"/api/members/{m['id']}/checkin", headers=cashier, json={}).status_code == 409           # no plan -> no entry
    s = c.post(f"/api/members/{m['id']}/subscriptions", headers=cashier, json={"plan_id": monthly["id"], "pay_cents": 2000}).json()
    assert s["balance_cents"] == 2500 and s["state"] == "ACTIVE"
    assert c.post(f"/api/members/{m['id']}/subscriptions", headers=cashier, json={"plan_id": monthly["id"], "pay_cents": 999999}).status_code == 422
    ci = c.post(f"/api/members/{m['id']}/checkin", headers=cashier, json={}).json(); assert ci["warnings"]    # unpaid balance warning
    assert c.post(f"/api/subscriptions/{s['id']}/payments", headers=cashier, json={"amount_cents": 2500}).json()["balance_cents"] == 0
    assert c.post(f"/api/subscriptions/{s['id']}/payments", headers=cashier, json={"amount_cents": 1}).status_code == 422  # overpay blocked
    assert c.post("/api/plans", headers=cashier, json={"name": "x"}).status_code == 403                       # cashier cannot create plans
    renew = c.post(f"/api/members/{m['id']}/subscriptions", headers=owner, json={"plan_id": monthly["id"]}).json()
    assert renew["start_on"] > s["end_on"]                                                                       # early renewal extends, no lost days
    p = c.post(f"/api/members/{m['id']}/subscriptions", headers=owner, json={"plan_id": pack["id"], "pay_cents": 6000}).json()
    assert c.get("/api/memberships/summary", headers=owner).json()["revenue_month_cents"] >= 8500

def test_reports_all_formats():
    for name in ["sales", "expenses", "suppliers", "outstanding", "customers", "bank", "cashflow", "vat", "stock", "products", "pnl", "shifts"]:
        r = c.get(f"/api/reports/{name}?fmt=json", headers=owner); assert r.status_code == 200, name
    assert c.get("/api/reports/sales?fmt=xlsx", headers=owner).content[:2] == b"PK"
    assert c.get("/api/reports/vat?fmt=pdf", headers=owner).content[:4] == b"%PDF"
    assert "Period" in c.get("/api/reports/sales?fmt=csv", headers=owner).text
    assert c.get("/api/reports/sales", headers=cashier).status_code == 403

def test_stripe_webhook_security_and_flow(monkeypatch):
    import hmac, hashlib, time, json
    from app import config
    from app.services import stripe_service as st
    config.STRIPE_SECRET_KEY = "sk_test_x"; config.STRIPE_WEBHOOK_SECRET = "whsec_test"
    monkeypatch.setattr(st, "create_checkout", lambda amount, name, tt, tid, email=None: {"id": f"cs_{tt}_{tid}", "url": "https://checkout.stripe.test/x"})
    prods = c.get("/api/products", headers=owner).json()
    o = c.post("/api/orders", headers=owner, json={"location_id": 2, "items": [{"product_id": prods[1]["id"], "quantity": 2}]}).json()
    link = c.post("/api/stripe/checkout", headers=cashier, json={"target_type": "order", "target_id": o["id"]}).json(); assert link["url"]
    def send(body, secret="whsec_test", t=None):
        raw = json.dumps(body).encode(); t = t or int(time.time()); sig = hmac.new(secret.encode(), f"{t}.".encode() + raw, hashlib.sha256).hexdigest()
        return c.post("/api/stripe/webhook", content=raw, headers={"stripe-signature": f"t={t},v1={sig}"})
    ev = lambda amt: {"type": "checkout.session.completed", "data": {"object": {"id": link["session_id"], "payment_status": "paid", "amount_total": amt, "currency": "eur"}}}
    assert send(ev(o["total_cents"]), secret="wrong").status_code == 400                      # forged signature rejected
    assert send(ev(o["total_cents"]), t=int(time.time()) - 4000).status_code == 400          # replayed old event rejected
    assert send(ev(1)).json().get("ok")                                                        # wrong amount -> mismatch, NOT paid
    assert [x for x in c.get("/api/orders", headers=owner).json() if x["id"] == o["id"]][0]["status"] != "PAID"
    o2 = c.post("/api/orders", headers=owner, json={"location_id": 2, "items": [{"product_id": prods[1]["id"], "quantity": 1}]}).json()
    link = c.post("/api/stripe/checkout", headers=cashier, json={"target_type": "order", "target_id": o2["id"]}).json()
    assert send(ev(o2["total_cents"])).json().get("ok"); assert send(ev(o2["total_cents"])).status_code == 200   # duplicate delivery is harmless
    assert [x for x in c.get("/api/orders", headers=owner).json() if x["id"] == o2["id"]][0]["status"] == "PAID"
    assert c.post("/api/stripe/checkout", headers=cashier, json={"target_type": "order", "target_id": o2["id"]}).status_code == 409   # already paid
    config.STRIPE_SECRET_KEY = ""

def test_assistant_permissions():
    assert "EUR" in c.post("/api/assistant", headers=owner, json={"question": "What were our sales last week?"}).json()["answer"]
    assert "Low stock" in c.post("/api/assistant", headers=owner, json={"question": "Which products are running low?"}).json()["answer"]
    assert "permission" in c.post("/api/assistant", headers=cashier, json={"question": "How much do we owe each supplier?"}).json()["answer"]

def test_user_admin():
    uid = [u for u in c.get("/api/users", headers=owner).json() if u["email"] == "payer@demo.com"][0]["id"]
    assert c.put(f"/api/users/{uid}", headers=cashier, json={"active": False}).status_code == 403
    assert c.put(f"/api/users/{uid}", headers=owner, json={"role": "hacker"}).status_code == 422
    assert c.post(f"/api/users/{uid}/reset-password", headers=owner, json={"temp_password": "short"}).status_code == 422

def test_every_role_can_load_locations():
    for who in (cashier, payer, login("driver@demo.com"), owner):
        assert c.get("/api/locations", headers=who).status_code == 200
    assert c.post("/api/locations", headers=cashier, json={"name": "x"}).status_code == 403


# ---------------- bank connection portal ----------------
def test_bank_portal_demo_flow():
    assert c.get("/api/bank/status", headers=owner).json()["provider"] == "demo"
    assert c.get("/api/bank/institutions", headers=cashier).status_code == 403
    assert c.post("/api/bank/connections", headers=cashier, json={"institution": "x"}).status_code == 403
    inst = c.get("/api/bank/institutions?country=CY", headers=owner).json(); assert inst
    r = c.post("/api/bank/connections", headers=owner, json={"institution": inst[0]["name"]}).json()
    state = r["authorization_url"].split("state=")[1]
    assert c.get(f"/api/bank/callback?code=demo&state=forged.abc", follow_redirects=False).headers["location"].startswith("/?bank=failed")
    ok = c.get(f"/api/bank/callback?code=demo&state={state}", follow_redirects=False); assert ok.headers["location"] == "/?bank=connected"
    assert c.get(f"/api/bank/callback?code=demo&state={state}", follow_redirects=False).headers["location"].startswith("/?bank=failed")   # one-time link
    conns = c.get("/api/bank/connections", headers=payer).json(); assert conns[0]["status"] == "ACTIVE" and conns[0]["accounts"][0]["balance_cents"] == 1245000
    assert "state" not in conns[0] and "session_id" not in conns[0]          # secrets never sent to the browser
    n = len(c.get("/api/bank/transactions", headers=owner).json()); assert n > 0
    assert c.post(f"/api/bank/connections/{conns[0]['id']}/sync", headers=owner).json()["added"] == 0   # no duplicates
    assert c.post(f"/api/bank/connections/{conns[0]['id']}/sync", headers=cashier).status_code == 403
    assert c.delete(f"/api/bank/connections/{conns[0]['id']}", headers=owner).json()["ok"]
    assert c.get("/api/bank/connections", headers=owner).json() == []
    assert len(c.get("/api/bank/transactions", headers=owner).json()) == n                              # history kept

def test_bank_expired_consent_and_reconnect():
    from datetime import datetime, timedelta
    from app.db import SessionLocal; from app import models
    r = c.post("/api/bank/connections", headers=owner, json={"institution": "Demo Bank (practice)"}).json()
    c.get(f"/api/bank/callback?code=demo&state={r['authorization_url'].split('state=')[1]}", follow_redirects=False)
    db = SessionLocal(); conn = db.query(models.BankConnection).filter_by(status="ACTIVE").first(); conn.consent_expires_at = datetime.utcnow() - timedelta(days=1); db.commit(); cid = conn.id; db.close()
    assert c.post(f"/api/bank/connections/{cid}/sync", headers=owner).status_code == 502
    lst = c.get("/api/bank/connections", headers=owner).json(); assert lst[0]["status"] == "EXPIRED" and lst[0]["needs_reconnect"]
    assert any("Bank connection problem" in n["message"] for n in c.get("/api/notifications", headers=owner).json())
    rc = c.post(f"/api/bank/connections/{cid}/reconnect", headers=owner).json()
    c.get(f"/api/bank/callback?code=demo&state={rc['authorization_url'].split('state=')[1]}", follow_redirects=False)
    assert c.get("/api/bank/connections", headers=owner).json()[0]["status"] == "ACTIVE"

def test_enable_banking_provider_mapping():
    import httpx, jwt, json
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from app.services.openbanking import EnableBankingProvider
    from datetime import date
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    pub = key.public_key(); seen = {}
    def handler(req):
        tok = req.headers["authorization"].split()[1]; hdr = jwt.get_unverified_header(tok); claims = jwt.decode(tok, pub, algorithms=["RS256"], audience="api.enablebanking.com")
        assert hdr["kid"] == "app-123" and claims["iss"] == "enablebanking.com"
        p = req.url.path
        if p == "/aspsps": return httpx.Response(200, json={"aspsps": [{"name": "Eurobank", "country": "CY", "maximum_consent_validity": 7776000}]})
        if p == "/auth": body = json.loads(req.content); seen["auth"] = body; return httpx.Response(200, json={"url": "https://bank.example/consent", "authorization_id": "a1"})
        if p == "/sessions" and req.method == "POST": return httpx.Response(200, json={"session_id": "s1", "accounts": [{"uid": "u1", "account_id": {"iban": "CY17002001280000001200527600"}, "currency": "EUR"}], "access": {"valid_until": "2026-12-31T00:00:00Z"}})
        if p.endswith("/balances"): return httpx.Response(200, json={"balances": [{"balance_type": "ITAV", "balance_amount": {"amount": "990.50"}}, {"balance_type": "CLBD", "balance_amount": {"amount": "1000.00"}}]})
        if p.endswith("/transactions"):
            if "continuation_key" not in req.url.params: return httpx.Response(200, json={"transactions": [{"entry_reference": "e1", "transaction_amount": {"amount": "85.00"}, "credit_debit_indicator": "CRDT", "booking_date": "2026-09-30", "remittance_information": ["ORDER-1048"], "debtor": {"name": "Maria"}}], "continuation_key": "k2"})
            return httpx.Response(200, json={"transactions": [{"entry_reference": "e2", "transaction_amount": {"amount": "450.00"}, "credit_debit_indicator": "DBIT", "booking_date": "2026-09-29", "remittance_information": ["INV-5521"], "creditor": {"name": "ABC FOODS"}}]})
        if req.method == "DELETE": return httpx.Response(204)
        return httpx.Response(404)
    pr = EnableBankingProvider("app-123", pem, httpx.Client(transport=httpx.MockTransport(handler)))
    assert pr.institutions("CY")[0]["name"] == "Eurobank"
    a = pr.start_auth("Eurobank", "CY", "business", "st", "https://x/cb", 90); assert a["url"] and seen["auth"]["psu_type"] == "business" and seen["auth"]["aspsp"]["name"] == "Eurobank"
    s = pr.create_session("code"); assert s["accounts"][0]["iban"].startswith("CY17") and s["valid_until"].year == 2026
    assert pr.balances("u1") == {"booked": 100000, "available": 99050}
    tx = pr.transactions("u1", date(2026, 9, 1)); assert [t["amount_cents"] for t in tx] == [8500, -45000] and tx[1]["counterparty"] == "ABC FOODS" and tx[0]["reference"] == "ORDER-1048"
    pr.delete_session("s1")

def test_provider_keys_stored_encrypted():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from app.db import SessionLocal; from app import models
    assert c.put("/api/bank/credentials", headers=owner, json={"app_id": "x", "private_key": "not a key"}).status_code == 422
    pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    assert c.put("/api/bank/credentials", headers=cashier, json={"app_id": "x", "private_key": pem}).status_code == 403
    assert c.put("/api/bank/credentials", headers=owner, json={"app_id": "app-1", "private_key": pem}).status_code == 200
    db = SessionLocal(); v = db.get(models.Setting, "eb_private_key").value; db.close(); assert v.startswith("enc1:") and "BEGIN" not in v
    assert c.delete("/api/bank/credentials", headers=owner).status_code == 200

# ---------------- finance features ----------------
def test_supplier_iban_profile_and_invoice_paid():
    assert c.put("/api/suppliers/2", headers=owner, json={"iban": "CY99 0020 0128 0000 0012 0000 0000"}).status_code == 422   # bad checksum caught
    assert c.put("/api/suppliers/2", headers=owner, json={"iban": "cy17 0020 0128 0000 0012 0052 7600"}).json()["iban"] == "CY17002001280000001200527600"
    inv = c.post("/api/invoices", headers=owner, json={"supplier_id": 2, "number": "D-1", "issue_date": "2026-09-01", "due_date": "2026-09-20", "total_cents": 12000, "vat_cents": 1916,
                 "items": [{"product_id": 1, "description": "Milk", "quantity": 100, "unit_cents": 120}], "location_id": 2, "add_to_stock": True}).json()
    st = {s["sku"]: s for s in c.get("/api/stock", headers=owner).json()}; assert st["MILK1"]["quantity"] >= 100      # invoice received -> stock up
    pf = c.get("/api/suppliers/2/profile", headers=owner).json(); assert pf["outstanding_cents"] >= 12000 and pf["pending_invoices"] >= 1 and len(pf["products"]) >= 1
    assert c.get(f"/api/invoices/{inv['id']}", headers=owner).json()["items"][0]["quantity"] == 100
    assert c.post(f"/api/invoices/{inv['id']}/mark-paid", headers=owner, json={"method": "CASH"}).json()["status"] == "PAID"
    assert c.post(f"/api/invoices/{inv['id']}/mark-paid", headers=owner, json={}).status_code == 409
    assert c.get("/api/suppliers/2/profile", headers=owner).json()["last_payment"]["amount_cents"] == 12000

def test_scan_suggestions():
    r = c.post("/api/scan/suggest", headers=owner, json={"supplier": "ABC Foods Limited", "items": [{"description": "coffee beans", "quantity": 2, "unit_price": 6}, {"description": "zzz unknown", "quantity": 1}]}).json()
    assert r["supplier_id"] == 1 and r["items"][0]["product_id"] is not None and r["items"][1]["product_id"] is None

def test_refund_and_ledger_and_classify():
    prods = c.get("/api/products", headers=owner).json()
    o = c.post("/api/orders", headers=owner, json={"location_id": 2, "payment_method": "CASH", "items": [{"product_id": prods[1]["id"], "quantity": 4}]}).json()
    assert c.post(f"/api/orders/{o['id']}/refund", headers=owner, json={"amount_cents": 100}).status_code == 409     # not paid yet
    c.put(f"/api/orders/{o['id']}/status", headers=owner, json={"status": "PAID"})
    assert c.post(f"/api/orders/{o['id']}/refund", headers=owner, json={"amount_cents": o["total_cents"] + 1}).status_code == 422
    assert c.post(f"/api/orders/{o['id']}/refund", headers=owner, json={"amount_cents": 250, "reason": "wrong item"}).status_code == 201
    assert c.post(f"/api/orders/{o['id']}/refund", headers=owner, json={"amount_cents": o["total_cents"] - 250}).status_code == 201
    assert [x for x in c.get("/api/orders", headers=owner).json() if x["id"] == o["id"]][0]["status"] == "REFUNDED"
    csv = "date,amount,reference,counterparty\n01/10/2026,-3.50,Monthly account fee,Eurobank\n01/10/2026,-500.00,Move to savings,Own account\n01/10/2026,20.00,Random deposit,Someone\n"
    c.post("/api/bank/accounts/1/import-csv", headers=owner, files={"file": ("s.csv", csv)})
    tx = {t["reference"]: t for t in c.get("/api/bank/transactions?status=UNMATCHED", headers=owner).json()}
    assert c.post(f"/api/bank/transactions/{tx['Monthly account fee']['id']}/classify", headers=owner, json={"category": "BANK_FEE"}).json()["match_status"] == "RECONCILED"
    assert c.post(f"/api/bank/transactions/{tx['Move to savings']['id']}/classify", headers=owner, json={"category": "TRANSFER"}).status_code == 200
    assert c.post(f"/api/bank/transactions/{tx['Random deposit']['id']}/classify", headers=owner, json={"category": "EXPENSE"}).status_code == 422   # incoming cannot be expense
    led = c.get("/api/reports/ledger?fmt=json&date_from=2026-01-01&date_to=2030-01-01", headers=owner).json()["rows"]
    types = {r[1] for r in led}; assert {"INCOME", "EXPENSE", "VAT", "PAYMENT", "REFUND", "BANK_FEE", "TRANSFER"} <= types, types
    assert c.get("/api/reports/ledger?fmt=xlsx", headers=owner).content[:2] == b"PK"
