"""Offline placeholder so the review workflow works with no API key. Returns an empty template for the user to fill in."""
from .base import OcrProvider

class MockOcr(OcrProvider):
    def extract(self, data, filename):
        return {"supplier": "", "number": "", "date": "", "due_date": "", "total": 0, "vat": 0,
                "payment_method": "", "items": [], "confidence": 0, "note": "OCR disabled - fill in manually or set OCR_PROVIDER=claude"}
