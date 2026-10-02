"""BANK INTEGRATION LAYER. The app only talks to this interface, never to a specific bank.
To add a bank/Open Banking provider: subclass BankProvider, implement the methods, register it in banking/__init__.py."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

@dataclass
class RawTransaction:
    external_id: str
    booked_on: date
    amount_cents: int      # + incoming, - outgoing
    reference: str = ""
    counterparty: str = ""

@dataclass
class PaymentResult:
    provider_ref: str
    status: str                       # AUTHORIZATION_REQUIRED | PROCESSING | COMPLETED | FAILED | REJECTED ...
    authorization_url: str | None = None  # bank's own login/approval page; the app never sees bank credentials

class BankProvider(ABC):
    name = "base"
    supports_payments = False

    @abstractmethod
    def get_balance(self, account) -> int: ...
    @abstractmethod
    def get_transactions(self, account, since: date | None = None) -> list[RawTransaction]: ...

    def initiate_payment(self, account, iban: str, amount_cents: int, reference: str) -> PaymentResult:
        raise NotImplementedError(f"{self.name} does not support payment initiation")
    def payment_status(self, provider_ref: str) -> str:
        raise NotImplementedError
