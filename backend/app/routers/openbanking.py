"""Bank connection portal: the business owner links, syncs, reconnects and disconnects their own bank - no developer needed."""
import secrets, time
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from .. import config, models, audit
from ..crypto import encrypt
from ..db import get_db
from ..security import require
from ..services.openbanking import get_provider, ProviderError, DemoProvider
from ..services.banksync import sync_connection
from .crud import row

router = APIRouter(prefix="/api/bank", tags=["open-banking"])
REDIRECT = lambda: f"{config.APP_BASE_URL}/api/bank/callback"

def _prov(db):
    p = get_provider(db)
    if not p: raise HTTPException(422, "Bank connections are not set up yet. Add your Open Banking provider keys (Settings -> Bank connections).")
    return p

@router.get("/status")
def status(db: Session = Depends(get_db), u=Depends(require("banking_read"))):
    p = get_provider(db); src = "demo" if isinstance(p, DemoProvider) else "environment" if (config.ENABLEBANKING_APP_ID and config.ENABLEBANKING_PRIVATE_KEY) else "settings" if p else "none"
    return {"provider": p.name if p else "none", "configured": bool(p), "keys_from": src, "redirect_url": REDIRECT(), "auto_sync_hours": config.BANK_SYNC_HOURS}

class Creds(BaseModel): app_id: str; private_key: str

@router.put("/credentials")
def set_creds(d: Creds, db: Session = Depends(get_db), u=Depends(require("banking_admin"))):
    from cryptography.hazmat.primitives import serialization
    try: k = serialization.load_pem_private_key(d.private_key.strip().replace("\\n", "\n").encode(), password=None)
    except Exception: raise HTTPException(422, "That is not a valid PEM private key (it should start with -----BEGIN PRIVATE KEY-----)")
    for key, val in (("eb_app_id", d.app_id.strip()), ("eb_private_key", encrypt(d.private_key.strip().replace("\\n", "\n")))):
        r = db.get(models.Setting, key) or models.Setting(key=key); r.value = val; db.add(r)
    audit.log(db, u, "set_bank_provider_keys", "settings", "eb"); db.commit(); return {"ok": True}

@router.delete("/credentials")
def del_creds(db: Session = Depends(get_db), u=Depends(require("banking_admin"))):
    for key in ("eb_app_id", "eb_private_key"):
        r = db.get(models.Setting, key)
        if r: db.delete(r)
    audit.log(db, u, "remove_bank_provider_keys", "settings", "eb"); db.commit(); return {"ok": True}

@router.get("/institutions")
def institutions(country: str = "CY", psu_type: str = "business", db: Session = Depends(get_db), u=Depends(require("banking_admin"))):
    try: return _prov(db).institutions(country.upper(), psu_type)
    except ProviderError as e: raise HTTPException(502, f"Provider error: {e}")

def _conn_out(db, c):
    accts = db.scalars(select(models.BankAccount).where(models.BankAccount.connection_id == c.id)).all()
    days = (c.consent_expires_at - datetime.utcnow()).days if c.consent_expires_at else None
    return {**{k: v for k, v in row(c).items() if k not in ("state", "session_id", "authorization_id")}, "days_left": days, "needs_reconnect": c.status in ("EXPIRED", "ERROR") or (days is not None and days < 14),
            "accounts": [{"id": a.id, "iban": a.iban, "name": a.name, "balance_cents": a.balance_cents, "available_cents": a.available_cents, "currency": a.currency, "balance_at": str(a.balance_at) if a.balance_at else None} for a in accts]}

@router.get("/connections")
def connections(db: Session = Depends(get_db), u=Depends(require("banking_read"))):
    return [_conn_out(db, c) for c in db.scalars(select(models.BankConnection).where(models.BankConnection.status != "DISCONNECTED").order_by(models.BankConnection.id.desc()))]

class Connect(BaseModel): institution: str; country: str = "CY"; psu_type: str = "business"

def _begin(db, prov, conn, user):
    state = f"{int(time.time())}.{secrets.token_urlsafe(24)}"
    try: a = prov.start_auth(conn.institution, conn.country, conn.psu_type, state, REDIRECT(), 90)
    except ProviderError as e: raise HTTPException(502, f"The provider refused: {e}")
    conn.state, conn.authorization_id = state, a.get("authorization_id"); return a["url"]

@router.post("/connections", status_code=201)
def connect(d: Connect, db: Session = Depends(get_db), u=Depends(require("banking_admin"))):
    prov = _prov(db)
    if d.psu_type not in ("business", "personal"): raise HTTPException(422, "psu_type must be business or personal")
    c = models.BankConnection(provider=prov.name, institution=d.institution, country=d.country.upper(), psu_type=d.psu_type, created_by=u.id); db.add(c); db.flush()
    url = _begin(db, prov, c, u); audit.log(db, u, "bank_connect_start", "bank_connection", c.id, None, {"institution": d.institution}); db.commit()
    return {"id": c.id, "authorization_url": url}

@router.post("/connections/{id}/reconnect")
def reconnect(id: int, db: Session = Depends(get_db), u=Depends(require("banking_admin"))):
    c = db.get(models.BankConnection, id)
    if not c or c.status == "DISCONNECTED": raise HTTPException(404)
    url = _begin(db, _prov(db), c, u); audit.log(db, u, "bank_reconnect_start", "bank_connection", id); db.commit(); return {"authorization_url": url}

@router.get("/callback")
def callback(code: str | None = None, state: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    """The bank sends the browser back here after the owner approved (or refused) on the bank's own page."""
    fail = lambda why: RedirectResponse(f"/?bank=failed&reason={why}")
    c = db.scalar(select(models.BankConnection).where(models.BankConnection.state == state)) if state else None
    if not c: return fail("unknown_or_used_link")
    try:
        if int(state.split(".")[0]) < time.time() - 3600: c.state = None; db.commit(); return fail("link_expired")
    except Exception: return fail("bad_state")
    if error or not code: c.state = None; c.last_error = f"Bank access was not granted ({error or 'no code'})"; db.commit(); return fail("not_granted")
    c.state = None   # one-time use
    try: s = get_provider(db).create_session(code)
    except (ProviderError, AttributeError) as e: c.status, c.last_error = "ERROR", str(e)[:300]; db.commit(); return fail("provider_error")
    c.session_id, c.status, c.consent_expires_at, c.last_error, c.warned_expiry = s["session_id"], "ACTIVE", s["valid_until"], None, False
    for a in s["accounts"]:
        acc = db.scalar(select(models.BankAccount).where(models.BankAccount.connection_id == c.id, models.BankAccount.external_uid == a["uid"])) or \
              (db.scalar(select(models.BankAccount).where(models.BankAccount.iban == a["iban"], models.BankAccount.provider != "csv")) if a["iban"] else None)
        if not acc: acc = models.BankAccount(name=a["name"] or c.institution); db.add(acc)
        acc.iban, acc.provider, acc.connection_id, acc.external_uid, acc.currency = a["iban"], c.provider, c.id, a["uid"], a["currency"]
    db.flush(); audit.log(db, None, "bank_connected", "bank_connection", c.id, None, {"institution": c.institution, "accounts": len(s["accounts"])})
    try: sync_connection(db, c)
    except Exception: pass
    db.commit(); return RedirectResponse("/?bank=connected")

@router.post("/connections/{id}/sync")
def sync(id: int, db: Session = Depends(get_db), u=Depends(require("banking_admin"))):
    c = db.get(models.BankConnection, id)
    if not c: raise HTTPException(404)
    try: return sync_connection(db, c, u)
    except ProviderError as e: raise HTTPException(502, str(e))

@router.delete("/connections/{id}")
def disconnect(id: int, db: Session = Depends(get_db), u=Depends(require("banking_admin"))):
    """Stops bank access immediately. Past transactions stay in your records."""
    c = db.get(models.BankConnection, id)
    if not c: raise HTTPException(404)
    if c.session_id:
        try: get_provider(db).delete_session(c.session_id)
        except Exception: pass   # still disconnect on our side even if the provider call fails
    c.status, c.session_id, c.state = "DISCONNECTED", None, None
    audit.log(db, u, "bank_disconnected", "bank_connection", id, None, {"institution": c.institution}); db.commit(); return {"ok": True}

@router.get("/demo-consent", response_class=HTMLResponse)
def demo_consent(state: str):
    if not config.DEMO_MODE: raise HTTPException(404)
    return f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><body style="font-family:system-ui;max-width:420px;margin:12vh auto;padding:16px">
<h2>Demo Bank</h2><p>This is a <b>practice</b> bank page. <b>FLOWMATE</b> asks to read your balances and transactions (read-only) for 90 days.</p>
<p><a href="/api/bank/callback?code=demo&state={state}" style="background:#1f6feb;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none">Approve access</a>
&nbsp; <a href="/api/bank/callback?error=access_denied&state={state}">Deny</a></p><p style="color:#666;font-size:13px">A real bank shows its own secure login here. FLOWMATE never sees your bank password.</p>"""
