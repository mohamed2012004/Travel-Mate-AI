import asyncio
import logging
from dataclasses import dataclass

from . import config
from .rails import get_rails, guard_enabled

logger = logging.getLogger(__name__)

@dataclass
class GuardResult:
    allowed: bool
    blocked: bool = False
    message: str = ""
    reason: str = ""
    canned: bool = False

async def check_output(text: str) -> GuardResult:
    if not guard_enabled() or not text:
        return GuardResult(True, False, text, "")
    rails = get_rails()
    if rails is None:
        return GuardResult(True, False, text, "nemo_unavailable_fail_open")
    try:
        result = await rails.check_async([{"role": "assistant", "content": text}])
        if str(result.status) == "RailStatus.BLOCKED" or getattr(result.status, "value", "") == "blocked":
            logger.warning("[guardrails] output blocked by NeMo rail %s", result.rail)
            return GuardResult(False, True, result.content, f"output:{result.rail}")
        return GuardResult(True, False, text, "")
    except Exception as error:
        logger.warning("[guardrails] output check failed, fail-open: %s", error)
        return GuardResult(True, False, text, "nemo_error_fail_open")

async def check_input(text: str) -> GuardResult:
    if not guard_enabled() or not (text or "").strip():
        return GuardResult(True)
    rails = get_rails()
    if rails is None:
        return GuardResult(True, False, "", "nemo_unavailable_fail_open")
    try:
        systematic = await rails.check_async([{"role": "user", "content": text}])
        if str(systematic.status) == "RailStatus.BLOCKED" or getattr(systematic.status, "value", "") == "blocked":
            rail_name = str(getattr(systematic, "rail", "") or "")
            if rail_name in config.CANNED:
                return GuardResult(True, False, config.CANNED[rail_name], rail_name, canned=True)
            blocked_content = systematic.content or config.CANNED.get("pii", "")
            return GuardResult(False, True, blocked_content, f"pii:{rail_name}", canned=True)
    except Exception as error:
        logger.warning("[guardrails] input systematic rails failed, fail-open: %s", error)
        return GuardResult(True, False, "", "nemo_error_fail_open")
    try:
        if hasattr(rails, "generate_async"):
            response = await rails.generate_async(messages=[{"role": "user", "content": text}])
        else:
            response = await asyncio.to_thread(rails.generate, messages=[{"role": "user", "content": text}])
        content = response.get("content", str(response)) if isinstance(response, dict) else str(response)
        content_norm = " ".join(content.strip().replace("\\u2014", "\u2014").split())
        for reason, canned in config.CANNED.items():
            if reason in ("output_sanitized", "pii"):
                continue
            if content_norm == " ".join(canned.strip().split()):
                blocked = reason in ("off_topic", "jailbreak", "sensitive")
                return GuardResult(not blocked, blocked, canned, reason, canned=True)
        return GuardResult(True, False, "", "allowed")
    except Exception as error:
        logger.warning("[guardrails] input check failed, fail-open: %s", error)
        return GuardResult(True, False, "", "nemo_error_fail_open")
