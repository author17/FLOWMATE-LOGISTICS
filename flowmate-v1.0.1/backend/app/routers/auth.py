import time, json, secrets, hashlib
from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import verify_password, make_token, current_user, require, hash_password, PERMS, new_totp_secret, totp_ok, mfa_required, mfa_policy
from ..services import sms
from datetime import datetime, timedelta
from .. import models, audit
from ..businesstypes import modules_for
from ..tenancy import get_setting, put_setting, all_settings

router = APIRouter(prefix="/api", tags=["auth"])
_fails: dict[str, list[float]] = {}   # simple brute-force protection: 5 wrong passwords per 15 min per email
WINDOW, MAX_FAILS = 900, 5

def _locked(email):
    now = time.time(); _fails[email] = [t for t in _fails.get(email, []) if now - t < WINDOW]
    return len(_fails[email]) >= MAX_FAILS

def _device(request: Request) -> dict:
    """Which browser/app and device a login came from (for the audit history)."""
    ua = request.headers.get("user-agent", "")
    br = next((n for k, n in [("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari")] if k in ua), "Unknown browser")
    os_ = next((n for k, n in [("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Mac OS", "Mac"), ("Linux", "Linux")] if k in ua), "Unknown device")
    mode = "installed app" if request.headers.get("x-app-mode") == "standalone" else "browser"
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
    return {"device": f"{br} on {os_} ({mode})", "ip": ip}

_sms_sends: dict[int, list[float]] = {}   # per user: at most 1 text per 30 s and 5 per hour (protects the SMS bill)

def _send_code(u, db, phone):
    if not phone: raise HTTPException(422, "No mobile number on this account - ask the owner to add one, or use a recovery code")
    now = time.time(); log_ = [t for t in _sms_sends.get(u.id, []) if now - t < 3600]; _sms_sends[u.id] = log_
    if log_ and now - log_[-1] < 30: raise HTTPException(429, "Please wait 30 seconds before asking for another code")
    if len(log_) >= 5: raise HTTPException(429, "Too many text messages requested. Try again in an hour or use a recovery code")
    code = f"{secrets.randbelow(10 ** 6):06d}"
    u.sms_hash = hashlib.sha256((code + str(u.id)).encode()).hexdigest(); u.sms_expires = datetime.utcnow() + timedelta(minutes=5); u.sms_tries = 0; db.commit()
    try: sms.send_sms(phone, f"FLOWMATE code: {code} (valid 5 minutes). Never share it.")
    except Exception as e: raise HTTPException(503, f"Could not send the text message: {e}")
    log_.append(now)

def _check_code(u, code, db) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not u.sms_hash or not u.sms_expires or u.sms_expires < datetime.utcnow() or (u.sms_tries or 0) >= 5: return False
    u.sms_tries = (u.sms_tries or 0) + 1
    ok = hmac_ok(hashlib.sha256((code + str(u.id)).encode()).hexdigest(), u.sms_hash)
    if ok: u.sms_hash = None; u.sms_expires = None
    db.commit(); return ok

def hmac_ok(a, b):
    import hmac; return hmac.compare_digest(a, b)

@router.post("/auth/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), otp: str = Form(""), db: Session = Depends(get_db)):
    class form: pass
    form.username, form.password = username, password
    email = form.username.strip().lower()
    dev = _device(request)
    if _locked(email): raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    u = db.scalar(select(models.User).where(models.User.email == email))
    if u: db.info["business_id"] = u.business_id        # login history belongs to that user's business
    biz = db.get(models.Business, u.business_id) if u and u.business_id else None
    if u and (not biz or not biz.active): raise HTTPException(401, "This business account is closed")
    if not u or not u.active or not verify_password(form.password, u.password_hash):
        _fails.setdefault(email, []).append(time.time())
        audit.log(db, None, "login_failed", "user", "", None, {"email": email[:80], **dev}); db.commit()   # who tried, from where (no password is ever stored)
        raise HTTPException(401, "Wrong email or password")
    if u.totp_enabled:
        if not otp:
            if u.mfa_method == "sms":
                try: _send_code(u, db, u.phone)
                except HTTPException as e: raise HTTPException(e.status_code, e.detail)
                raise HTTPException(401, f"MFA_REQUIRED:sms:{sms.mask(u.phone or '')}")
            raise HTTPException(401, "MFA_REQUIRED:app")
        rc = json.loads(u.recovery_codes or "[]"); h = hashlib.sha256(otp.strip().lower().encode()).hexdigest()
        if h in rc: rc.remove(h); u.recovery_codes = json.dumps(rc)          # recovery code: works once
        elif not (_check_code(u, otp, db) if u.mfa_method == "sms" else totp_ok(u.totp_secret or "", otp)):
            _fails.setdefault(email, []).append(time.time()); raise HTTPException(401, "Wrong authentication code")
    _fails.pop(email, None)
    audit.log(db, u, "login", "user", u.id, None, dev); db.commit()
    return {"access_token": make_token(u), "token_type": "bearer", "user": {"id": u.id, "name": u.name, "role": u.role, "must_change_password": u.must_change_password}}

@router.get("/auth/me")
def me(u=Depends(current_user), db: Session = Depends(get_db)):
    b = db.get(models.Business, u.business_id)
    return {"business": {"id": b.id, "name": b.name, "kind": b.kind, "slug": b.slug, "modules": modules_for(b.kind)}, **_me(u, db)}

def _me(u, db): return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "location_id": u.location_id, "must_change_password": u.must_change_password, "perms": sorted(PERMS.get(u.role, set())), "totp_enabled": u.totp_enabled, "mfa_method": (u.mfa_method or "app") if u.totp_enabled else None, "phone": u.phone, "must_setup_mfa": mfa_required(u, db)}

class PwChange(BaseModel): old_password: str; new_password: str

@router.post("/auth/change-password")
def change_pw(d: PwChange, u=Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(d.old_password, u.password_hash): raise HTTPException(401, "Current password is wrong")
    if len(d.new_password) < 10: raise HTTPException(422, "New password must be at least 10 characters")
    if d.new_password == d.old_password: raise HTTPException(422, "Choose a different password")
    u.password_hash = hash_password(d.new_password); u.must_change_password = False; u.token_version = (u.token_version or 0) + 1
    audit.log(db, u, "change_password", "user", u.id); db.commit(); return {"ok": True, "access_token": make_token(u)}

class NewUser(BaseModel):
    name: str; email: str; password: str; role: str = "employee"; location_id: int | None = None; phone: str | None = None

@router.get("/users")
def users(db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    return [{"id": x.id, "name": x.name, "email": x.email, "role": x.role, "location_id": x.location_id, "active": x.active, "phone": x.phone} for x in db.scalars(select(models.User))]

@router.post("/users", status_code=201)
def add_user(d: NewUser, db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    if len(d.password) < 10: raise HTTPException(422, "Password must be at least 10 characters")
    n = models.User(name=d.name, email=d.email.strip().lower(), must_change_password=True, password_hash=hash_password(d.password), role=d.role, location_id=d.location_id, phone=d.phone)
    db.add(n); db.flush(); audit.log(db, u, "create_user", "user", n.id, None, {"email": d.email, "role": d.role}); db.commit()
    return {"id": n.id}

class UserEdit(BaseModel): name: str | None = None; role: str | None = None; active: bool | None = None; location_id: int | None = None; phone: str | None = None
ROLES = {"owner", "manager", "employee", "accountant", "bank_payment", "admin", "driver"}

@router.put("/users/{id}")
def edit_user(id: int, d: UserEdit, db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    x = db.get(models.User, id)
    if not x: raise HTTPException(404)
    if d.role and d.role not in ROLES: raise HTTPException(422, "Unknown role")
    if id == u.id and (d.active is False or (d.role and d.role not in ("owner", "admin"))): raise HTTPException(409, "You cannot lock yourself out")
    old = {"name": x.name, "role": x.role, "active": x.active}
    for k, v in d.model_dump(exclude_none=True).items(): setattr(x, k, v)
    if d.active is False or d.role: x.token_version = (x.token_version or 0) + 1      # role change / lock-out ends their sessions
    audit.log(db, u, "edit_user", "user", id, old, d.model_dump(exclude_none=True)); db.commit(); return {"ok": True}

class Reset(BaseModel): temp_password: str

@router.post("/users/{id}/reset-password")
def reset_pw(id: int, d: Reset, db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    x = db.get(models.User, id)
    if not x: raise HTTPException(404)
    if len(d.temp_password) < 10: raise HTTPException(422, "At least 10 characters")
    x.password_hash = hash_password(d.temp_password); x.must_change_password = True; x.token_version = (x.token_version or 0) + 1
    audit.log(db, u, "reset_password", "user", id); db.commit(); return {"ok": True}

@router.get("/settings")
def get_settings(db: Session = Depends(get_db), u=Depends(current_user)):
    from ..config import OCR_PROVIDER, DEMO_MODE
    s = all_settings(db)
    return {"company_name": s.get("company_name", ""), "vat_number": s.get("vat_number", ""), "currency": s.get("currency", "EUR"), "public_orders_enabled": s.get("public_orders_enabled", "0") in ("1", "true"), "company_email": s.get("company_email", ""), "company_address": s.get("company_address", ""), "ocr_provider": OCR_PROVIDER, "demo": DEMO_MODE, "mfa_policy": mfa_policy(db)}

@router.put("/settings")
def put_settings(d: dict, db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    for k in ("company_name", "vat_number", "currency", "public_orders_enabled", "company_email", "company_address"):
        if k in d:
            put_setting(db, k, ("1" if d[k] else "0") if k == "public_orders_enabled" else str(d[k]))
    if d.get("mfa_policy") in ("optional", "required"):
        put_setting(db, "mfa_policy", d["mfa_policy"])
    audit.log(db, u, "update_settings", "settings", "", None, d); db.commit(); return {"ok": True}

@router.post("/notifications/read-all")
def read_all(db: Session = Depends(get_db), u=Depends(current_user)):
    for n in db.scalars(select(models.Notification).where(models.Notification.read == False)): n.read = True
    db.commit(); return {"ok": True}

# ---------------- sessions & two-factor ----------------
@router.post("/auth/logout-all")
def logout_all(u=Depends(current_user), db: Session = Depends(get_db)):
    u.token_version = (u.token_version or 0) + 1; audit.log(db, u, "logout_all_devices", "user", u.id); db.commit(); return {"ok": True}

@router.post("/auth/mfa/setup")
def mfa_setup(u=Depends(current_user), db: Session = Depends(get_db)):
    if u.totp_enabled: raise HTTPException(409, "Two-factor login is already on")
    u.totp_secret = new_totp_secret(); u.mfa_method = None; db.commit()
    from ..config import APP_BASE_URL
    return {"secret": u.totp_secret, "otpauth": f"otpauth://totp/FLOWMATE:{u.email}?secret={u.totp_secret}&issuer=FLOWMATE"}

class Code(BaseModel): code: str

@router.post("/auth/mfa/enable")
def mfa_enable(d: Code, u=Depends(current_user), db: Session = Depends(get_db)):
    if not u.totp_secret or u.totp_enabled: raise HTTPException(409, "Start setup first")
    if not totp_ok(u.totp_secret, d.code): raise HTTPException(422, "That code is wrong - check the time on your phone and try the next code")
    codes = [secrets.token_hex(4) for _ in range(8)]
    u.totp_enabled = True; u.mfa_method = "app"; u.recovery_codes = json.dumps([hashlib.sha256(c.encode()).hexdigest() for c in codes])
    audit.log(db, u, "mfa_enabled", "user", u.id, None, {"method": "app"}); db.commit(); return {"recovery_codes": codes}     # shown once

class PhoneIn(BaseModel): phone: str

@router.post("/auth/mfa/sms/start")
def mfa_sms_start(d: PhoneIn, u=Depends(current_user), db: Session = Depends(get_db)):
    if u.totp_enabled: raise HTTPException(409, "Two-step login is already on")
    if not sms.configured(): raise HTTPException(503, "Text-message codes are not set up on this server yet. Use the authenticator app.")
    ph = sms.normalize_phone(d.phone)
    if not ph: raise HTTPException(422, "Enter the mobile number with country code, e.g. +357 96 123456")
    u.sms_pending_phone = ph; _send_code(u, db, ph); return {"sent_to": sms.mask(ph)}

@router.post("/auth/mfa/sms/enable")
def mfa_sms_enable(d: Code, u=Depends(current_user), db: Session = Depends(get_db)):
    if u.totp_enabled or not u.sms_pending_phone: raise HTTPException(409, "Start setup first")
    if not _check_code(u, d.code, db): raise HTTPException(422, "That code is wrong or expired - ask for a new text")
    _sms_sends.pop(u.id, None)   # setup is done: the first real login should not wait
    codes = [secrets.token_hex(4) for _ in range(8)]
    u.phone, u.mfa_method, u.totp_enabled, u.sms_pending_phone = u.sms_pending_phone, "sms", True, None
    u.recovery_codes = json.dumps([hashlib.sha256(c.encode()).hexdigest() for c in codes])
    audit.log(db, u, "mfa_enabled", "user", u.id, None, {"method": "sms"}); db.commit(); return {"recovery_codes": codes}

class Disable(BaseModel): password: str; code: str = ""

@router.post("/auth/mfa/disable")
def mfa_disable(d: Disable, u=Depends(current_user), db: Session = Depends(get_db)):
    if not u.totp_enabled: raise HTTPException(409, "Not enabled")
    if not verify_password(d.password, u.password_hash) or (u.mfa_method != "sms" and not totp_ok(u.totp_secret or "", d.code)): raise HTTPException(401, "Password or code is wrong")
    u.totp_enabled, u.totp_secret, u.recovery_codes, u.mfa_method = False, None, None, None; audit.log(db, u, "mfa_disabled", "user", u.id); db.commit(); return {"ok": True}

@router.post("/users/{id}/reset-mfa")
def reset_mfa(id: int, db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    """Owner unlocks someone who lost their phone."""
    x = db.get(models.User, id)
    if not x: raise HTTPException(404)
    x.totp_enabled, x.totp_secret, x.recovery_codes, x.mfa_method, x.token_version = False, None, None, None, (x.token_version or 0) + 1
    audit.log(db, u, "reset_mfa", "user", id); db.commit(); return {"ok": True}
