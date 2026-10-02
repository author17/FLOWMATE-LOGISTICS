"""Payment state machine. COMPLETED can ONLY be set from provider-confirmed status."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from .. import models, audit
from ..banking import get_provider

STATES = {"APPROVED", "PENDING", "AUTHORIZATION_REQUIRED", "PROCESSING", "COMPLETED", "FAILED", "REJECTED", "CANCELLED", "UNKNOWN"}
ALLOWED = {
    "PENDING": {"APPROVED", "AUTHORIZATION_REQUIRED", "PROCESSING", "FAILED", "CANCELLED"},
    "APPROVED": {"COMPLETED", "CANCELLED", "FAILED"},
    "AUTHORIZATION_REQUIRED": {"PROCESSING", "COMPLETED", "REJECTED", "CANCELLED", "FAILED", "UNKNOWN"},
    "PROCESSING": {"COMPLETED", "FAILED", "REJECTED", "UNKNOWN"},
    "UNKNOWN": {"COMPLETED", "FAILED", "REJECTED", "PROCESSING"},
}

def transition(db, pr, new, user=None):
    if new not in ALLOWED.get(pr.status, set()):
        raise HTTPException(409, f"Illegal payment transition {pr.status} -> {new}")
    old = pr.status; pr.status = new; pr.updated_at = datetime.utcnow()
    audit.log(db, user, "payment_status_change", "payment_request", pr.id, {"status": old}, {"status": new})
    inv = db.get(models.Invoice, pr.invoice_id)
    if new == "COMPLETED":
        inv.status = "PAID"; inv.paid_on = datetime.utcnow().date(); inv.paid_method = "BANK_API"; audit.notify(db, "payment", f"Payment {pr.id} completed for invoice {inv.number}")
    elif new in ("FAILED", "REJECTED", "CANCELLED"):
        inv.status = "UNPAID"; audit.notify(db, "payment_failed", f"Payment {pr.id} {new.lower()} for invoice {inv.number}")

def prepare_payment(db, inv, account, user):
    """Step 1 (payment user): prepare. Nothing is sent to any bank yet."""
    if inv.status == "PAID": raise HTTPException(409, "Invoice already paid")
    if inv.status == "PAYMENT_PENDING": raise HTTPException(409, "A payment is already prepared for this invoice")
    sup = db.get(models.Supplier, inv.supplier_id)
    if not sup or not sup.iban: raise HTTPException(422, "Supplier has no IBAN on file - add it on the supplier profile")
    pr = models.PaymentRequest(invoice_id=inv.id, account_id=account.id, amount_cents=inv.total_cents, created_by=user.id)
    db.add(pr); db.flush(); inv.status = "PAYMENT_PENDING"
    audit.log(db, user, "payment_prepared", "payment_request", pr.id, None, {"invoice": inv.number, "amount_cents": inv.total_cents})
    audit.notify(db, "payment_pending", f"Supplier payment waiting for approval: {sup.name} invoice {inv.number}, {inv.total_cents/100:.2f} EUR")
    return pr

def approve_payment(db, pr, user):
    """Step 2 (owner): approve. Banks that allow it get the payment request now; the bank still asks the owner to authorise on its own page.
    Otherwise the owner pays in the bank's own app and the statement line completes it automatically."""
    if pr.status != "PENDING": raise HTTPException(409, f"Payment is {pr.status}")
    inv = db.get(models.Invoice, pr.invoice_id); acc = db.get(models.BankAccount, pr.account_id); sup = db.get(models.Supplier, inv.supplier_id)
    audit.log(db, user, "payment_approved", "payment_request", pr.id)
    prov = get_provider(acc.provider)
    if not prov.supports_payments: transition(db, pr, "APPROVED", user); return pr
    result = prov.initiate_payment(acc, sup.iban, pr.amount_cents, f"INV {inv.number}")
    pr.provider_ref, pr.authorization_url = result.provider_ref, result.authorization_url
    transition(db, pr, result.status, user); return pr

def reject_payment(db, pr, user, why=""):
    if pr.status not in ("PENDING", "APPROVED"): raise HTTPException(409, f"Payment is {pr.status}")
    transition(db, pr, "CANCELLED", user); audit.log(db, user, "payment_rejected", "payment_request", pr.id, None, {"reason": why})

def complete_by_statement(db, invoice_id, user=None):
    """A matching bank statement line is the bank's confirmation - close any open payment request for that invoice."""
    for pr in db.scalars(select(models.PaymentRequest).where(models.PaymentRequest.invoice_id == invoice_id, models.PaymentRequest.status.in_(["APPROVED", "PENDING", "AUTHORIZATION_REQUIRED", "PROCESSING", "UNKNOWN"]))):
        old = pr.status; pr.status, pr.updated_at = "COMPLETED", datetime.utcnow(); audit.log(db, user, "payment_completed_by_statement", "payment_request", pr.id, {"status": old}, {"status": "COMPLETED"})

def refresh(db, pr, user=None):
    prov = get_provider(db.get(models.BankAccount, pr.account_id).provider)
    st = prov.payment_status(pr.provider_ref)
    if pr.status in ("PENDING", "APPROVED"): return pr
    if st != pr.status and st in STATES:
        transition(db, pr, st, user)
    return pr
