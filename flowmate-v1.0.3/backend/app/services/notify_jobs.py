"""Scheduled notification work: invoice due / overdue reminders, and e-mailing important notifications to the owners."""
from datetime import date, datetime, timedelta
from sqlalchemy import select
from .. import models
from . import mailer

EMAIL_KINDS = {"invoice_due", "invoice_overdue", "payment_pending", "bank_problem", "payment_failed", "cash_difference", "stripe_mismatch", "doc_to_verify"}

def _once(db, kind, message, days=1):
    since = datetime.utcnow() - timedelta(days=days)
    return db.scalar(select(models.Notification).where(models.Notification.kind == kind, models.Notification.message == message, models.Notification.created_at >= since)) is None

def due_reminders(db) -> int:
    n, today = 0, date.today()
    for i in db.scalars(select(models.Invoice).where(models.Invoice.status != "PAID", models.Invoice.due_date.is_not(None))):
        s = db.get(models.Supplier, i.supplier_id); who = f"{s.name if s else ''} invoice {i.number} ({i.total_cents/100:.2f} EUR)"
        if i.due_date < today: kind, msg, win = "invoice_overdue", f"OVERDUE: {who} was due {i.due_date:%d/%m/%Y}", 3
        elif i.due_date <= today + timedelta(days=3): kind, msg, win = "invoice_due", f"Due soon: {who} is due {i.due_date:%d/%m/%Y}", 2
        else: continue
        if _once(db, kind, msg, win): db.add(models.Notification(kind=kind, message=msg)); n += 1
    db.commit(); return n

def email_pending(db) -> int:
    if not mailer.configured(): return 0
    owners = [u.email for u in db.scalars(select(models.User).where(models.User.active == True, models.User.role.in_(["owner", "manager"])))]
    todo = [x for x in db.scalars(select(models.Notification).where(models.Notification.emailed == False, models.Notification.kind.in_(EMAIL_KINDS)))]
    if todo and owners:
        try: mailer.send_email(owners, f"FLOWMATE: {len(todo)} notification(s)", "\n\n".join(f"- {x.message}" for x in todo))
        except Exception: return 0
    for x in db.scalars(select(models.Notification).where(models.Notification.emailed == False)): x.emailed = True
    db.commit(); return len(todo)
