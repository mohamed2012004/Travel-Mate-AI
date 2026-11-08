import asyncio
import logging
from dataclasses import dataclass

from . import config
from .rails import get_guard_llm, get_rails, guard_enabled

logger = logging.getLogger(__name__)

BLOCKING_CANNED = {"off_topic", "jailbreak", "sensitive", "capabilities", "farewell"}

GREETING_REPLY = "Hi, I am travel planner. I can plan flights, hotels, weather and itineraries. Where do you want to go?"

async def _is_greeting(text: str) -> bool:
    llm = get_guard_llm()
    prompt = (
        "You are a greeting detector for a travel planner. "
        "Is the user message ONLY a greeting (for example hello, hi, hey, salam, good morning) "
        "with NO travel request at all? Answer with exactly one word: YES or NO.\n\n"
        f"User message: {text}"
    )
    response = await llm.ainvoke(prompt)
    content = getattr(response, "content", response)
    return str(content).strip().upper().startswith("YES")

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
    try:
        if await _is_greeting(text):
            return GuardResult(False, True, GREETING_REPLY, "greeting", canned=True)
    except Exception as error:
        logger.warning("[guardrails] greeting LLM check failed, fail-open to NeMo rails: %s", error)
    rails = get_rails()
    if rails is None:
        return GuardResult(True, False, "", "nemo_unavailable_fail_open")
    try:
        systematic = await rails.check_async([{"role": "user", "content": text}])
        if str(systematic.status) == "RailStatus.BLOCKED" or getattr(systematic.status, "value", "") == "blocked":
            rail_name = str(getattr(systematic, "rail", "") or "")
            if rail_name in config.CANNED:
                blocked = rail_name in BLOCKING_CANNED
                return GuardResult(not blocked, blocked, systematic.content or config.CANNED[rail_name], rail_name, canned=True)
            else:
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
                blocked = reason in BLOCKING_CANNED
                return GuardResult(not blocked, blocked, canned, reason, canned=True)
        return GuardResult(True, False, "", "allowed")
    except Exception as error:
        logger.warning("[guardrails] input check failed, fail-open: %s", error)
        return GuardResult(True, False, "", "nemo_error_fail_open")
