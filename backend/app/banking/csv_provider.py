"""Works with every bank today: import the statement CSV the bank lets you download.
Accepts flexible headers: date, amount (or debit/credit), reference/description, counterparty/name, id."""
import csv, io, hashlib
from datetime import datetime, date
from .base import BankProvider, RawTransaction

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"]

def _date(s: str) -> date:
    for f in DATE_FORMATS:
        try: return datetime.strptime(s.strip(), f).date()
        except ValueError: pass
    raise ValueError(f"Unrecognised date: {s}")

def _cents(s: str) -> int:
    s = s.strip().replace(" ", "").replace("€", "")
    if not s: return 0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    return round(float(s) * 100)

def parse_csv(text: str) -> list[RawTransaction]:
    sample = text[:2000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    rows = csv.DictReader(io.StringIO(text), delimiter=delim)
    out = []
    for r in rows:
        r = {(k or "").strip().lower(): (v or "") for k, v in r.items()}
        d = r.get("date") or r.get("booking date") or r.get("booked")
        if not d: continue
        if r.get("amount"): amt = _cents(r["amount"])
        else: amt = _cents(r.get("credit", "")) - _cents(r.get("debit", ""))
        ref = r.get("reference") or r.get("description") or r.get("details") or ""
        cp = r.get("counterparty") or r.get("name") or ""
        ext = r.get("id") or hashlib.sha1(f"{d}|{amt}|{ref}|{cp}".encode()).hexdigest()[:20]
        out.append(RawTransaction(ext, _date(d), amt, ref.strip(), cp.strip()))
    return out

class CsvProvider(BankProvider):
    name = "csv"
    def get_balance(self, account): return account.balance_cents
    def get_transactions(self, account, since=None): return []  # CSV is pushed via import endpoint
