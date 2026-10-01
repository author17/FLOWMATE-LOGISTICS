import time, json, secrets, hashlib
from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import verify_password, make_token, current_user, require, hash_password, PERMS, new_totp_secret, totp_ok, mfa_required
from .. import models, audit

router = APIRouter(prefix="/api", tags=["auth"])
_fails: dict[str, list[float]] = {}   # simple brute-force protection: 5 wrong passwords per 15 min per email
WINDOW, MAX_FAILS = 900, 5

def _locked(email):
    now = time.time(); _fails[email] = [t for t in _fails.get(email, []) if now - t < WINDOW]
    return len(_fails[email]) >= MAX_FAILS

@router.post("/auth/login")
def login(username: str = Form(...), password: str = Form(...), otp: str = Form(""), db: Session = Depends(get_db)):
    class form: pass
    form.username, form.password = username, password
    email = form.username.strip().lower()
    if _locked(email): raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    u = db.scalar(select(models.User).where(models.User.email == email))
    if not u or not u.active or not verify_password(form.password, u.password_hash):
        _fails.setdefault(email, []).append(time.time())
        raise HTTPException(401, "Wrong email or password")
    if u.totp_enabled:
        if not otp: raise HTTPException(401, "MFA_REQUIRED")
        rc = json.loads(u.recovery_codes or "[]"); h = hashlib.sha256(otp.strip().lower().encode()).hexdigest()
        if h in rc: rc.remove(h); u.recovery_codes = json.dumps(rc)          # recovery code: works once
        elif not totp_ok(u.totp_secret or "", otp):
            _fails.setdefault(email, []).append(time.time()); raise HTTPException(401, "Wrong authentication code")
    _fails.pop(email, None)
    audit.log(db, u, "login", "user", u.id); db.commit()
    return {"access_token": make_token(u), "token_type": "bearer", "user": {"id": u.id, "name": u.name, "role": u.role, "must_change_password": u.must_change_password}}

@router.get("/auth/me")
def me(u=Depends(current_user)): return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "location_id": u.location_id, "must_change_password": u.must_change_password, "perms": sorted(PERMS.get(u.role, set())), "totp_enabled": u.totp_enabled, "must_setup_mfa": mfa_required(u)}

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
    s = {r.key: r.value for r in db.scalars(select(models.Setting))}
    return {"company_name": s.get("company_name", ""), "vat_number": s.get("vat_number", ""), "currency": s.get("currency", "EUR"), "public_orders_enabled": s.get("public_orders_enabled", "0") in ("1", "true"), "company_email": s.get("company_email", ""), "company_address": s.get("company_address", ""), "ocr_provider": OCR_PROVIDER, "demo": DEMO_MODE}

@router.put("/settings")
def put_settings(d: dict, db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    for k in ("company_name", "vat_number", "currency", "public_orders_enabled", "company_email", "company_address"):
        if k in d:
            row = db.get(models.Setting, k) or models.Setting(key=k); row.value = ("1" if d[k] else "0") if k == "public_orders_enabled" else str(d[k]); db.add(row)
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
    u.totp_secret = new_totp_secret(); db.commit()
    from ..config import APP_BASE_URL
    return {"secret": u.totp_secret, "otpauth": f"otpauth://totp/FLOWMATE:{u.email}?secret={u.totp_secret}&issuer=FLOWMATE"}

class Code(BaseModel): code: str

@router.post("/auth/mfa/enable")
def mfa_enable(d: Code, u=Depends(current_user), db: Session = Depends(get_db)):
    if not u.totp_secret or u.totp_enabled: raise HTTPException(409, "Start setup first")
    if not totp_ok(u.totp_secret, d.code): raise HTTPException(422, "That code is wrong - check the time on your phone and try the next code")
    codes = [secrets.token_hex(4) for _ in range(8)]
    u.totp_enabled = True; u.recovery_codes = json.dumps([hashlib.sha256(c.encode()).hexdigest() for c in codes])
    audit.log(db, u, "mfa_enabled", "user", u.id); db.commit(); return {"recovery_codes": codes}     # shown once

class Disable(BaseModel): password: str; code: str

@router.post("/auth/mfa/disable")
def mfa_disable(d: Disable, u=Depends(current_user), db: Session = Depends(get_db)):
    if not u.totp_enabled: raise HTTPException(409, "Not enabled")
    if not verify_password(d.password, u.password_hash) or not totp_ok(u.totp_secret or "", d.code): raise HTTPException(401, "Password or code is wrong")
    u.totp_enabled, u.totp_secret, u.recovery_codes = False, None, None; audit.log(db, u, "mfa_disabled", "user", u.id); db.commit(); return {"ok": True}

@router.post("/users/{id}/reset-mfa")
def reset_mfa(id: int, db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    """Owner unlocks someone who lost their phone."""
    x = db.get(models.User, id)
    if not x: raise HTTPException(404)
    x.totp_enabled, x.totp_secret, x.recovery_codes, x.token_version = False, None, None, (x.token_version or 0) + 1
    audit.log(db, u, "reset_mfa", "user", id); db.commit(); return {"ok": True}
