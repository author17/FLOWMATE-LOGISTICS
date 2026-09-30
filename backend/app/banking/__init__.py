from .base import BankProvider
from .csv_provider import CsvProvider
from .sandbox_provider import SandboxProvider

_registry: dict[str, BankProvider] = {"csv": CsvProvider(), "sandbox": SandboxProvider()}

def get_provider(name: str) -> BankProvider:
    if name not in _registry: raise KeyError(f"Unknown bank provider: {name}")
    return _registry[name]
