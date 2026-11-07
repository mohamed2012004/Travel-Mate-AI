from agents.base_agent import AgentState, BaseAgent
from agents.utils_agents import agent_section
from enums import SECTION_LABELS, AgentName, Intent, StateKey
from prompt_catalog import FINAL_AGENT_PROMPT, final_user_prompt


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

        return final_user_prompt(
            str(state[StateKey.USER_QUERY]),
            str(intent),
            requested,
            agent_section(state, StateKey.FLIGHT_RESULTS, AgentName.FLIGHT, selected),
            agent_section(state, StateKey.HOTEL_RESULTS, AgentName.HOTEL, selected),
            agent_section(state, StateKey.WEATHER_RESULTS, AgentName.WEATHER, selected),
            agent_section(state, StateKey.ITINERARY, AgentName.ITINERARY, selected),
        )
