from test_flow import c, owner
from app import models
from test_flow import SessionLocal

def test_scanner_files_duplicate_warning_and_big_limit():
    f = {"file": ("scan1.tif", b"II*\x00fake-tiff-bytes")}
    r = c.post("/api/documents/scan", headers=owner, files=f, data={"doc_type": "invoice"}); assert r.status_code == 201, r.text   # TIFF accepted
    assert r.json()["duplicate_of"] is None and r.json()["file_hash"]
    r2 = c.post("/api/documents/scan", headers=owner, files={"file": ("again.tif", b"II*\x00fake-tiff-bytes")}, data={"doc_type": "invoice"})
    assert r2.status_code == 201 and r2.json()["duplicate_of"] == r.json()["id"]          # same content -> warning, not blocked
    assert c.post("/api/documents/scan", headers=owner, files={"file": ("x.exe", b"MZ")}, data={"doc_type": "other"}).status_code == 415

def test_login_audit_records_device_and_failures():
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
    c.post("/api/auth/login", data={"username": "nobody@demo.com", "password": "bad"}, headers=ua)
    ok = c.post("/api/auth/login", data={"username": "owner@demo.com", "password": "demo12345"}, headers={**ua, "X-App-Mode": "standalone"})
    rows = c.get("/api/audit", headers=owner).json()
    assert any(r["action"] == "login_failed" and r["new_value"]["email"] == "nobody@demo.com" and "Chrome on Windows" in r["new_value"]["device"] for r in rows)
    if ok.status_code == 200: assert any(r["action"] == "login" and r["new_value"] and "installed app" in r["new_value"]["device"] for r in rows)

def test_upload_safety_checks():
    assert c.post("/api/documents/scan", headers=owner, files={"file": ("evil.pdf", b"MZ\x90\x00program")}, data={"doc_type": "other"}).status_code == 415   # renamed program
    assert c.post("/api/documents/scan", headers=owner, files={"file": ("empty.pdf", b"")}, data={"doc_type": "other"}).status_code == 422
    assert c.post("/api/documents/scan", headers=owner, files={"file": ("ok.pdf", b"%PDF-1.4 minimal")}, data={"doc_type": "other"}).status_code == 201

def test_sms_two_step_choice_and_policy():
    import os; os.environ["SMS_PROVIDER"] = "console"
    from app.services import sms
    assert c.get("/api/config").json()["sms_available"] is True
    assert c.post("/api/users", headers=owner, json={"name": "S", "email": "sms@demo.com", "role": "manager", "password": "demo12345xx"}).status_code in (200, 201)
    tok = c.post("/api/auth/login", data={"username": "sms@demo.com", "password": "demo12345xx"}).json()["access_token"]; h = {"Authorization": "Bearer " + tok}
    assert c.post("/api/auth/mfa/sms/start", headers=h, json={"phone": "12"}).status_code == 422                       # bad number
    r = c.post("/api/auth/mfa/sms/start", headers=h, json={"phone": "96 540597"}); assert r.status_code == 200 and "+357" in r.json()["sent_to"]
    assert c.post("/api/auth/mfa/sms/start", headers=h, json={"phone": "96 540597"}).status_code == 429               # 30 s cooldown
    code = sms.LAST["+35796540597"].split("code: ")[1][:6]
    assert c.post("/api/auth/mfa/sms/enable", headers=h, json={"code": "000000"}).status_code == 422
    rc = c.post("/api/auth/mfa/sms/enable", headers=h, json={"code": code}).json()["recovery_codes"]; assert len(rc) == 8
    assert c.get("/api/auth/me", headers=h).json()["mfa_method"] == "sms"
    r = c.post("/api/auth/login", data={"username": "sms@demo.com", "password": "demo12345xx"}); assert r.status_code == 401 and "MFA_REQUIRED:sms:" in r.text   # text is sent now
    from app.routers import auth as A; A._sms_sends.clear()
    c.post("/api/auth/login", data={"username": "sms@demo.com", "password": "demo12345xx"})
    code2 = sms.LAST["+35796540597"].split("code: ")[1][:6]
    assert c.post("/api/auth/login", data={"username": "sms@demo.com", "password": "demo12345xx", "otp": "111111"}).status_code == 401
    assert c.post("/api/auth/login", data={"username": "sms@demo.com", "password": "demo12345xx", "otp": code2}).status_code == 200
    assert c.post("/api/auth/login", data={"username": "sms@demo.com", "password": "demo12345xx", "otp": code2}).status_code == 401      # codes work once
    assert c.get("/api/settings", headers=owner).json()["mfa_policy"] == "optional"                                                    # optional by default
    assert c.put("/api/settings", headers=owner, json={"mfa_policy": "required"}).status_code == 200
    assert c.get("/api/settings", headers=owner).json()["mfa_policy"] == "required"
    c.put("/api/settings", headers=owner, json={"mfa_policy": "optional"})
