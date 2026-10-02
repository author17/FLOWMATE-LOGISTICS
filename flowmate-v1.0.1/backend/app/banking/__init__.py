from .base import BankProvider
from .csv_provider import CsvProvider
from .sandbox_provider import SandboxProvider

class ReadOnlyProvider(CsvProvider):
    """Open Banking account-information providers: balances/transactions arrive through the sync job; payments are made in the bank's own app."""
    def __init__(self, name): self.name = name

_registry: dict[str, BankProvider] = {"csv": CsvProvider(), "sandbox": SandboxProvider(), "enablebanking": ReadOnlyProvider("enablebanking"), "demo": ReadOnlyProvider("demo")}

def get_provider(name: str) -> BankProvider:
    if name not in _registry: raise KeyError(f"Unknown bank provider: {name}")
    return _registry[name]
