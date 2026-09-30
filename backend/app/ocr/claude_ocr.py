"""Reads receipts/invoices (photo or PDF) with Claude vision. Needs ANTHROPIC_API_KEY. Output is ALWAYS reviewed by a human before saving."""
import base64, json, mimetypes, httpx
from .base import OcrProvider, EXTRACT_FIELDS
from ..config import ANTHROPIC_API_KEY

class ClaudeOcr(OcrProvider):
    model = "claude-sonnet-4-5"
    def extract(self, data, filename):
        mt = mimetypes.guess_type(filename)[0] or "image/jpeg"
        kind = "document" if mt == "application/pdf" else "image"
        block = {"type": kind, "source": {"type": "base64", "media_type": mt, "data": base64.b64encode(data).decode()}}
        prompt = f"Extract these fields from this business document as pure JSON, no prose: {EXTRACT_FIELDS}. Use numbers for money (e.g. 12.50). Use null if unknown. Add a 'confidence' 0-100."
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=60,
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
            json={"model": self.model, "max_tokens": 1500, "messages": [{"role": "user", "content": [block, {"type": "text", "text": prompt}]}]})
        r.raise_for_status()
        text = r.json()["content"][0]["text"].strip().strip("`")
        if text.startswith("json"): text = text[4:]
        j = json.loads(text)
        j["supplier"] = j.pop("merchant_or_supplier", j.get("supplier", ""))
        return j
