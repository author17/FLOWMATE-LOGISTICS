from abc import ABC, abstractmethod

EXTRACT_FIELDS = "doc_type, merchant_or_supplier, number, date (YYYY-MM-DD), due_date, currency, total, vat, payment_method, items[{description, quantity, unit_price}]"

class OcrProvider(ABC):
    @abstractmethod
    def extract(self, data: bytes, filename: str) -> dict:
        """Return a dict with keys: supplier, number, date, due_date, total, vat, payment_method, items, confidence."""
