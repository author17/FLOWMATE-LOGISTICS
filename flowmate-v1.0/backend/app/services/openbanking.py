"""Open Banking providers behind one interface. The app never handles bank passwords: the owner authenticates on the BANK's own page.
EnableBankingProvider follows the documented REST API (JWT RS256 app key). DemoProvider simulates a bank so the whole portal works with no credentials."""
import time, uuid, jwt, httpx, hashlib, random
from datetime import datetime, timedelta, date
from .. import config

class ProviderError(Exception): pass

class EnableBankingProvider:
    name = "enablebanking"; base = "https://api.enablebanking.com"
    def __init__(self, app_id: str, private_key: str, client: httpx.Client | None = None):
        self.app_id, self.key = app_id, private_key; self.http = client or httpx.Client(timeout=40)
    def _headers(self):
        now = int(time.time())
        tok = jwt.encode({"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": now, "exp": now + 3600}, self.key, algorithm="RS256", headers={"typ": "JWT", "kid": self.app_id})
        return {"Authorization": f"Bearer {tok}"}
    def _call(self, method, path, **kw):
        r = self.http.request(method, self.base + path, headers=self._headers(), **kw)
        if r.status_code >= 400:
            try: msg = r.json().get("message") or r.json().get("error") or r.text
            except Exception: msg = r.text
            raise ProviderError(f"{r.status_code}: {str(msg)[:200]}")
        return r.json() if r.content else {}
    def institutions(self, country, psu_type="business"):
        rows = self._call("GET", "/aspsps", params={"country": country, "psu_type": psu_type}).get("aspsps", [])
        return [{"name": a["name"], "country": a.get("country", country), "max_consent_days": int((a.get("maximum_consent_validity") or 7776000) / 86400), "logo": a.get("logo")} for a in rows]
    def start_auth(self, institution, country, psu_type, state, redirect_url, valid_days):
        valid_until = (datetime.utcnow() + timedelta(days=valid_days)).strftime("%Y-%m-%dT%H:%M:%S.000000+00:00")
        j = self._call("POST", "/auth", json={"access": {"valid_until": valid_until}, "aspsp": {"name": institution, "country": country}, "state": state, "redirect_url": redirect_url, "psu_type": psu_type})
        return {"url": j["url"], "authorization_id": j.get("authorization_id")}
    def create_session(self, code):
        j = self._call("POST", "/sessions", json={"code": code}); exp = (j.get("access") or {}).get("valid_until")
        accts = [{"uid": a.get("uid"), "iban": (a.get("account_id") or {}).get("iban") or a.get("iban") or "", "name": a.get("name") or (a.get("details") or ""), "currency": a.get("currency") or "EUR"} for a in j.get("accounts", [])]
        return {"session_id": j.get("session_id"), "accounts": accts, "valid_until": _dt(exp)}
    def balances(self, uid):
        b = self._call("GET", f"/accounts/{uid}/balances").get("balances", [])
        def amt(types):
            for t in types:
                for x in b:
                    if x.get("balance_type") == t: return round(float(x["balance_amount"]["amount"]) * 100)
        return {"booked": amt(["CLBD", "ITBD", "OPBD", "XPCD"]), "available": amt(["ITAV", "CLAV", "FWAV"])}
    def transactions(self, uid, date_from: date):
        out, key = [], None
        for _ in range(20):
            params = {"date_from": date_from.isoformat(), "transaction_status": "BOOK"}
            if key: params["continuation_key"] = key
            j = self._call("GET", f"/accounts/{uid}/transactions", params=params)
            for t in j.get("transactions", []):
                amt = round(float((t.get("transaction_amount") or {}).get("amount", 0)) * 100)
                if t.get("credit_debit_indicator") == "DBIT": amt = -abs(amt)
                party = (t.get("creditor") if amt < 0 else t.get("debtor")) or {}
                ref = " ".join(t.get("remittance_information") or []) or t.get("note") or ""
                d = t.get("booking_date") or t.get("value_date") or t.get("transaction_date")
                ext = t.get("entry_reference") or t.get("transaction_id") or hashlib.sha1(f"{d}|{amt}|{ref}|{party.get('name')}".encode()).hexdigest()[:24]
                out.append({"external_id": str(ext), "booked_on": date.fromisoformat(d[:10]), "amount_cents": amt, "reference": ref[:300], "counterparty": (party.get("name") or "")[:200]})
            key = j.get("continuation_key")
            if not key: break
        return out
    def delete_session(self, session_id): self._call("DELETE", f"/sessions/{session_id}")

def _dt(s):
    if not s: return None
    try: return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception: return None

class DemoProvider:
    """Fake 'Demo Bank' for practice mode and sales demos. Generates believable transactions; no real bank involved."""
    name = "demo"
    def institutions(self, country, psu_type="business"): return [{"name": "Demo Bank (practice)", "country": country, "max_consent_days": 90, "logo": None}]
    def start_auth(self, institution, country, psu_type, state, redirect_url, valid_days):
        return {"url": f"{config.APP_BASE_URL}/api/bank/demo-consent?state={state}", "authorization_id": "demo-" + state[:8]}
    def create_session(self, code):
        return {"session_id": "demo-session-" + uuid.uuid4().hex[:8], "accounts": [{"uid": "demo-acct-1", "iban": "CY17002001280000001200527600", "name": "Demo business account", "currency": "EUR"}], "valid_until": datetime.utcnow() + timedelta(days=90)}
    def balances(self, uid): return {"booked": 1_245_000, "available": 1_230_000}
    def transactions(self, uid, date_from):
        rnd = random.Random(42); out = []
        for i in range(12):
            d = date.today() - timedelta(days=i * 2); amt = rnd.choice([8500, 4200, 15750, -4500, -6320, -12050, -990])
            out.append({"external_id": f"demo-{d}-{i}", "booked_on": d, "amount_cents": amt, "reference": rnd.choice(["ORDER-1", "Electricity bill", "INV-5521 ABC Foods", "Card settlement", "Monthly membership"]), "counterparty": rnd.choice(["Maria Georgiou", "EAC", "ABC FOODS LTD", "Card acquirer"])})
        return [t for t in out if t["booked_on"] >= date_from]
    def delete_session(self, session_id): pass

def get_provider(db=None):
    """Env keys win; otherwise keys the owner pasted in Settings (stored encrypted); practice mode uses the demo bank."""
    if config.DEMO_MODE and not (config.ENABLEBANKING_APP_ID and config.ENABLEBANKING_PRIVATE_KEY): return DemoProvider()
    app_id, key = config.ENABLEBANKING_APP_ID, config.ENABLEBANKING_PRIVATE_KEY
    if db is not None and not (app_id and key):
        from .. import models; from ..crypto import decrypt
        from ..tenancy import get_setting
        a, k = get_setting(db, "eb_app_id"), get_setting(db, "eb_private_key")
        if a and k: app_id, key = a, decrypt(k) or ""
    return EnableBankingProvider(app_id, key) if app_id and key else None
