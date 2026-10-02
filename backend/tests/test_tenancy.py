"""Strict isolation tests: business B must never see, change or delete anything of business A (the seeded demo business)."""
import os, tempfile, io, zipfile
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/t.db"); os.environ.setdefault("STORAGE_DIR", tempfile.mkdtemp())
os.environ["DEMO_MODE"] = "1"; os.environ["DISABLE_SCHEDULER"] = "1"
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app import models
import seed as seedmod

with SessionLocal() as _d: seedmod.seed(_d)
c = TestClient(app)

def hdr(tok): return {"Authorization": "Bearer " + tok}
def login(email, pw="demo12345"):
    r = c.post("/api/auth/login", data={"username": email, "password": pw}); assert r.status_code == 200, r.text; return hdr(r.json()["access_token"])

A = login("owner@demo.com")
def signup(name, email, kind="cafe"):
    r = c.post("/api/signup", json={"business_name": name, "kind": kind, "owner_name": "Bee", "email": email, "password": "Strong-pass-123", "accept_terms": True}); assert r.status_code == 201, r.text
    return hdr(r.json()["access_token"])
B = signup("Bee Cafe", "bee@example.com")

def test_every_table_is_business_owned():
    from app.tenancy import Tenant
    for m in models.Base.registry.mappers:
        if m.class_ is models.Business: continue
        assert issubclass(m.class_, Tenant), f"{m.class_.__name__} is not business-scoped"

def test_signup_rules():
    base = {"business_name": "X Shop", "kind": "shop", "owner_name": "X", "email": "x1@example.com", "password": "Strong-pass-123", "accept_terms": True}
    assert c.post("/api/signup", json={**base, "accept_terms": False}).status_code == 422
    assert c.post("/api/signup", json={**base, "password": "short"}).status_code == 422
    assert c.post("/api/signup", json={**base, "kind": "hacker"}).status_code == 422
    assert c.post("/api/signup", json={**base, "email": "owner@demo.com"}).status_code == 409      # existing e-mail

def test_new_business_starts_empty_with_its_own_starter_data():
    assert c.get("/api/orders", headers=B).json() == []
    assert c.get("/api/products", headers=B).json() == []
    assert [l["name"] for l in c.get("/api/locations", headers=B).json()] == ["Main"]
    assert len(c.get("/api/users", headers=B).json()) == 1
    me = c.get("/api/auth/me", headers=B).json(); assert me["business"]["kind"] == "cafe" and me["business"]["name"] == "Bee Cafe"

def test_cannot_read_or_touch_other_business_by_id():
    a_orders = c.get("/api/orders", headers=A).json(); a_prod = c.get("/api/products", headers=A).json(); a_users = c.get("/api/users", headers=A).json()
    a_inv = c.get("/api/invoices", headers=A).json(); a_cust = c.get("/api/customers", headers=A).json() if c.get("/api/customers", headers=A).status_code == 200 else []
    assert a_prod and a_users
    for p in a_prod:
        assert c.put(f"/api/products/{p['id']}", headers=B, json={"name": "HACKED"}).status_code in (404, 405, 422)
        assert c.delete(f"/api/products/{p['id']}", headers=B).status_code in (404, 405)
    assert all(p["name"] != "HACKED" for p in c.get("/api/products", headers=A).json())
    for u in a_users:
        assert c.put(f"/api/users/{u['id']}", headers=B, json={"active": False}).status_code == 404
        assert c.post(f"/api/users/{u['id']}/reset-password", headers=B, json={"temp_password": "Hacked-password-1"}).status_code == 404
    login("owner@demo.com")                                                  # A can still log in with the old password
    for o in a_orders:
        assert c.get(f"/api/orders/{o['id']}", headers=B).status_code == 404
    for i in a_inv:
        assert c.get(f"/api/invoices/{i['id']}", headers=B).status_code in (404, 405)

def test_cannot_use_other_business_ids_when_creating():
    a_loc = c.get("/api/locations", headers=A).json()[0]["id"]; a_prod = c.get("/api/products", headers=A).json()[0]["id"]
    b_loc = c.get("/api/locations", headers=B).json()[0]["id"]
    r = c.post("/api/orders", headers=B, json={"location_id": a_loc, "items": []}); assert r.status_code >= 400
    r = c.post("/api/orders", headers=B, json={"location_id": b_loc, "items": [{"product_id": a_prod, "quantity": 1}]}); assert r.status_code >= 400
    assert c.get("/api/orders", headers=A).json() == c.get("/api/orders", headers=A).json()

def test_same_sku_and_category_names_allowed_per_business():
    a_sku = c.get("/api/products", headers=A).json()[0]["sku"]
    r = c.post("/api/products", headers=B, json={"sku": a_sku, "name": "Bee product", "purchase_cents": 10, "sell_cents": 20}); assert r.status_code in (200, 201), r.text
    r2 = c.post("/api/products", headers=B, json={"sku": a_sku, "name": "dup", "purchase_cents": 10, "sell_cents": 20}); assert r2.status_code >= 400   # but not twice inside B
    assert [p["name"] for p in c.get("/api/products", headers=B).json()] == ["Bee product"]

def test_settings_are_per_business():
    assert c.put("/api/settings", headers=B, json={"company_name": "Bee Cafe Ltd", "vat_number": "BEEVAT"}).status_code == 200
    assert c.get("/api/settings", headers=B).json()["vat_number"] == "BEEVAT"
    assert c.get("/api/settings", headers=A).json()["vat_number"] != "BEEVAT"

def test_blind_sweep_no_get_endpoint_leaks_a_data_to_b():
    """Calls every parameter-free GET endpoint as B and looks for any trace of A's data."""
    markers = ["owner@demo.com", "ABC Foods", "Fresh Dairy", "Gym A", "demo12345", "CY10000000X"]
    n = 0
    for path, ops in app.openapi()["paths"].items():
        if "get" not in ops or "{" in path or not path.startswith("/api/") or path in ("/api/backups", "/api/export/all.zip", "/api/export/documents.zip"): continue
        r = c.get(path, headers=B)
        assert r.status_code < 500, (path, r.status_code, r.text[:200])
        if "zip" in r.headers.get("content-type", ""): continue
        n += 1
        for m in markers: assert m not in r.text, f"LEAK of {m!r} via {path}"
    assert n > 30

def test_export_contains_only_own_data():
    r = c.get("/api/export/all.zip", headers=B); assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content)); blob = "".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist())
    assert "bee@example.com" in blob
    for m in ["owner@demo.com", "ABC Foods", "Gym A", "password_hash"]: assert m not in blob
    assert "inbound_token" not in blob

def test_whole_system_backups_are_platform_only():
    assert c.get("/api/backups", headers=B).status_code == 403 and c.post("/api/backups/run", headers=B).status_code == 403
    assert c.get("/api/backups", headers=A).status_code == 403      # even demo owner A: PLATFORM_ADMIN_EMAILS not set

def test_public_ordering_is_per_business():
    slug_b = c.get("/api/auth/me", headers=B).json()["business"]["slug"]
    c.put("/api/settings", headers=A, json={"public_orders_enabled": True}); c.put("/api/settings", headers=B, json={"public_orders_enabled": True})
    pa = c.get("/api/public/demo/menu").json(); pb = c.get(f"/api/public/{slug_b}/menu").json()
    assert {p["name"] for p in pb["products"]} == {"Bee product"} or pb["products"] == []
    assert all(p["name"] != "Bee product" for p in pa["products"])
    assert c.get("/api/public/no-such-business/menu").status_code == 404
    a_prod = c.get("/api/products", headers=A).json()[0]["id"]; b_loc = pb["locations"][0]["id"]
    r = c.post(f"/api/public/{slug_b}/orders", json={"name": "Z", "phone": "1", "location_id": b_loc, "items": [{"product_id": a_prod, "quantity": 1}]}); assert r.status_code >= 400   # A's product cannot be ordered from B's page
    c.put("/api/settings", headers=A, json={"public_orders_enabled": False})

def test_inbound_email_goes_only_to_token_owner(monkeypatch):
    with SessionLocal() as d: tok = d.get(models.Business, 1).inbound_token
    before = len(c.get("/api/documents", headers=B).json())
    r = c.post(f"/api/inbound/email?token={tok}", data={"from": "s@x.com"}, files={"a": ("i.pdf", b"%PDF-1")}); assert r.status_code == 201
    assert len(c.get("/api/documents", headers=B).json()) == before
    assert any(d_["source"] == "email" for d_ in c.get("/api/documents", headers=A).json())

def test_stripe_webhook_cannot_cross_businesses():
    import hmac, hashlib, time, json
    from app import config
    from app.tenancy import use_business, put_setting
    from app.crypto import encrypt
    with SessionLocal() as d:
        use_business(d, 2); put_setting(d, "stripe_secret", encrypt("sk_test_b")); put_setting(d, "stripe_webhook_secret", encrypt("whsec_b")); d.commit()
    def send(bid, secret):
        raw = json.dumps({"type": "checkout.session.completed", "data": {"object": {"id": "cs_none", "payment_status": "paid", "amount_total": 1, "currency": "eur"}}}).encode(); t = int(time.time())
        sig = hmac.new(secret.encode(), f"{t}.".encode() + raw, hashlib.sha256).hexdigest()
        return c.post(f"/api/stripe/webhook/{bid}", content=raw, headers={"stripe-signature": f"t={t},v1={sig}"})
    assert send(2, "whsec_b").status_code == 200           # its own secret works
    assert send(2, "whsec_a").status_code == 400            # another secret does not
    assert send(1, "whsec_b").status_code == 400            # B's secret is useless on A's URL
    assert c.get("/api/stripe/status", headers=B).json()["configured"] is True
    assert "sk_test" not in c.get("/api/stripe/status", headers=B).text

def test_orm_layer_blocks_cross_business_even_with_known_ids():
    from app.tenancy import use_business
    with SessionLocal() as d:
        a_id = d.query(models.Product).filter(models.Product.business_id == 1).first().id
        use_business(d, 2)
        assert d.get(models.Product, a_id) is None
        assert d.query(models.Product).filter(models.Product.id == a_id).first() is None
        from sqlalchemy import update, select
        d.execute(update(models.Product).where(models.Product.id == a_id).values(name="X")); d.commit()
        use_business(d, 1); assert d.get(models.Product, a_id).name != "X"
        use_business(d, 2)
        p = models.Product(sku="Z", name="z", business_id=1, purchase_cents=1, sell_cents=1); d.add(p)
        with pytest.raises(PermissionError): d.flush()
        d.rollback()

def test_deleted_staff_and_business():
    # staff: owner B adds an employee who deletes themselves
    assert c.post("/api/users", headers=B, json={"name": "Emp", "email": "emp@example.com", "password": "Temp-password-1", "role": "employee"}).status_code == 201
    emp = login("emp@example.com", "Temp-password-1")
    assert c.post("/api/account/delete-me", headers=emp, json={"password": "wrong"}).status_code == 401
    assert c.post("/api/account/delete-me", headers=emp, json={"password": "Temp-password-1"}).status_code == 200
    assert c.post("/api/auth/login", data={"username": "emp@example.com", "password": "Temp-password-1"}).status_code == 401
    assert c.post("/api/account/delete-me", headers=B, json={"password": "Strong-pass-123"}).status_code == 409        # owner must delete the business
    # business: needs owner + password + exact name
    assert c.post("/api/account/delete-business", headers=emp, json={"password": "x", "confirm_name": "x"}).status_code in (401, 403)
    assert c.post("/api/account/delete-business", headers=B, json={"password": "Strong-pass-123", "confirm_name": "wrong"}).status_code == 422
    n_a = len(c.get("/api/products", headers=A).json())
    assert c.post("/api/account/delete-business", headers=B, json={"password": "Strong-pass-123", "confirm_name": "Bee Cafe"}).status_code == 200
    assert c.get("/api/orders", headers=B).status_code == 401
    assert c.post("/api/auth/login", data={"username": "bee@example.com", "password": "Strong-pass-123"}).status_code == 401
    with SessionLocal() as d:
        from sqlalchemy import text
        for t in models.Base.metadata.sorted_tables:
            if "business_id" in t.c: assert d.execute(text(f'SELECT COUNT(*) FROM "{t.name}" WHERE business_id = 2')).scalar() == 0, t.name
    assert len(c.get("/api/products", headers=A).json()) == n_a                       # A untouched
