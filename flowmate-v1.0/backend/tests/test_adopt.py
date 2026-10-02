"""Upgrading Christina's existing single-company database: everything must become business #1 and still work."""
import os, tempfile, subprocess, sys, textwrap

def test_legacy_database_is_adopted_as_business_1():
    d = tempfile.mkdtemp(); db = f"{d}/old.db"
    code = textwrap.dedent(f'''
        import os; os.environ["DATABASE_URL"] = "sqlite:///{db}"; os.environ["STORAGE_DIR"] = "{d}/st"; os.environ["DISABLE_SCHEDULER"]="1"
        import sqlite3
        cx = sqlite3.connect("{db}")
        cx.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password_hash TEXT, role TEXT, location_id INT, active BOOLEAN, must_change_password BOOLEAN, token_version INT);
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE products (id INTEGER PRIMARY KEY, sku TEXT UNIQUE, name TEXT, purchase_cents INT, sell_cents INT);
        INSERT INTO users VALUES (1,'Old Owner','old@x.com','x$y','owner',NULL,1,0,0);
        INSERT INTO settings VALUES ('company_name','VIP GYM'),('vat_number','CY123');
        INSERT INTO products VALUES (1,'S1','Old product',1,2);
        """); cx.commit(); cx.close()
        from app.main import app
        from fastapi.testclient import TestClient
        from app.db import SessionLocal; from app import models
        from app.tenancy import use_business, get_setting
        with SessionLocal() as d:
            b = d.get(models.Business, 1); assert b.name == "VIP GYM" and b.kind == "general", b
            use_business(d, 1)
            assert get_setting(d, "vat_number") == "CY123"
            assert d.query(models.User).one().business_id == 1 and d.query(models.Product).one().name == "Old product"
        # a new business can sign up and does not see the old data, and the old key counter does not collide
        c = TestClient(app)
        r = c.post("/api/signup", json={{"business_name":"New Co","kind":"shop","owner_name":"N","email":"n@x.com","password":"Strong-pass-123","accept_terms":True}}); assert r.status_code == 201, r.text
        h = {{"Authorization": "Bearer " + r.json()["access_token"]}}
        assert c.get("/api/products", headers=h).json() == []
        assert c.get("/api/auth/me", headers=h).json()["business"]["id"] == 2
        print("ADOPT-OK")
    ''')
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))
    assert "ADOPT-OK" in r.stdout, r.stdout + r.stderr[-2000:]
