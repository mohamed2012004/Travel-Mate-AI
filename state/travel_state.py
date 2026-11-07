import operator
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage


class TravelState(TypedDict):
    """Shared workflow state every agent reads and writes."""

    messages: Annotated[list[AnyMessage], operator.add]
    run_id: str
    thread_id: str
    user_query: str
    intent: str
    selected_agents: list[str]
    flight_results: str
    hotel_results: str
    weather_results: str
    itinerary: str
    llm_calls: Annotated[int, operator.add]
