import operator
from typing import Annotated, Any, NotRequired, TypedDict

from langchain_core.messages import AnyMessage


def _latest_version(old: int | None, new: int | None) -> int:
    """Reducer for `version`: keep the highest version seen.

    Plain `int` uses LangGraph's LastValue channel, which rejects a
    second write to the same key in one superstep. The research
    agents run in parallel and each advances the shared-memory
    version, so their writes must be folded with max() instead.
    """
    return max(old or 0, new or 0)


def _merge_shared_memory(
    old: dict[str, Any] | None, new: dict[str, Any] | None
) -> dict[str, Any]:
    """Reducer for `shared_memory`: merge dicts instead of replacing.

    Parallel research nodes write only the field they own
    (e.g. {"flight": ...}), so merging is order-independent and
    no agent's result is lost. A full snapshot (router/final
    node, the only writer in its step) also merges cleanly, and
    its embedded version is kept at the highest seen.
    """
    merged: dict[str, Any] = {**(old or {}), **(new or {})}
    if "version" in (old or {}) or "version" in (new or {}):
        merged["version"] = max(
            int((old or {}).get("version") or 0),
            int((new or {}).get("version") or 0),
        )
    return merged


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
    version: Annotated[int, _latest_version]
    shared_memory: Annotated[dict[str, Any], _merge_shared_memory]
    guard_checked: NotRequired[bool]
    guard_blocked: NotRequired[bool]
    guard_reason: NotRequired[str]
