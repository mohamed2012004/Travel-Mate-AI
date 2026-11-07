# ✈️ TravelMate AI — A Multi-Agent Travel Planner with MCP

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

- ✈️ Flight research using Tavily search
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
- WeatherAPI
- MCP via `langchain-mcp-adapters` and `mcp`

## System Design

Source design: [`excalidraw_files/design.excalidraw`](excalidraw_files/design.excalidraw) — *TravelMate AI - LangGraph Multi-Agent Travel Planner*.

```mermaid
flowchart LR
    Client["Client"] --> Guard["Rate Limiter / Auth / Route Guard"]
    Guard --> API["POST /api/travel<br/>router/router.py"]
    API --> Supervisor["Supervisor / Intent Router<br/>agents/intent_router.py"]

    Supervisor --> Hotel["Hotel Agent"]
    Supervisor --> Flight["Flight Agent"]
    Supervisor --> Weather["Weather Agent"]

    Hotel --> Lock["Optimistic Locking<br/>SharedMemory.update_with_retry()"]
    Flight --> Lock
    Weather --> Lock
    Lock --> Shared["Shared Memory<br/>state/shared_memory.py"]
    Shared --> Episodic["Episodic Memory<br/>PostgreSQL: agent_states, version_states"]

    Hotel --> Summarize["Summarize Agent<br/>Itinerary + Final Agent"]
    Flight --> Summarize
    Weather --> Summarize
    Summarize --> Fidelity["Instruction Fidelity<br/>summary covers only requested intent"]
    Fidelity -. feedback .-> Supervisor
```

How to read it:

| Design element | Implementation |
| --- | --- |
| Client → Guard → `POST /travel` | Browser UI (`templates/`, `static/`) → FastAPI app (`app.py`) → router (`router/router.py`) |
| Supervisor | `IntentRouter` (`agents/intent_router.py`) + `Nodes.route_intent()` — classifies intent and selects only needed agents |
| Hotel / Flight / Weather Agents | `HotelAgent`, `FlightAgent`, `WeatherAgent` (`agents/`) — run in parallel via LangGraph fan-out |
| Optimistic Locking | `SharedMemory.update_with_retry()` (`state/shared_memory.py`, used in `nodes/nodes.py:_commit`) — stale parallel writes are rejected and retried against the latest version instead of overwriting each other |
| Shared Memory | In-memory `SharedMemory` per `run_id` (`{version, hotel, flight, weather}`), persisted as snapshots |
| Episodic Memory | PostgreSQL (`database/postgres_database.py`) — `agent_states` + `version_states`; crashed runs replay completed agents by `run_id` |
| Summarize Agent | `ItineraryAgent` → `FinalAgent` (`agents/`) — builds the itinerary, then the final answer |
| Instruction Fidelity | `FinalAgent` receives the detected intent and writes a summary covering only the requested topics |

## Agent Architecture

```mermaid
flowchart TD
    START([START]) --> Router["Intent Router<br/>route_intent()"]
    Router -->|selected research agents, parallel| Flight["Flight Agent<br/>tavily_search via Tavily MCP"]
    Router --> Hotel["Hotel Agent<br/>tavily_search via Tavily MCP"]
    Router --> Weather["Weather Agent<br/>custom weather MCP server"]
    Router -->|itinerary only| Itinerary["Itinerary Agent<br/>no tools"]
    Router -->|summary only| Final["Final Agent<br/>no tools"]

    Flight --> After1{"after_research()"}
    Hotel --> After2{"after_research()"}
    Weather --> After3{"after_research()"}
    After1 -->|itinerary requested| Itinerary
    After2 -->|itinerary requested| Itinerary
    After3 -->|itinerary requested| Itinerary
    After1 -->|otherwise| Final
    After2 -->|otherwise| Final
    After3 -->|otherwise| Final

    Itinerary --> Final
    Final --> END([END])

    Flight -.-> SM["SharedMemory<br/>optimistic locking + version bump"]
    Hotel -.-> SM
    Weather -.-> SM
    Itinerary -.->|reads flight/hotel/weather| SM
    Final -.->|reads snapshot at current version, writes it back| SM
    SM -.-> PG[("PostgreSQL<br/>episodic memory")]
```

### Shared Memory & Versions — Itinerary / Final

- **Research agents (Flight/Hotel/Weather)** are the only ones that *write* to `SharedMemory` with optimistic locking: each commits its own field (`flight`/`hotel`/`weather`) via `Nodes._commit()` → `SharedMemory.update_with_retry()`, which bumps `version` by 1 (e.g. `1 → 2 → 3 → 4` for 3 parallel agents).
- **Itinerary Agent** *reads* the shared research data (`flight_results`/`hotel_results`/`weather_results` from `TravelState`, populated from the shared-memory commits) to build the itinerary, but it does **not** commit to `SharedMemory` and does **not** bump `version` — `SharedMemory.FIELDS` is only `("hotel", "flight", "weather")`.
- **Final Agent** *reads* the full shared-memory snapshot and writes it back at the **current** version (`Nodes.final_agent()` → `snapshot["version"]`), but also does **not** bump `version` and adds no `itinerary`/`final` field. It is the sole writer in its step, so the full authoritative snapshot can be written back without a concurrent-update conflict.
- Both Itinerary and Final therefore share data through the same `TravelState` + `SharedMemory` snapshot, and both *use* the current `version` for ordering, but only the parallel research agents advance it.

Agent responsibilities:

| Agent | File | MCP server / tools | Role |
| --- | --- | --- | --- |
| Intent Router | `agents/intent_router.py` | Structured LLM output (no tools) | Classifies intent, selects agents (e.g. hotels-only → only `HotelAgent`; full trip → flight + hotel + weather in parallel) |
| Flight Agent | `agents/flight_agent.py` | `tavily` — `tavily_search` | Flight research with Tavily web search |
| Hotel Agent | `agents/hotel_agent.py` | `tavily` — `tavily_search` | Hotel research with Tavily web search |
| Weather Agent | `agents/weather_agent.py` | `weather` — `get_current_weather`, `get_forecast` | Current weather + forecast via the custom local MCP server |
| Itinerary Agent | `agents/itinerary_agent.py` | None | Builds a practical day-by-day itinerary from research results |
| Final Agent | `agents/final_agent.py` | None | Formats the final answer covering only requested topics |

Every agent extends `BaseAgent` (`agents/base_agent.py`): it loads only its own MCP server's tools (`tools/mcp_tools.py:mcp_tools()`), runs `create_agent(...)`, counts LLM calls, and persists `start_agent` / `finish_agent` / `fail_agent` to PostgreSQL so completed agents replay on retry. Graph wiring is in `graph/travel_graph.py` (`build_graph()`), node functions in `nodes/nodes.py` (`Nodes`).

## State and MCP Integration

This project integrates MCP in several places:

- `Tavily` search uses a remote MCP endpoint at `https://mcp.tavily.com/mcp/`
- `Weather` is implemented with a custom local MCP server in `tools/custom_weather_mcp_server.py`

The MCP client is defined in `tools/mcp_tools.py`, which exposes one persistent-session context manager per MCP server:

- `mcp_tools("tavily")` — Tavily web search tools (flight + hotel agents)
- `mcp_tools("weather")` — the custom weather MCP server tools (weather agent)

Every graph node in `router/router.py` / `utils/backend_helpers.py` is its own LangChain agent, built with `create_agent`, and each agent only receives the MCP tools of the API it is responsible for. No agent calls an HTTP API directly.

Each agent lives in its own class under `agents/` and implements the `BaseAgent` interface:

- `FlightAgent`, `HotelAgent`, `WeatherAgent` — declare `mcp_server` / `mcp_tool_names` to receive their MCP server's tools
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

On startup the app connects to PostgreSQL, creates the table if needed and prints any agent runs that started but never finished (`startup_database()` in `utils/backend_helpers.py`). The same information is exposed by `GET /health`. If PostgreSQL is unreachable, the app still starts, logs the problem and runs with in-memory conversation checkpoints.

## Project Structure

```text
.
├── app.py                       # FastAPI app entry point (lifespan, static, include_router)
├── pyproject.toml               # Project metadata / dependencies
├── requirements.txt             # Python dependencies
├── router/
│   └── router.py                # APIRouter: /, /api/travel, /health, /favicon.ico
├── utils/
│   ├── backend_helpers.py       # LLM/DB/Graph setup, startup/shutdown, run_travel_agent
│   └── background_tasks.py      # Non-blocking DB save scheduling
├── graph/
│   └── travel_graph.py          # Graph wiring (build_graph)
├── state/
│   ├── travel_state.py          # TravelState schema
│   └── shared_memory.py         # SharedMemory with optimistic locking
├── nodes/
│   └── nodes.py                 # Nodes class (graph node functions, parallel research, commit)
├── enums/
│   └── enums.py                 # Shared enums (agents, intent, state keys)
├── tools/
│   ├── mcp_tools.py             # MCP client (tavily + weather persistent sessions)
│   └── custom_weather_mcp_server.py # Local weather MCP server
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
├── llm/                         # LLM factory (Groq)
├── prompt_catalog/              # Agent prompts
├── excalidraw_files/
│   └── design.excalidraw        # System design diagram
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
  - WeatherAPI (https://www.weatherapi.com/)

## Environment Variables

Create a `.env` file in the project root with the following variables:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/travel_db
GROQ_API_KEY=your_groq_api_key
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

If you need to customize the weather MCP server command, edit `tools/mcp_tools.py` and update the `weather` server path to your local Python environment.

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
2. The intent router classifies the request and selects the needed agents.
3. The flight and hotel agents call the remote Tavily MCP search tools in parallel.
4. The weather agent calls the custom weather MCP server tools.
5. Research results are committed to shared memory with optimistic locking (each commit bumps `version`).
6. The itinerary agent reads the shared research data and creates a practical travel plan (no version bump).
7. The final agent reads the shared-memory snapshot at the current version and formats the answer, which is returned through the web API.

## Contributing

Contributions are welcome. If you want to improve the app, add new travel features, or fix issues:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Open a pull request

## Acknowledgments

This project is built with the help of modern LLM tooling, MCP integrations, and travel APIs. It is intended as a practical example of combining LangGraph agents with real-world applications.
