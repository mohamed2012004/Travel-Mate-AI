from enum import StrEnum


class AgentStatus(StrEnum):
    """Lifecycle states an agent record moves through in the database."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentName(StrEnum):
    """Stable names of the workflow agents, used as graph node keys."""

    ROUTER = "intent_router"
    FLIGHT = "flight_agent"
    HOTEL = "hotel_agent"
    WEATHER = "weather_agent"
    ITINERARY = "itinerary_agent"
    FINAL = "final_agent"
    INPUT_GUARD = "input_guard"
    OUTPUT_GUARD = "output_guard"


SECTION_LABELS: dict[AgentName, str] = {
    AgentName.FLIGHT: "flights",
    AgentName.HOTEL: "hotels",
    AgentName.WEATHER: "weather",
    AgentName.ITINERARY: "itinerary",
}


class Intent(StrEnum):
    """Coarse label for what the traveller is asking for."""

    FULL_TRIP = "full_trip"
    FLIGHTS = "flights"
    HOTELS = "hotels"
    WEATHER = "weather"
    ITINERARY = "itinerary"
    FLIGHTS_AND_HOTELS = "flights_and_hotels"
    GENERAL = "general"


class CheckpointerBackend(StrEnum):
    """Which conversation checkpointer the compiled graph is using."""

    UNSET = "unset"
    POSTGRES = "postgres"
    MEMORY = "memory"
    NONE = "none"


class StateKey(StrEnum):
    """Keys of the shared travel workflow state."""

    MESSAGES = "messages"
    RUN_ID = "run_id"
    THREAD_ID = "thread_id"
    USER_QUERY = "user_query"
    INTENT = "intent"
    SELECTED_AGENTS = "selected_agents"
    FLIGHT_RESULTS = "flight_results"
    HOTEL_RESULTS = "hotel_results"
    WEATHER_RESULTS = "weather_results"
    ITINERARY = "itinerary"
    LLM_CALLS = "llm_calls"
    VERSION = "version"
    SHARED_MEMORY = "shared_memory"


__all__ = [
    "AgentStatus",
    "AgentName",
    "CheckpointerBackend",
    "Intent",
    "SECTION_LABELS",
    "StateKey",
]
