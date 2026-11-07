import logging

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from enums import AgentName, Intent

logger = logging.getLogger(__name__)

RESEARCH_AGENTS = (AgentName.FLIGHT, AgentName.HOTEL, AgentName.WEATHER)
FULL_TRIP_AGENTS = (
    AgentName.FLIGHT,
    AgentName.HOTEL,
    AgentName.WEATHER,
    AgentName.ITINERARY,
)

AGENTS_BY_INTENT: dict[Intent, list[AgentName]] = {
    Intent.FULL_TRIP: list(FULL_TRIP_AGENTS),
    Intent.FLIGHTS: [AgentName.FLIGHT],
    Intent.HOTELS: [AgentName.HOTEL],
    Intent.WEATHER: [AgentName.WEATHER],
    Intent.ITINERARY: [AgentName.ITINERARY],
    Intent.FLIGHTS_AND_HOTELS: [AgentName.FLIGHT, AgentName.HOTEL],
    Intent.GENERAL: [],
}


class RouteDecision(BaseModel):
    """The traveller's intent and the agents that request needs."""

    intent: Intent = Field(description="The traveller's intent")
    agents: list[AgentName] = Field(
        description=(
            "Agents that must run for this request, in any order. "
            "Never include final_agent."
        )
    )


ROUTER_PROMPT = """You are the intent router of a multi-agent travel planner.

Given the user's request, decide the intent and which agents must run.

Agents:
- flight_agent: flights, airports, airlines, routes
- hotel_agent: hotels, accommodation, places to stay
- weather_agent: weather, forecast, packing advice
- itinerary_agent: a day-by-day plan built from the other agents' research
- final_agent: always runs last to write the answer, never include it

Intents:
- full_trip: the user wants a complete trip plan -> all four agents
- flights, hotels, weather, itinerary, flights_and_hotels: the user asked only for those topics
- general: greetings or requests with no travel task -> no agents

Rules:
- Only include agents the user's request actually needs.
- If the user asks to plan a trip or wants a complete itinerary covering
  flights, hotels and weather, use full_trip with all four agents.
- If the user asks only about hotels, use hotels with [hotel_agent].
- If the user asks about hotels and flights, use flights_and_hotels with
  [flight_agent, hotel_agent].
- If the request is a greeting or not about travel, use general with [].
- The itinerary_agent needs research: include flight_agent, hotel_agent and
  weather_agent too whenever the itinerary should cover them.

User request:
{user_query}"""


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

        return _normalize(decision)


def _normalize(decision: RouteDecision) -> RouteDecision:
    """Keep the agent list consistent with the chosen intent."""

    intent = decision.intent

    if intent == Intent.FULL_TRIP:
        return RouteDecision(intent=intent, agents=list(FULL_TRIP_AGENTS))

    if intent == Intent.GENERAL:
        return RouteDecision(intent=intent, agents=[])

    agents: list[AgentName] = []
    for agent in decision.agents:
        if agent == AgentName.FINAL or agent in agents:
            continue
        agents.append(agent)

    if not agents:
        agents = list(AGENTS_BY_INTENT.get(intent, []))

    return RouteDecision(intent=intent, agents=agents)


__all__ = [
    "AGENTS_BY_INTENT",
    "FULL_TRIP_AGENTS",
    "IntentRouter",
    "RESEARCH_AGENTS",
    "RouteDecision",
]
