from collections.abc import Sequence

from langchain_core.tools import BaseTool

from agents.base_agent import AgentState, BaseAgent
from enums import AgentName, StateKey
from mcp_client import get_weather_tools

WEATHER_AGENT_PROMPT = """
You are the weather agent of a multi-agent travel planner.

1. Identify the trip destination from the user's request.
2. Call the current weather tool for that city.
3. Call the forecast tool for that city.
4. Summarise the weather in celsius with what it means for the traveller.

Include packing advice and any weather-related risk for the trip.
"""


class WeatherAgent(BaseAgent):
    """Looks up current weather and forecast with the custom weather MCP server."""

    name = AgentName.WEATHER

    @property
    def system_prompt(self) -> str:
        return WEATHER_AGENT_PROMPT

    async def load_tools(self) -> Sequence[BaseTool]:
        return await get_weather_tools()

    def build_prompt(self, state: AgentState) -> str:
        return state[StateKey.USER_QUERY]
