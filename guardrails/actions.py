import re
from typing import Optional

try:
    from nemoguardrails.actions import action
except Exception:
    def action(is_system_action=False):
        def decorator(fn):
            return fn
        return decorator

PII_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "phone": r"\b(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "api_key": r"(api[_\s-]?key|token|secret|password|passwd)[:\s]+[A-Za-z0-9_\-]{8,}",
    "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    "passport": r"(?i)passport(?:\s*(?:number|no\.?|#))?[:\s]+[A-Z0-9]{6,9}\b",
}

SENSITIVE_OUTPUT_PATTERNS = {
    "hardcoded_credential": r"(?i)(password|passwd|secret|api[_\-]?key|token)\s*[:=]\s*['\"]?\w{4,}",
    "private_key": r"-----BEGIN.{0,20}PRIVATE KEY-----",
    "exploit_technique": r"(?i)\b(reverse.?shell|bind.?shell|shellcode|meterpreter|exploit\s*code)\b",
    "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    "passport": r"(?i)passport(?:\s*(?:number|no\.?|#))?[:\s]+[A-Z0-9]{6,9}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
}

def find_pii(text: str) -> list[str]:
    return [k for k, pat in PII_PATTERNS.items() if re.search(pat, text or "", re.IGNORECASE)]

def find_sensitive_output(text: str) -> list[str]:
    return [k for k, pat in SENSITIVE_OUTPUT_PATTERNS.items() if re.search(pat, text or "", re.IGNORECASE)]

@action(is_system_action=True)
async def detect_pii_in_input(context: Optional[dict] = None):
    user_message = context.get("user_message", "") if context else ""
    return find_pii(user_message)

@action(is_system_action=True)
async def sanitize_output(context: Optional[dict] = None):
    bot_message = context.get("bot_message", "") if context else ""
    return find_sensitive_output(bot_message)
