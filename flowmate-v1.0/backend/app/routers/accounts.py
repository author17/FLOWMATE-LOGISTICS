"""Self-service sign-up of a new business, and account deletion (required by Google Play and the App Store)."""
import re, secrets, time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select, delete, text
from sqlalchemy.orm import Session
from .. import config, models, audit
from ..db import get_db, engine
from ..security import hash_password, make_token, current_user, verify_password
from ..tenancy import use_business, put_setting
from ..businesstypes import KINDS, kind_info

router = APIRouter(prefix="/api", tags=["accounts"])
_signups: dict[str, list[float]] = {}

def _slug(db, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "business"
    s = base
    while db.scalar(select(models.Business.id).where(models.Business.slug == s)): s = f"{base}-{secrets.token_hex(2)}"
    return s

class SignUp(BaseModel):
    business_name: str; kind: str = "general"; owner_name: str; email: str; password: str; accept_terms: bool = False

@router.post("/signup", status_code=201)
def signup(d: SignUp, request: Request, db: Session = Depends(get_db)):
    if not config.SIGNUP_ENABLED: raise HTTPException(403, "New accounts are not open yet")
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "x")).split(",")[0].strip()
    now = time.time(); h = [t for t in _signups.get(ip, []) if now - t < 3600]
    if len(h) >= config.SIGNUPS_PER_IP_HOUR: raise HTTPException(429, "Too many sign-ups from this connection. Try again later.")
    if not d.accept_terms: raise HTTPException(422, "Please accept the Terms and the Privacy Policy")
    name, email = d.business_name.strip(), d.email.strip().lower()
    if len(name) < 2 or not d.owner_name.strip(): raise HTTPException(422, "Enter the business name and your name")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email): raise HTTPException(422, "Enter a valid e-mail address")
    if len(d.password) < 10: raise HTTPException(422, "Password must be at least 10 characters")
    if d.kind not in KINDS: raise HTTPException(422, "Pick a business type")
    if db.scalar(select(models.User.id).where(models.User.email == email)): raise HTTPException(409, "This e-mail already has an account. Log in instead.")
    h.append(now); _signups[ip] = h
    info = kind_info(d.kind)
    b = models.Business(name=name[:150], slug=_slug(db, name), kind=d.kind, inbound_token=secrets.token_urlsafe(24), signup_ip=ip[:60], terms_accepted_at=datetime.utcnow())
    db.add(b); db.flush()
    use_business(db, b.id)
    db.add(models.Location(name="Main", kind=info["location_kind"]))
    for c in info["categories"]: db.add(models.Category(name=c))
    db.add(models.BankAccount(name="Main bank account", provider="csv"))
    u = models.User(name=d.owner_name.strip()[:100], email=email, password_hash=hash_password(d.password), role="owner", must_change_password=False)
    db.add(u); put_setting(db, "company_name", name)
    db.flush(); audit.log(db, u, "signup", "business", b.id, None, {"kind": d.kind}); db.commit()
    return {"access_token": make_token(u), "token_type": "bearer"}

@router.get("/business-types")
def business_types(): return [{"kind": k, "label": v["label"]} for k, v in KINDS.items()]

# ---------------- account deletion ----------------
class DeleteMe(BaseModel): password: str

@router.post("/account/delete-me")
def delete_me(d: DeleteMe, db: Session = Depends(get_db), u=Depends(current_user)):
    """A staff member removes their own login (their name disappears; business records they created stay). The owner uses /account/delete-business."""
    if u.role == "owner": raise HTTPException(409, "You are the owner: delete the whole business instead (Settings > Delete account)")
    if not verify_password(d.password, u.password_hash): raise HTTPException(401, "Password is wrong")
    audit.log(db, u, "account_deleted", "user", u.id)
    u.active, u.name, u.email = False, "Deleted user", f"deleted-{u.id}-{secrets.token_hex(3)}@deleted.invalid"
    u.password_hash = hash_password(secrets.token_urlsafe(24)); u.phone = u.totp_secret = u.recovery_codes = u.mfa_method = None; u.totp_enabled = False
    u.token_version = (u.token_version or 0) + 1; db.commit(); return {"ok": True}

class DeleteBiz(BaseModel): password: str; confirm_name: str

def erase_business(business_id: int):
    """Permanently removes a business: every row of every table, and its uploaded files."""
    from ..config import STORAGE_DIR
    with engine.begin() as cx:
        keys = [r[0] for r in cx.execute(text("SELECT storage_key FROM documents WHERE business_id = :b"), {"b": business_id})]
        for t in reversed(models.Base.metadata.sorted_tables):
            if t.name == "businesses": continue
            cx.execute(delete(t).where(t.c.business_id == business_id))
        cx.execute(delete(models.Business.__table__).where(models.Business.__table__.c.id == business_id))
    for k in keys:
        try: (STORAGE_DIR / k).unlink(missing_ok=True)
        except Exception: pass
    import shutil; shutil.rmtree(STORAGE_DIR / f"b{business_id}", ignore_errors=True)

@router.post("/account/delete-business")
def delete_business(d: DeleteBiz, db: Session = Depends(get_db), u=Depends(current_user)):
    if u.role != "owner": raise HTTPException(403, "Only the owner can delete the business")
    b = db.get(models.Business, u.business_id)
    if not verify_password(d.password, u.password_hash): raise HTTPException(401, "Password is wrong")
    if d.confirm_name.strip().lower() != b.name.strip().lower(): raise HTTPException(422, "Type the business name exactly to confirm")
    bid = b.id; db.close(); erase_business(bid); return {"ok": True}
