from agents.base_agent import AgentState, BaseAgent
from enums import AgentName, StateKey
from prompt_catalog import WEATHER_AGENT_PROMPT


class WeatherAgent(BaseAgent):
    """Looks up current weather and forecast with the custom weather MCP server."""

    name = AgentName.WEATHER
    mcp_server = "weather"

    @property
    def system_prompt(self) -> str:
        return WEATHER_AGENT_PROMPT

    def build_prompt(self, state: AgentState) -> str:
        return state[StateKey.USER_QUERY]
