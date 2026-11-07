from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from agents import (
    BaseAgent,
    FinalAgent,
    FlightAgent,
    HotelAgent,
    IntentRouter,
    ItineraryAgent,
    WeatherAgent,
)
from agents.base_agent import AgentState
from agents.intent_router import RESEARCH_AGENTS
from database import BaseDatabase
from enums import AgentName, StateKey


class Nodes:
    """Every LangGraph node and routing decision of the travel workflow.

    Holds the agents and the intent router, and exposes the functions the
    graph is wired to: research nodes run in parallel and each one decides
    whether the itinerary or the final summary comes next.
    """

    def __init__(self, llm: BaseChatModel, database: BaseDatabase | None = None):
        self.intent_router = IntentRouter(llm)
        self.flight = FlightAgent(llm, database)
        self.hotel = HotelAgent(llm, database)
        self.weather = WeatherAgent(llm, database)
        self.itinerary = ItineraryAgent(llm, database)
        self.final = FinalAgent(llm, database)

    async def _research(
        self, agent: BaseAgent, state: AgentState, label: str
    ) -> tuple[str, int]:
        """Run a research agent, degrading gracefully when its tools fail."""

        try:
            return await agent.run(state)
        except Exception as error:
            return f"{label} unavailable: {error}", 0

    async def route_intent(self, state: AgentState) -> dict:
        """Classify the request so only the needed agents run."""

        decision = await self.intent_router.decide(
            str(state.get(StateKey.USER_QUERY, ""))
        )
        selected = [str(agent) for agent in decision.agents]

        return {
            StateKey.INTENT: str(decision.intent),
            StateKey.SELECTED_AGENTS: selected,
            StateKey.MESSAGES: [
                AIMessage(
                    content=f"Router: intent={decision.intent} agents={selected}"
                )
            ],
            StateKey.LLM_CALLS: 1,
        }

    def route_from_router(self, state: AgentState) -> list[str]:
        """Fan out to the selected agents; research runs in parallel."""

        selected = state.get(StateKey.SELECTED_AGENTS) or []
        research = [a for a in selected if a in RESEARCH_AGENTS]

        if research:
            return research

        if str(AgentName.ITINERARY) in selected:
            return [str(AgentName.ITINERARY)]

        return [str(AgentName.FINAL)]

    def after_research(self, state: AgentState) -> str:
        """Itinerary only when it was requested, otherwise straight to the summary."""

        selected = state.get(StateKey.SELECTED_AGENTS) or []

        if str(AgentName.ITINERARY) in selected:
            return str(AgentName.ITINERARY)

        return str(AgentName.FINAL)

    async def flight_agent(self, state: AgentState) -> dict:
        flight_results, llm_calls = await self._research(
            self.flight, state, "Flight information"
        )

        return {
            StateKey.FLIGHT_RESULTS: flight_results,
            StateKey.MESSAGES: [
                AIMessage(content="Flight agent finished research.")
            ],
            StateKey.LLM_CALLS: llm_calls,
        }

    async def hotel_agent(self, state: AgentState) -> dict:
        hotel_results, llm_calls = await self._research(
            self.hotel, state, "Hotel information"
        )

        return {
            StateKey.HOTEL_RESULTS: hotel_results,
            StateKey.MESSAGES: [
                AIMessage(content="Hotel agent finished research.")
            ],
            StateKey.LLM_CALLS: llm_calls,
        }

    async def weather_agent(self, state: AgentState) -> dict:
        weather_results, llm_calls = await self._research(
            self.weather, state, "Weather information"
        )

        return {
            StateKey.WEATHER_RESULTS: weather_results,
            StateKey.MESSAGES: [
                AIMessage(content="Weather agent finished research.")
            ],
            StateKey.LLM_CALLS: llm_calls,
        }

    async def itinerary_agent(self, state: AgentState) -> dict:
        itinerary_text, llm_calls = await self.itinerary.run(state)

        return {
            StateKey.ITINERARY: itinerary_text,
            StateKey.MESSAGES: [
                AIMessage(content=itinerary_text)
            ],
            StateKey.LLM_CALLS: llm_calls,
        }

    async def final_agent(self, state: AgentState) -> dict:
        final_answer, llm_calls = await self.final.run(state)

        return {
            StateKey.MESSAGES: [
                AIMessage(content=final_answer)
            ],
            StateKey.LLM_CALLS: llm_calls,
        }
