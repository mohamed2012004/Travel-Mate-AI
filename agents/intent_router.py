import logging

from langchain_core.language_models import BaseChatModel

from agents.utils_agents import (
    AGENTS_BY_INTENT,
    FULL_TRIP_AGENTS,
    RESEARCH_AGENTS,
    RouteDecision,
    normalize_route_decision,
)
from enums import Intent
from prompt_catalog import ROUTER_PROMPT

logger = logging.getLogger(__name__)


class IntentRouter:
    """Classifies one user request into an intent and a set of agents."""

    def __init__(self, model: BaseChatModel):
        self._structured = model.with_structured_output(RouteDecision)

    async def decide(self, user_query: str) -> RouteDecision:
        try:
            decision = await self._structured.ainvoke(
                ROUTER_PROMPT.format(user_query=user_query)
            )
        except Exception as error:
            logger.warning(
                "intent routing failed, defaulting to full trip: %s", error
            )
            return RouteDecision(
                intent=Intent.FULL_TRIP, agents=list(FULL_TRIP_AGENTS)
            )

        return normalize_route_decision(decision)


__all__ = [
    "AGENTS_BY_INTENT",
    "FULL_TRIP_AGENTS",
    "RESEARCH_AGENTS",
    "IntentRouter",
    "RouteDecision",
]
