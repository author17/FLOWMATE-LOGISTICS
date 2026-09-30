"""Fake Open Banking provider to develop/test the payment workflow without a real bank.
Real providers (e.g. a licensed Open Banking aggregator) replace this class; the rest of the app is unchanged."""
import uuid
from .base import BankProvider, PaymentResult

class SandboxProvider(BankProvider):
    name = "sandbox"
    supports_payments = True
    _payments: dict[str, str] = {}

    def get_balance(self, account): return account.balance_cents
    def get_transactions(self, account, since=None): return []

    def initiate_payment(self, account, iban, amount_cents, reference):
        ref = "SBX-" + uuid.uuid4().hex[:10]
        self._payments[ref] = "AUTHORIZATION_REQUIRED"
        return PaymentResult(ref, "AUTHORIZATION_REQUIRED", f"https://sandbox-bank.example/authorize/{ref}")

    def payment_status(self, provider_ref):
        return self._payments.get(provider_ref, "UNKNOWN")

    # test helper simulating the bank's callback after the owner approves in the bank's own app
    def simulate_bank_approval(self, provider_ref, ok=True):
        self._payments[provider_ref] = "COMPLETED" if ok else "REJECTED"
