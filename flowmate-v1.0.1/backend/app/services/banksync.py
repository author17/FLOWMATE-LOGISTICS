from datetime import datetime, timedelta, date
from sqlalchemy import select
from .. import models, audit
from .openbanking import get_provider, ProviderError
from . import matching

def sync_connection(db, conn, user=None, days_first=90) -> dict:
    prov = get_provider(db)
    if not prov: raise ProviderError("No Open Banking provider is configured")
    if conn.status not in ("ACTIVE", "ERROR"): raise ProviderError(f"Connection is {conn.status}")
    if conn.consent_expires_at and conn.consent_expires_at < datetime.utcnow():
        conn.status = "EXPIRED"; conn.last_error = "Bank consent expired - reconnect"; audit.notify(db, "bank_problem", f"Bank connection problem: {conn.institution} consent expired. Reconnect in Settings."); db.commit(); raise ProviderError(conn.last_error)
    added = 0
    try:
        for acc in db.scalars(select(models.BankAccount).where(models.BankAccount.connection_id == conn.id)):
            bal = prov.balances(acc.external_uid)
            if bal.get("booked") is not None: acc.balance_cents = bal["booked"]
            acc.available_cents = bal.get("available"); acc.balance_at = datetime.utcnow()
            since = (conn.last_sync_at.date() - timedelta(days=3)) if conn.last_sync_at else date.today() - timedelta(days=days_first)
            have = set(db.scalars(select(models.BankTransaction.external_id).where(models.BankTransaction.account_id == acc.id)))
            for t in prov.transactions(acc.external_uid, since):
                if t["external_id"] in have: continue
                db.add(models.BankTransaction(account_id=acc.id, **t)); have.add(t["external_id"]); added += 1
        conn.last_sync_at, conn.last_error = datetime.utcnow(), None
        if conn.status == "ERROR": conn.status = "ACTIVE"
    except ProviderError as e:
        first = conn.last_error is None
        conn.status, conn.last_error = "ERROR", str(e)[:300]
        if first: audit.notify(db, "bank_problem", f"Bank connection problem: {conn.institution} - {conn.last_error}")
        db.commit(); raise
    db.flush(); res = matching.run_matching(db, user) if added else {"reconciled": 0, "suggested": 0, "unmatched": 0}
    audit.log(db, user, "bank_sync", "bank_connection", conn.id, None, {"added": added}); db.commit()
    return {"added": added, **res}

def sync_all(db):
    out = []
    for c in db.scalars(select(models.BankConnection).where(models.BankConnection.status.in_(["ACTIVE", "ERROR"]))):
        try: out.append((c.id, sync_connection(db, c)))
        except Exception as e: out.append((c.id, {"error": str(e)}))
        if c.consent_expires_at and not c.warned_expiry and c.consent_expires_at - datetime.utcnow() < timedelta(days=14):
            c.warned_expiry = True; audit.notify(db, "bank_problem", f"Bank consent for {c.institution} expires on {c.consent_expires_at:%d/%m/%Y}. Reconnect in Settings before then."); db.commit()
    return out
