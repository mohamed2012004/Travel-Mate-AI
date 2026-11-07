from agents.base_agent import AgentState, BaseAgent
from enums import AgentName, StateKey
from prompt_catalog import ITINERARY_AGENT_PROMPT, itinerary_user_prompt


class ItineraryAgent(BaseAgent):
    """Turns the other agents' research into a day-by-day plan. No tools."""

    name = AgentName.ITINERARY

    @property
    def system_prompt(self) -> str:
        return ITINERARY_AGENT_PROMPT

    def build_prompt(self, state: AgentState) -> str:
        return itinerary_user_prompt(
            str(state[StateKey.USER_QUERY]),
            str(state[StateKey.FLIGHT_RESULTS]),
            str(state[StateKey.HOTEL_RESULTS]),
            str(state[StateKey.WEATHER_RESULTS]),
        )
