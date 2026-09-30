import os, tempfile
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/t.db"
os.environ["STORAGE_DIR"] = tempfile.mkdtemp()
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
    r = c.post("/api/documents/scan", headers=owner, files={"file": ("r.jpg", b"fakejpg")}, data={"doc_type": "receipt"})
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
