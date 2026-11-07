from collections.abc import Sequence

from langchain_core.tools import BaseTool

from agents.base_agent import AgentState, BaseAgent
from enums import AgentName, StateKey
from mcp_client import get_tavily_tools

HOTEL_AGENT_PROMPT = """
You are the hotel research agent of a multi-agent travel planner.

Use the web search tool to find real hotels that match the user's trip,
then summarise the best options.

For every shortlisted hotel include:

1. Hotel name and area / neighbourhood
2. Why it suits this trip
3. Approximate nightly price range
4. One useful practical note (breakfast, airport transfer, location, ...)

Prefer hotels that are actually mentioned in the search results.
Never invent hotel names.
"""


class HotelAgent(BaseAgent):
    """Researches hotels with the Tavily MCP search tools."""

    name = AgentName.HOTEL

    @property
    def system_prompt(self) -> str:
        return HOTEL_AGENT_PROMPT

    async def load_tools(self) -> Sequence[BaseTool]:
        return await get_tavily_tools()

    def build_prompt(self, state: AgentState) -> str:
        return f"Best hotels for this trip: {state[StateKey.USER_QUERY]}"
