"""Stripe Checkout via plain REST (no SDK needed). Card details never touch this app - Stripe hosts the payment page."""
import hmac, hashlib, time, httpx
from .. import config

API = "https://api.stripe.com/v1"

def secret_key(db) -> str:
    """Each business uses ITS OWN Stripe account (keys pasted in Settings, stored encrypted). Business #1 may also use the server's environment keys."""
    from ..tenancy import get_setting; from ..crypto import decrypt
    v = decrypt(get_setting(db, "stripe_secret"))
    return v or (config.STRIPE_SECRET_KEY if db.info.get("business_id") == 1 else "")

def webhook_secret(db) -> str:
    from ..tenancy import get_setting; from ..crypto import decrypt
    v = decrypt(get_setting(db, "stripe_webhook_secret"))
    return v or (config.STRIPE_WEBHOOK_SECRET if db.info.get("business_id") == 1 else "")

def configured(db) -> bool: return bool(secret_key(db))
def mode(db) -> str:
    k = secret_key(db); return "live" if k.startswith(("sk_live", "rk_live")) else "test" if k else "off"

def create_checkout(db, amount_cents: int, name: str, target_type: str, target_id: int, email: str | None = None) -> dict:
    data = {"mode": "payment", "success_url": f"{config.APP_BASE_URL}/?paid=1", "cancel_url": f"{config.APP_BASE_URL}/?paid=0",
            "line_items[0][quantity]": "1", "line_items[0][price_data][currency]": "eur", "line_items[0][price_data][unit_amount]": str(amount_cents),
            "line_items[0][price_data][product_data][name]": name, "metadata[target_type]": target_type, "metadata[target_id]": str(target_id),
            "client_reference_id": f"{target_type}-{target_id}", "expires_at": str(int(time.time()) + 23 * 3600)}
    if email: data["customer_email"] = email
    r = httpx.post(f"{API}/checkout/sessions", data=data, headers={"Authorization": f"Bearer {secret_key(db)}"}, timeout=30)
    if r.status_code >= 400: raise RuntimeError(r.json().get("error", {}).get("message", "Stripe error"))
    j = r.json(); return {"id": j["id"], "url": j["url"]}

def verify_signature(payload: bytes, header: str, secret: str, tolerance: int = 300, now: float | None = None) -> bool:
    """Stripe-Signature: t=timestamp,v1=hmac_sha256(secret, f"{t}.{payload}")"""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        t = parts["t"]; sigs = [v for k, v in (p.split("=", 1) for p in header.split(",")) if k == "v1"]
    except Exception: return False
    if abs((now or time.time()) - int(t)) > tolerance: return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in sigs)

def refund(db, payment_intent: str, amount_cents: int) -> dict:
    r = httpx.post(f"{API}/refunds", data={"payment_intent": payment_intent, "amount": str(amount_cents)}, headers={"Authorization": f"Bearer {secret_key(db)}"}, timeout=30)
    if r.status_code >= 400: raise RuntimeError(r.json().get("error", {}).get("message", "Stripe error"))
    return r.json()
