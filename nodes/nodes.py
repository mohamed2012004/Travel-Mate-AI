import logging
import threading
from typing import Any

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
from agents.utils_agents import RESEARCH_AGENTS
from utils.background_tasks import schedule
from database import BaseDatabase
from enums import AgentName, StateKey
from state import SharedMemory

logger = logging.getLogger(__name__)

_FIELD_TO_AGENT = {
    "flight": AgentName.FLIGHT,
    "hotel": AgentName.HOTEL,
    "weather": AgentName.WEATHER,
}


class Nodes:
    """Every LangGraph node and routing decision of the travel workflow.

    Holds the agents and the intent router, and exposes the functions the
    graph is wired to: research nodes run in parallel and each one decides
    whether the itinerary or the final summary comes next.
    """

    def __init__(self, llm: BaseChatModel, database: BaseDatabase | None = None):
        self.database = database
        self.intent_router = IntentRouter(llm)
        self.flight = FlightAgent(llm, database)
        self.hotel = HotelAgent(llm, database)
        self.weather = WeatherAgent(llm, database)
        self.itinerary = ItineraryAgent(llm, database)
        self.final = FinalAgent(llm, database)
        self._shared_memories: dict[str, SharedMemory] = {}
        self._shared_lock = threading.Lock()

    def _shared_memory(self, state: AgentState, reset: bool = False) -> SharedMemory:
        run_id = str(state.get(StateKey.RUN_ID, "default"))
        with self._shared_lock:
            if reset or run_id not in self._shared_memories:
                self._shared_memories[run_id] = SharedMemory()
            return self._shared_memories[run_id]

    async def _commit(
        self, state: AgentState, field: str, value: str
    ) -> dict[str, Any]:
        """Commit one result with optimistic locking and automatic retry.

        The agent read shared memory at `state[version]`; if a parallel
        agent already advanced it, update() rejects the stale write,
        then update_with_retry() re-reads the latest memory, merges
        this result into it, and retries with the latest version.

        The resulting snapshot is also persisted to `version_states`,
        linked by run_id and by the committing agent's
        `agent_states.id` (best-effort: a DB failure must not fail
        the travel run, mirroring BaseAgent's persistence guards).
        """

        memory = self._shared_memory(state)
        base_version = int(state.get(StateKey.VERSION, 1) or 1)
        snapshot = memory.update_with_retry(
            {field: value}, expected_version=base_version
        )
        # Report path uses in-memory SharedMemory snapshot only.
        # DB version_states write is background / best-effort.
        run_id = str(state.get(StateKey.RUN_ID, ""))
        agent_name = _FIELD_TO_AGENT.get(field)
        if agent_name:
            logger.info("[shared-memory] committed %s -> version=%s (in-memory, DB persist queued)", field, snapshot["version"])
            schedule(
                f"{run_id}:{agent_name}",
                lambda: self._persist_version(state, field, dict(snapshot)),
            )
        return snapshot

    async def _persist_version(
        self, state: AgentState, field: str, snapshot: dict[str, Any]
    ) -> None:
        database = getattr(self, "database", None)
        if database is None or not getattr(database, "connected", False):
            return

        agent_name = _FIELD_TO_AGENT.get(field)
        run_id = str(state.get(StateKey.RUN_ID, ""))
        if not agent_name or not run_id:
            return

        try:
            record = await database.get_agent_state(run_id, str(agent_name))
            if record is None or record.id is None:
                return
            await database.save_version_state(
                run_id=run_id,
                agent_state_id=record.id,
                version=int(snapshot["version"]),
                shared_memory=snapshot,
            )
        except Exception as error:
            logger.warning(
                "[version_states] could not persist version %s for run %s: %s",
                snapshot.get("version"),
                run_id,
                error,
            )

    async def _research(
        self, agent: BaseAgent, state: AgentState, label: str, field: str
    ) -> tuple[str, int, dict[str, Any]]:
        """Run a research agent, then commit its result to shared memory."""

        try:
            result, llm_calls = await agent.run(state)
        except Exception as error:
            result, llm_calls = f"{label} unavailable: {error}", 0

        snapshot = await self._commit(state, field, result)
        return result, llm_calls, snapshot

    async def input_guard(self, state: AgentState) -> dict:
        if state.get("guard_checked"):
            return {"guard_checked": True}
        try:
            from guardrails import check_input
            result = await check_input(str(state.get(StateKey.USER_QUERY, "")))
        except Exception as error:
            logger.warning("[guardrails] input_guard failed, fail-open: %s", error)
            return {"guard_checked": True, "guard_blocked": False, "guard_reason": "fail_open"}
        if result.blocked or result.canned:
            return {
                "guard_checked": True,
                "guard_blocked": result.blocked,
                "guard_reason": result.reason,
                StateKey.MESSAGES: [AIMessage(content=result.message)],
            }
        return {"guard_checked": True, "guard_blocked": False, "guard_reason": ""}

    def after_input_guard(self, state: AgentState) -> str:
        return str(AgentName.OUTPUT_GUARD) if state.get("guard_blocked") else str(AgentName.ROUTER)

    async def output_guard(self, state: AgentState) -> dict:
        messages = state.get(StateKey.MESSAGES) or []
        if not messages:
            return {}
        from agents import message_text as _message_text
        last_text = _message_text(messages[-1])
        try:
            from guardrails import check_output
            result = await check_output(last_text)
        except Exception as error:
            logger.warning("[guardrails] output_guard failed, fail-open: %s", error)
            return {}
        if result.blocked:
            return {
                "guard_blocked": True,
                "guard_reason": result.reason,
                StateKey.MESSAGES: [AIMessage(content=result.message)],
            }
        return {"guard_blocked": bool(state.get("guard_blocked", False)), "guard_reason": str(state.get("guard_reason", "") or "")}

    async def route_intent(self, state: AgentState) -> dict:
        """Classify the request so only the needed agents run."""

        decision = await self.intent_router.decide(
            str(state.get(StateKey.USER_QUERY, ""))
        )
        selected = [str(agent) for agent in decision.agents]
        structured = decision.to_dict()
        logger.info("[router] structured intent=%s", structured)
        snapshot = self._shared_memory(state, reset=True).snapshot()

        return {
            StateKey.INTENT: str(decision.intent),
            StateKey.SELECTED_AGENTS: selected,
            StateKey.VERSION: snapshot["version"],
            StateKey.SHARED_MEMORY: snapshot,
            StateKey.MESSAGES: [
                AIMessage(
                    content=str(structured)
                )
            ],
            StateKey.LLM_CALLS: 1,
        }

    def route_from_router(self, state: AgentState) -> list[str]:
        """Fan out to the selected agents; research runs in parallel."""

        selected = state.get(StateKey.SELECTED_AGENTS) or []
        research = [a for a in selected if a in RESEARCH_AGENTS]
        logger.info("[workflow] fan-out (parallel) -> %s", research or selected)

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
        flight_results, llm_calls, snapshot = await self._research(
            self.flight, state, "Flight information", "flight"
        )

        return {
            StateKey.FLIGHT_RESULTS: flight_results,
            StateKey.VERSION: snapshot["version"],
            # Partial update only: parallel nodes writing a full
            # snapshot would overwrite each other's fields when
            # LangGraph folds the writes in arbitrary order. The
            # authoritative copy is the SharedMemory object.
            StateKey.SHARED_MEMORY: {"flight": flight_results},
            StateKey.MESSAGES: [
                AIMessage(content="Flight agent finished research.")
            ],
            StateKey.LLM_CALLS: llm_calls,
        }

    async def hotel_agent(self, state: AgentState) -> dict:
        hotel_results, llm_calls, snapshot = await self._research(
            self.hotel, state, "Hotel information", "hotel"
        )

        return {
            StateKey.HOTEL_RESULTS: hotel_results,
            StateKey.VERSION: snapshot["version"],
            StateKey.SHARED_MEMORY: {"hotel": hotel_results},
            StateKey.MESSAGES: [
                AIMessage(content="Hotel agent finished research.")
            ],
            StateKey.LLM_CALLS: llm_calls,
        }

    async def weather_agent(self, state: AgentState) -> dict:
        weather_results, llm_calls, snapshot = await self._research(
            self.weather, state, "Weather information", "weather"
        )

        return {
            StateKey.WEATHER_RESULTS: weather_results,
            StateKey.VERSION: snapshot["version"],
            StateKey.SHARED_MEMORY: {"weather": weather_results},
            StateKey.MESSAGES: [
                AIMessage(content="Weather agent finished research.")
            ],
            StateKey.LLM_CALLS: llm_calls,
        }

    async def itinerary_agent(self, state: AgentState) -> dict:
        try:
            itinerary_text, llm_calls = await self.itinerary.run(state)
        except Exception as error:
            itinerary_text, llm_calls = f"Itinerary unavailable: {error}", 0

        return {
            StateKey.ITINERARY: itinerary_text,
            StateKey.MESSAGES: [
                AIMessage(content=itinerary_text)
            ],
            StateKey.LLM_CALLS: llm_calls,
        }

    async def final_agent(self, state: AgentState) -> dict:
        try:
            final_answer, llm_calls = await self.final.run(state)
        except Exception as error:
            sections = [
                str(state.get(key, "") or "")
                for key in (
                    StateKey.FLIGHT_RESULTS,
                    StateKey.HOTEL_RESULTS,
                    StateKey.WEATHER_RESULTS,
                    StateKey.ITINERARY,
                )
            ]
            final_answer = (
                f"Summary unavailable: {error}\n\n"
                + "\n\n".join(section for section in sections if section)
            )
            llm_calls = 0

        # Sole writer in this step, so the full authoritative
        # snapshot (all research fields + final version) can be
        # written back without a concurrent-update conflict.
        snapshot = self._shared_memory(state).snapshot()

        return {
            StateKey.VERSION: snapshot["version"],
            StateKey.SHARED_MEMORY: snapshot,
            StateKey.MESSAGES: [
                AIMessage(content=final_answer)
            ],
            StateKey.LLM_CALLS: llm_calls,
        }
