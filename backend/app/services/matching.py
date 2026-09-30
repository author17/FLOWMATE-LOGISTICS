"""Automatic payment matching. Score each candidate; >=90 auto-reconciles, 50-89 = suggestion, else stays UNMATCHED."""
import re
from sqlalchemy import select
from sqlalchemy.orm import Session
from .. import models, audit

AUTO, SUGGEST = 90, 50

def _norm(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def score_incoming(tx, order) -> tuple[int, str]:
    s, why = 0, []
    if tx.amount_cents == order.total_cents: s += 50; why.append("amount equal")
    if re.search(rf"order[-\s#_]*0*{order.id}\b", tx.reference, re.I): s += 50; why.append("reference names order")
    elif order.customer_id and _norm(tx.counterparty) and _norm(tx.counterparty) in _norm(getattr(order, "_cname", "")): s += 25; why.append("customer name")
    return min(s, 100), ", ".join(why)

def score_outgoing(tx, inv, supplier) -> tuple[int, str]:
    s, why = 0, []
    if -tx.amount_cents == inv.total_cents: s += 50; why.append("amount equal")
    if _norm(inv.number) and _norm(inv.number) in _norm(tx.reference): s += 40; why.append("invoice number in reference")
    if supplier and _norm(supplier.name)[:6] and _norm(supplier.name)[:6] in _norm(tx.counterparty): s += 10; why.append("supplier name")
    return min(s, 100), ", ".join(why)

def apply_match(db, tx, target_type, target_id, confidence, reason, user=None, confirmed=True):
    db.add(models.PaymentMatch(transaction_id=tx.id, target_type=target_type, target_id=target_id, confidence=confidence, confirmed=confirmed, reason=reason))
    if confirmed:
        tx.match_status = "RECONCILED"
        if target_type == "order":
            o = db.get(models.Order, target_id); old = o.status; o.status = "PAID"
            audit.log(db, user, "order_paid_by_bank_match", "order", o.id, {"status": old}, {"status": "PAID", "tx": tx.id})
        elif target_type == "invoice":
            i = db.get(models.Invoice, target_id); old = i.status; i.status = "PAID"
            audit.log(db, user, "invoice_paid_by_bank_match", "invoice", i.id, {"status": old}, {"status": "PAID", "tx": tx.id})
    else:
        tx.match_status = "SUGGESTED"

def run_matching(db: Session, user=None) -> dict:
    res = {"reconciled": 0, "suggested": 0, "unmatched": 0}
    txs = db.scalars(select(models.BankTransaction).where(models.BankTransaction.match_status == "UNMATCHED")).all()
    for tx in txs:
        best = (0, None, None, "")
        if tx.amount_cents > 0:
            for o in db.scalars(select(models.Order).where(models.Order.status.in_(["NEW", "PROCESSING", "COMPLETED"]))):
                if o.customer_id:
                    c = db.get(models.Customer, o.customer_id); o._cname = c.name if c else ""
                sc, why = score_incoming(tx, o)
                if sc > best[0]: best = (sc, "order", o.id, why)
        else:
            for i in db.scalars(select(models.Invoice).where(models.Invoice.status != "PAID")):
                sup = db.get(models.Supplier, i.supplier_id)
                sc, why = score_outgoing(tx, i, sup)
                if sc > best[0]: best = (sc, "invoice", i.id, why)
        sc, tt, tid, why = best
        if sc >= AUTO: apply_match(db, tx, tt, tid, sc, why, user); res["reconciled"] += 1
        elif sc >= SUGGEST: apply_match(db, tx, tt, tid, sc, why, user, confirmed=False); res["suggested"] += 1
        else: res["unmatched"] += 1
    db.commit()
    return res
