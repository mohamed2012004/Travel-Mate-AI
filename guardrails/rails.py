import logging
import os
from dotenv import load_dotenv
load_dotenv()
from langchain_groq import ChatGroq
from nemoguardrails import LLMRails, RailsConfig

from . import config
from .actions import classify_input, detect_pii_in_input, sanitize_output

logger = logging.getLogger(__name__)

_rails = None
_rails_failed = False

def guard_enabled() -> bool:
    return os.getenv("GUARDRAILS_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")

def get_guard_llm():
    
    api_key = os.getenv("GROQ_GUARD_KEY") or os.getenv("GUARD_API_KEY") or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_GUARD_KEY/GUARD_API_KEY/GROQ_API_KEY is missing")
    model = os.getenv("GUARD_MODEL") or os.getenv("GROQ_GUARD_MODEL") or "qwen/qwen3.8-27b"
    return ChatGroq(api_key=api_key, model=model, temperature=0)

def get_rails():
    global _rails, _rails_failed
    if _rails is not None:
        return _rails
    if _rails_failed:
        return None
    try:
        
        rails_config = RailsConfig.from_content(colang_content=config.COLANG, yaml_content=config.YAML)
        rails = LLMRails(rails_config, llm=get_guard_llm())
        rails.register_action(detect_pii_in_input)
        rails.register_action(sanitize_output)
        rails.register_action(classify_input)
        _rails = rails
        return rails
    except Exception as error:
        _rails_failed = True
        logger.warning("[guardrails] NeMo unavailable, fail-open to regex checks: %s", error)
        return None
