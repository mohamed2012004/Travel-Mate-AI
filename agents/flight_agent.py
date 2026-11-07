from agents.base_agent import AgentState, BaseAgent
from enums import AgentName, StateKey
from prompt_catalog import FLIGHT_AGENT_PROMPT, flight_user_prompt


class FlightAgent(BaseAgent):
    """Researches flights with Tavily web search, using the client's question."""

    name = AgentName.FLIGHT
    mcp_server = "tavily"
    mcp_tool_names = ("tavily_search",)

    @property
    def system_prompt(self) -> str:
        return FLIGHT_AGENT_PROMPT

    def build_prompt(self, state: AgentState) -> str:
        return flight_user_prompt(str(state[StateKey.USER_QUERY]))
