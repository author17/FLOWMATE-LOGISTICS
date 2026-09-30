"""Payment state machine. COMPLETED can ONLY be set from provider-confirmed status."""
from datetime import datetime
from fastapi import HTTPException
from .. import models, audit
from ..banking import get_provider

STATES = {"PENDING", "AUTHORIZATION_REQUIRED", "PROCESSING", "COMPLETED", "FAILED", "REJECTED", "CANCELLED", "UNKNOWN"}
ALLOWED = {
    "PENDING": {"AUTHORIZATION_REQUIRED", "PROCESSING", "FAILED", "CANCELLED"},
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
        inv.status = "PAID"; audit.notify(db, "payment", f"Payment {pr.id} completed for invoice {inv.number}")
    elif new in ("FAILED", "REJECTED", "CANCELLED"):
        inv.status = "UNPAID"; audit.notify(db, "payment_failed", f"Payment {pr.id} {new.lower()} for invoice {inv.number}")

def create_payment(db, inv, account, user):
    if inv.status == "PAID": raise HTTPException(409, "Invoice already paid")
    sup = db.get(models.Supplier, inv.supplier_id)
    if not sup or not sup.iban: raise HTTPException(422, "Supplier has no IBAN on file")
    prov = get_provider(account.provider)
    if not prov.supports_payments: raise HTTPException(422, f"Bank provider '{account.provider}' cannot initiate payments. Pay in your bank app and import the statement; it will auto-match.")
    pr = models.PaymentRequest(invoice_id=inv.id, account_id=account.id, amount_cents=inv.total_cents, created_by=user.id)
    db.add(pr); db.flush()
    audit.log(db, user, "payment_created", "payment_request", pr.id, None, {"invoice": inv.number, "amount_cents": inv.total_cents})
    result = prov.initiate_payment(account, sup.iban, inv.total_cents, f"INV {inv.number}")
    pr.provider_ref, pr.authorization_url = result.provider_ref, result.authorization_url
    transition(db, pr, result.status, user)
    inv.status = "PAYMENT_PENDING"
    return pr

def refresh(db, pr, user=None):
    prov = get_provider(db.get(models.BankAccount, pr.account_id).provider)
    st = prov.payment_status(pr.provider_ref)
    if st != pr.status and st in STATES:
        transition(db, pr, st, user)
    return pr
