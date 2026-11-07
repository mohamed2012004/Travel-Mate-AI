from agents.base_agent import AgentState, BaseAgent
from enums import AgentName, Intent, StateKey

FINAL_AGENT_PROMPT = """
You are a professional AI travel booking assistant writing the final
answer for the traveller.

The workflow researched only the topics the user asked about. Write a
summary that matches that intent:

- Start with a short Trip Summary.
- Add a section only for topics that have research: Flight Information,
  Hotel Suggestions, Weather Information, Day-by-Day Itinerary.
- Omit sections marked "not requested" or with no results entirely -
  never invent research and never pad the answer with unrelated topics.
- If the user asked about a single topic (for example only hotels), give
  a focused, practical answer about that topic alone.
- Add Estimated Budget and Final Recommendations only when enough
  research exists to support them.
- If intent is general and no research was requested, reply
  conversationally: ask for destination, dates, travellers and budget,
  and briefly say what you can plan.

Be clear and practical. Mention that the live flight API may not provide
ticket prices when pricing is unavailable. Include weather-based advice
whenever weather research is present.
"""

SECTION_LABELS = {
    AgentName.FLIGHT: "flights",
    AgentName.HOTEL: "hotels",
    AgentName.WEATHER: "weather",
    AgentName.ITINERARY: "itinerary",
}


class FinalAgent(BaseAgent):
    """Formats the completed trip plan into the final user-facing answer. No tools."""

    name = AgentName.FINAL

    @property
    def system_prompt(self) -> str:
        return FINAL_AGENT_PROMPT

    def build_prompt(self, state: AgentState) -> str:
        intent = state.get(StateKey.INTENT, "") or Intent.GENERAL
        selected = state.get(StateKey.SELECTED_AGENTS) or []

        requested = ", ".join(
            label
            for agent, label in SECTION_LABELS.items()
            if str(agent) in selected
        ) or "none (general request)"

        return f"""
User Request:
{state[StateKey.USER_QUERY]}

Intent: {intent}
Requested topics: {requested}

Flights:
{self._section(state, StateKey.FLIGHT_RESULTS, AgentName.FLIGHT, selected)}

Hotels:
{self._section(state, StateKey.HOTEL_RESULTS, AgentName.HOTEL, selected)}

Weather:
{self._section(state, StateKey.WEATHER_RESULTS, AgentName.WEATHER, selected)}

Itinerary:
{self._section(state, StateKey.ITINERARY, AgentName.ITINERARY, selected)}
"""

    @staticmethod
    def _section(
        state: AgentState, key: StateKey, agent: AgentName, selected: list[str]
    ) -> str:
        if str(agent) not in selected:
            return "(not requested)"

        return str(state.get(key, "")) or "(no results)"
