from collections.abc import Mapping
from typing import Any

from langchain_core.messages import AnyMessage
from pydantic import BaseModel, Field

from enums import AgentName, Intent, StateKey

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


def message_text(message: AnyMessage) -> str:
    """Flatten a message's content into plain text."""

    content = getattr(message, "content", message)

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(part for part in parts if part)

    return str(content)


def normalize_route_decision(decision: RouteDecision) -> RouteDecision:
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


def agent_section(
    state: Mapping[str, Any],
    key: StateKey,
    agent: AgentName,
    selected: list[str],
) -> str:
    if str(agent) not in selected:
        return "(not requested)"

    return str(state.get(key, "")) or "(no results)"


__all__ = [
    "AGENTS_BY_INTENT",
    "FULL_TRIP_AGENTS",
    "RESEARCH_AGENTS",
    "RouteDecision",
    "agent_section",
    "message_text",
    "normalize_route_decision",
]
