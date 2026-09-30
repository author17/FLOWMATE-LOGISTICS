import time
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..security import verify_password, make_token, current_user, require, hash_password, PERMS
from .. import models, audit

router = APIRouter(prefix="/api", tags=["auth"])
_fails: dict[str, list[float]] = {}   # simple brute-force protection: 5 wrong passwords per 15 min per email
WINDOW, MAX_FAILS = 900, 5

def _locked(email):
    now = time.time(); _fails[email] = [t for t in _fails.get(email, []) if now - t < WINDOW]
    return len(_fails[email]) >= MAX_FAILS

@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form.username.strip().lower()
    if _locked(email): raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    u = db.scalar(select(models.User).where(models.User.email == email))
    if not u or not u.active or not verify_password(form.password, u.password_hash):
        _fails.setdefault(email, []).append(time.time())
        raise HTTPException(401, "Wrong email or password")
    _fails.pop(email, None)
    audit.log(db, u, "login", "user", u.id); db.commit()
    return {"access_token": make_token(u), "token_type": "bearer", "user": {"id": u.id, "name": u.name, "role": u.role, "must_change_password": u.must_change_password}}

@router.get("/auth/me")
def me(u=Depends(current_user)): return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "location_id": u.location_id, "must_change_password": u.must_change_password, "perms": sorted(PERMS.get(u.role, set()))}

class PwChange(BaseModel): old_password: str; new_password: str

@router.post("/auth/change-password")
def change_pw(d: PwChange, u=Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(d.old_password, u.password_hash): raise HTTPException(401, "Current password is wrong")
    if len(d.new_password) < 10: raise HTTPException(422, "New password must be at least 10 characters")
    if d.new_password == d.old_password: raise HTTPException(422, "Choose a different password")
    u.password_hash = hash_password(d.new_password); u.must_change_password = False
    audit.log(db, u, "change_password", "user", u.id); db.commit(); return {"ok": True}

class NewUser(BaseModel):
    name: str; email: str; password: str; role: str = "employee"; location_id: int | None = None

@router.get("/users")
def users(db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    return [{"id": x.id, "name": x.name, "email": x.email, "role": x.role, "location_id": x.location_id, "active": x.active} for x in db.scalars(select(models.User))]

@router.post("/users", status_code=201)
def add_user(d: NewUser, db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    if len(d.password) < 10: raise HTTPException(422, "Password must be at least 10 characters")
    n = models.User(name=d.name, email=d.email.strip().lower(), must_change_password=True, password_hash=hash_password(d.password), role=d.role, location_id=d.location_id)
    db.add(n); db.flush(); audit.log(db, u, "create_user", "user", n.id, None, {"email": d.email, "role": d.role}); db.commit()
    return {"id": n.id}

class UserEdit(BaseModel): name: str | None = None; role: str | None = None; active: bool | None = None; location_id: int | None = None
ROLES = {"owner", "manager", "employee", "accountant", "bank_payment", "admin", "driver"}

@router.put("/users/{id}")
def edit_user(id: int, d: UserEdit, db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    x = db.get(models.User, id)
    if not x: raise HTTPException(404)
    if d.role and d.role not in ROLES: raise HTTPException(422, "Unknown role")
    if id == u.id and (d.active is False or (d.role and d.role not in ("owner", "admin"))): raise HTTPException(409, "You cannot lock yourself out")
    old = {"name": x.name, "role": x.role, "active": x.active}
    for k, v in d.model_dump(exclude_none=True).items(): setattr(x, k, v)
    audit.log(db, u, "edit_user", "user", id, old, d.model_dump(exclude_none=True)); db.commit(); return {"ok": True}

class Reset(BaseModel): temp_password: str

@router.post("/users/{id}/reset-password")
def reset_pw(id: int, d: Reset, db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    x = db.get(models.User, id)
    if not x: raise HTTPException(404)
    if len(d.temp_password) < 10: raise HTTPException(422, "At least 10 characters")
    x.password_hash = hash_password(d.temp_password); x.must_change_password = True
    audit.log(db, u, "reset_password", "user", id); db.commit(); return {"ok": True}

@router.get("/settings")
def get_settings(db: Session = Depends(get_db), u=Depends(current_user)):
    from ..config import OCR_PROVIDER, DEMO_MODE
    s = {r.key: r.value for r in db.scalars(select(models.Setting))}
    return {"company_name": s.get("company_name", ""), "vat_number": s.get("vat_number", ""), "currency": s.get("currency", "EUR"), "ocr_provider": OCR_PROVIDER, "demo": DEMO_MODE}

@router.put("/settings")
def put_settings(d: dict, db: Session = Depends(get_db), u=Depends(require("users_dummy"))):
    for k in ("company_name", "vat_number", "currency"):
        if k in d:
            row = db.get(models.Setting, k) or models.Setting(key=k); row.value = str(d[k]); db.add(row)
    audit.log(db, u, "update_settings", "settings", "", None, d); db.commit(); return {"ok": True}

@router.post("/notifications/read-all")
def read_all(db: Session = Depends(get_db), u=Depends(current_user)):
    for n in db.scalars(select(models.Notification).where(models.Notification.read == False)): n.read = True
    db.commit(); return {"ok": True}
