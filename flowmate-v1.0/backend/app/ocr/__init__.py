from ..config import OCR_PROVIDER
from .mock import MockOcr

def get_ocr():
    if OCR_PROVIDER == "claude":
        from .claude_ocr import ClaudeOcr
        return ClaudeOcr()
    return MockOcr()
