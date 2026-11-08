from langgraph.graph import END, START, StateGraph

from enums import AgentName
from nodes import Nodes
from state import TravelState


def build_graph(nodes: Nodes) -> StateGraph:
    """Wire the intent router, research agents and summary into one graph."""

    graph = StateGraph(TravelState)

    graph.add_node(AgentName.ROUTER, nodes.route_intent)
    graph.add_node(AgentName.FLIGHT, nodes.flight_agent)
    graph.add_node(AgentName.HOTEL, nodes.hotel_agent)
    graph.add_node(AgentName.WEATHER, nodes.weather_agent)
    graph.add_node(AgentName.ITINERARY, nodes.itinerary_agent)
    graph.add_node(AgentName.FINAL, nodes.final_agent)
    graph.add_node(AgentName.INPUT_GUARD, nodes.input_guard)
    graph.add_node(AgentName.OUTPUT_GUARD, nodes.output_guard)

    graph.add_edge(START, AgentName.INPUT_GUARD)
    graph.add_conditional_edges(
        AgentName.INPUT_GUARD,
        nodes.after_input_guard,
        [AgentName.ROUTER, AgentName.OUTPUT_GUARD],
    )
    graph.add_conditional_edges(
        AgentName.ROUTER,
        nodes.route_from_router,
        [
            AgentName.FLIGHT,
            AgentName.HOTEL,
            AgentName.WEATHER,
            AgentName.ITINERARY,
            AgentName.FINAL,
        ],
    )
    for research_node in (AgentName.FLIGHT, AgentName.HOTEL, AgentName.WEATHER):
        graph.add_conditional_edges(
            research_node,
            nodes.after_research,
            [AgentName.ITINERARY, AgentName.FINAL],
        )
    graph.add_edge(AgentName.ITINERARY, AgentName.FINAL)
    graph.add_edge(AgentName.FINAL, AgentName.OUTPUT_GUARD)
    graph.add_edge(AgentName.OUTPUT_GUARD, END)

    return graph
