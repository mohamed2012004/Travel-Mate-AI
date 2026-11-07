from agents.base_agent import AgentState, BaseAgent
from enums import AgentName, StateKey
from prompt_catalog import HOTEL_AGENT_PROMPT, hotel_user_prompt


class HotelAgent(BaseAgent):
    """Researches hotels with the Tavily MCP search tools."""

    name = AgentName.HOTEL
    mcp_server = "tavily"
    mcp_tool_names = ("tavily_search",)

    @property
    def system_prompt(self) -> str:
        return HOTEL_AGENT_PROMPT

    def build_prompt(self, state: AgentState) -> str:
        return hotel_user_prompt(str(state[StateKey.USER_QUERY]))
