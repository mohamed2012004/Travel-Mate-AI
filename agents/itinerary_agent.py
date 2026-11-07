from agents.base_agent import AgentState, BaseAgent
from enums import AgentName, StateKey

ITINERARY_AGENT_PROMPT = """
You are the itinerary planning agent of a multi-agent travel planner.

Create a practical, budget-aware, day-by-day travel itinerary using the
flight, hotel and weather research provided.

Keep it realistic: respect travel time, cluster nearby activities and
adapt outdoor plans to the forecast.
"""


class ItineraryAgent(BaseAgent):
    """Turns the other agents' research into a day-by-day plan. No tools."""

    name = AgentName.ITINERARY

    @property
    def system_prompt(self) -> str:
        return ITINERARY_AGENT_PROMPT

    def build_prompt(self, state: AgentState) -> str:
        return f"""
User Query:
{state[StateKey.USER_QUERY]}

Flight Results:
{state[StateKey.FLIGHT_RESULTS]}

Hotel Results:
{state[StateKey.HOTEL_RESULTS]}

Weather Results:
{state[StateKey.WEATHER_RESULTS]}
"""
