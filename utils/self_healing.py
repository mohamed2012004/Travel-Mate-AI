from prompt_catalog.catalog import FIREWALL_INSTRUCTION
from prompt_catalog.util_healing import sanitize_text, wrap_untrusted

__all__ = [
    "FIREWALL_INSTRUCTION",
    "sanitize_text",
    "wrap_untrusted",
    "sanitize_agent_result",
]


def sanitize_agent_result(text, agent_name="agent"):
    cleaned, findings = sanitize_text(text or "")
    return cleaned, findings
