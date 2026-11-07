from collections.abc import Sequence

from langchain_core.tools import BaseTool

from agents.base_agent import AgentState, BaseAgent
from enums import AgentName, StateKey
from mcp_client import get_aviation_tools

FLIGHT_AGENT_PROMPT = """
You are the flight research agent of a multi-agent travel planner.

Use the aviation tools you have access to in order to find real airport,
airline and flight data for the user's trip.

Report back with:

1. Likely departure airport (IATA code and city)
2. Likely arrival airport (IATA code and city)
3. Airlines serving this route
4. Typical flight duration
5. Estimated airfare range
6. Peak season pricing warning
7. Booking advice

Only state flight facts you actually retrieved from the tools.
If the API does not return ticket prices, say that live pricing is
unavailable and give a typical range as an estimate instead.
"""


class FlightAgent(BaseAgent):
    """Researches airports, airlines, routes and schedules via AviationStack MCP."""

    name = AgentName.FLIGHT

    @property
    def system_prompt(self) -> str:
        return FLIGHT_AGENT_PROMPT

    async def load_tools(self) -> Sequence[BaseTool]:
        return await get_aviation_tools()

    def build_prompt(self, state: AgentState) -> str:
        return state[StateKey.USER_QUERY]
