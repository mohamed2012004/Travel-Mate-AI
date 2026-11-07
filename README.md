# ✈️ TripMate AI — A Multi-Agent Travel Planner with MCP

An open-source AI travel planner that turns a natural-language trip request into a practical travel plan with flight suggestions, hotel ideas, weather details, and a day-by-day itinerary. The project uses a multi-agent workflow built with LangGraph, LangChain, FastAPI, and MCP tooling.

## Why this project?

Planning a trip usually means jumping between multiple websites, tools, and spreadsheets. This project brings that flow into one experience by combining:

- a flight-search agent,
- a hotel-research agent,
- a weather agent,
- an itinerary-planning agent, and
- a final response agent,

all coordinated through a LangGraph workflow with MCP-based tool integrations.

## Features

- ✈️ Flight research using AviationStack
- 🏨 Hotel suggestions using Tavily search
- 🌤 Weather lookup via a custom MCP tool
- 🧠 Multi-agent orchestration with LangGraph and MCP
- 📝 Structured travel itinerary generation
- 🌐 FastAPI backend with a simple web interface
- 💾 Conversation state persistence using PostgreSQL
- ⚡ LLM-powered responses with Groq

## Tech Stack

- Python 3.10+
- FastAPI
- Jinja2 + HTML/CSS/JavaScript frontend
- LangGraph
- LangChain
- Groq LLMs
- PostgreSQL
- Tavily API
- AviationStack API
- MCP via `langchain-mcp-adapters` and `mcp`

## State and MCP Integration

This project integrates MCP in several places:

- `Tavily` search uses a remote MCP endpoint at `https://mcp.tavily.com/mcp/`
- `AviationStack` uses a local stdio MCP command: `uvx aviationstack-mcp`
- `Weather` is implemented with a custom local MCP server in `custom_weather_mcp_server.py`

The MCP client is defined in `mcp_client.py`, which exposes one async tool getter per MCP server:

- `get_aviation_tools()` — AviationStack airport, airline, route and flight tools
- `get_tavily_tools()` — Tavily web search tools
- `get_weather_tools()` — the custom weather MCP server tools
- `get_all_tools()` — every tool across all servers (handy for debugging)

Every graph node in `backend.py` is its own LangChain agent, built with `create_agent`, and each agent only receives the MCP tools of the API it is responsible for. No agent calls an HTTP API directly.

Each agent lives in its own class under `agents/` and implements the `BaseAgent` interface:

- `FlightAgent`, `HotelAgent`, `WeatherAgent` — declare `load_tools()` to receive their MCP server's tools
- `ItineraryAgent`, `FinalAgent` — planning and writing agents with no tools

A concrete agent only supplies its role prompt, its tools and how the shared state becomes its input; `BaseAgent` handles running the agent, counting its LLM calls, and saving the result.

Before any agent runs, an intent router (`agents/intent_router.py`) classifies the user's request with a structured LLM call and picks only the agents that request needs: hotels-only queries go straight to `HotelAgent`, hotels + flights run those two in parallel, and a full trip request fans out to flight, hotel and weather research in parallel before the itinerary and final summary. The final agent receives the detected intent and writes a summary that covers only the requested topics.

## Database and Recovery

Persistence sits behind an interface in `database/base_database.py` (`BaseDatabase`), with the PostgreSQL implementation in `database/postgres_database.py` (`PostgresDatabase`). Agents only depend on the interface, so another backend can be added without touching them.

Every agent writes its own state to the `agent_states` table:

1. `start_agent` — marks the agent `running` before it works (increments `attempts`)
2. `finish_agent` — stores the answer and marks it `completed`
3. `fail_agent` — stores the error and marks it `failed`

Each run gets a `run_id`, and agent results are keyed by `(run_id, agent_name)`. To recover a crashed run, call the API again with the same `run_id`: agents that already completed replay their saved answer from the database instead of calling the LLM and tools again, and only the remaining agents run. `/api/travel` returns the `run_id` it used for exactly this purpose.

On startup the app connects to PostgreSQL, creates the table if needed and prints any agent runs that started but never finished (`startup_database()` in `backend.py`). The same information is exposed by `GET /health`. If PostgreSQL is unreachable, the app still starts, logs the problem and runs with in-memory conversation checkpoints.

## Project Structure

```text
.
├── app.py                       # FastAPI app entry point
├── backend.py                   # LangGraph travel workflow
├── graph/
│   └── travel_graph.py          # Graph wiring (build_graph)
├── state/
│   └── travel_state.py          # TravelState schema
├── nodes/
│   └── nodes.py                 # Nodes class (graph node functions)
├── enums/
│   └── enums.py                 # Shared enums (agents, intent, state keys)
├── mcp_client.py                # MCP client and per-server tool getters
├── custom_weather_mcp_server.py # Local weather MCP server
├── database/
│   ├── base_database.py         # BaseDatabase interface
│   └── postgres_database.py     # PostgreSQL implementation
├── agents/
│   ├── base_agent.py            # BaseAgent interface
│   ├── intent_router.py         # IntentRouter (structured routing)
│   ├── flight_agent.py          # FlightAgent
│   ├── hotel_agent.py           # HotelAgent
│   ├── weather_agent.py         # WeatherAgent
│   ├── itinerary_agent.py       # ItineraryAgent
│   └── final_agent.py           # FinalAgent
├── requirements.txt             # Python dependencies
├── static/                      # Static frontend assets
└── templates/                   # HTML templates
```

## Prerequisites

Before running the project locally, make sure you have:

- Python 3.10 or newer installed
- PostgreSQL running and accessible
- API keys for:
  - Groq
  - Tavily
  - AviationStack
  - WeatherAPI (https://www.weatherapi.com/)
- `uvx` available for local `aviationstack-mcp` usage (or adjust `mcp_client.py` accordingly)

## Environment Variables

Create a `.env` file in the project root with the following variables:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/travel_db
GROQ_API_KEY=your_groq_api_key
AVIATIONSTACK_API_KEY=your_aviationstack_api_key
TAVILY_API_KEY=your_tavily_api_key
WEATHERAPI_API_KEY=your_weatherapi_api_key
DEFAULT_ORIGIN_IATA=DAC
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running the App

Start the FastAPI server:

```bash
python app.py
```

Then open your browser at:

```text
http://127.0.0.1:8000/
```

## Using MCP Tools

The app uses MCP behind the scenes, so there is no separate frontend change required after the environment is set up.

If you need to customize the weather MCP server command, edit `mcp_client.py` and update the `weather` tool path to your local Python environment.

## API Endpoints

- GET /health - Health check
- POST /api/travel - Submit a travel request

Example request:

```bash
curl -X POST http://127.0.0.1:8000/api/travel \
  -H "Content-Type: application/json" \
  -d '{"message":"Plan a 3-day trip to Tokyo with a budget of $1200"}'
```

## How the Workflow Works

1. The user submits a travel request.
2. The flight agent calls the AviationStack MCP tools (airports, airlines, routes, schedules).
3. The hotel agent calls the remote Tavily MCP search tools.
4. The weather agent calls the custom weather MCP server tools.
5. The itinerary agent creates a practical travel plan from the previous agents' research.
6. The final response agent formats the answer, which is returned through the web API.

## Contributing

Contributions are welcome. If you want to improve the app, add new travel features, or fix issues:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Open a pull request

## Acknowledgments

This project is built with the help of modern LLM tooling, MCP integrations, and travel APIs. It is intended as a practical example of combining LangGraph agents with real-world applications.
