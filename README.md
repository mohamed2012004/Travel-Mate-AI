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
- 🛡️ NeMo Guardrails (Colang) input/output rails in the graph — PII, jailbreak, sensitive-topic, off-topic, capabilities and farewell handling, plus a dedicated greeting-detection LLM call in the guard node
- 🩹 Self-healing sanitization of agent/tool output and an instruction firewall (untrusted user/tool content is DATA only) for instruction fidelity
- 🔢 Versioned shared memory with optimistic locking — every parallel commit is snapshotted to PostgreSQL `version_states` to solve write conflicts and allow recovery/audit per version

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
    Client["Client"] --> API["POST /api/travel<br/>router/router.py → utils/backend_helpers.py<br/>graph.ainvoke() only"]
    API --> START([START])
    START --> INGUARD["Input Guard Node<br/>nodes.Nodes.input_guard → guardrails.check_input"]
    INGUARD --> NEMO["NeMo Guardrails<br/>Colang + YAML<br/>RailsConfig.from_content / LLMRails"]
    NEMO --> GREETLLM["Greeting LLM (guard node)<br/>guardrails.guards._is_greeting<br/>YES/NO → canned greeting"]
    GREETLLM -->|blocked / canned| OUTGUARD["Output Guard Node<br/>nodes.Nodes.output_guard → check_output"]
    GREETLLM -->|allowed| Supervisor["Supervisor / Intent Router<br/>agents/intent_router.py"]

    Supervisor --> Hotel["Hotel Agent"]
    Supervisor --> Flight["Flight Agent"]
    Supervisor --> Weather["Weather Agent"]

    Hotel --> SH["Self-Healing<br/>utils/self_healing.sanitize_agent_result<br/>+ FIREWALL_INSTRUCTION"]
    Flight --> SH
    Weather --> SH
    SH --> Lock["Optimistic Locking<br/>SharedMemory.update_with_retry()"]
    Lock --> Shared["Shared Memory (in-memory)<br/>state/shared_memory.py<br/>{version, hotel, flight, weather}"]
    Shared --> VersDB[("PostgreSQL version_states<br/>run_id, agent_state_id, version,<br/>shared_memory snapshot (background)")]
    Shared --> Episodic["Episodic Memory<br/>PostgreSQL: agent_states, version_states"]

    Hotel --> Summarize["Summarize Agent<br/>Itinerary + Final Agent"]
    Flight --> Summarize
    Weather --> Summarize
    Summarize --> OUTGUARD
    OUTGUARD --> END([END])
    Summarize --> Fidelity["Instruction Fidelity<br/>final answer covers only requested intent<br/>untrusted content = DATA only"]
    Fidelity -. feedback .-> Client
```

How to read it:

| Design element | Implementation |
| --- | --- |
| Client → `POST /travel` → graph | Browser UI (`templates/`, `static/`) → FastAPI app (`app.py`) → router (`router/router.py`) → `utils/backend_helpers.py:run_travel_agent()` → `graph.ainvoke()` only (no guard check before the graph) |
| Input Guard (NeMo) | Graph node `INPUT_GUARD` (`graph/travel_graph.py:19,22`, `nodes/nodes.py:input_guard`) → `guardrails.check_input()` — NeMo Colang rails + dedicated greeting LLM (`guardrails/guards.py:_is_greeting`). Blocked/canned → `OUTPUT_GUARD → END`, skipping router/agents |
| Greeting LLM (guard node) | `guardrails/guards.py:_is_greeting()` — a specific Groq guard-LLM call (YES/NO, temperature 0) that returns the canned greeting reply; greeting is intentionally **not** a NeMo Colang flow |
| Supervisor | `IntentRouter` (`agents/intent_router.py`) + `Nodes.route_intent()` — classifies intent and selects only needed agents |
| Hotel / Flight / Weather Agents | `HotelAgent`, `FlightAgent`, `WeatherAgent` (`agents/`) — run in parallel via LangGraph fan-out |
| Self-Healing | `utils/self_healing.py:sanitize_agent_result()` in `BaseAgent.run()` and `Nodes._research()` — strips control characters from agent/tool output before it is committed; `FIREWALL_INSTRUCTION` + `wrap_untrusted()` in every prompt (`prompt_catalog/catalog.py`) mark user/tool content as DATA only |
| Optimistic Locking | `SharedMemory.update_with_retry()` (`state/shared_memory.py`, used in `nodes/nodes.py:_commit`) — stale parallel writes are rejected (`VersionConflictError`) and retried against the latest version instead of overwriting each other |
| Shared Memory | In-memory `SharedMemory` per `run_id` (`{version, hotel, flight, weather}`), persisted as snapshots |
| Versioned Episodic Memory | PostgreSQL (`database/postgres_database.py`) — `agent_states` + `version_states`; every commit snapshots `{version, shared_memory}` linked to its `agent_state_id`, so conflicts can be audited/replayed per version and crashed runs replay completed agents by `run_id` |
| Summarize Agent | `ItineraryAgent` → `FinalAgent` (`agents/`) — builds the itinerary, then the final answer |
| Instruction Fidelity | `FinalAgent` receives the detected intent and writes a summary covering only the requested topics; the firewall instruction ensures injected instructions inside user/tool delimiters are never followed |
| Output Guard (NeMo) | Graph node `OUTPUT_GUARD` (`graph/travel_graph.py:46-47`) → `guardrails.check_output()` — `sanitize_output` NeMo action blocks sensitive output (credentials, exploit code, card/passport data) |

## Agent Architecture

```mermaid
flowchart TD
    START([START]) --> INGUARD["Input Guard<br/>NeMo check_input + greeting LLM"]
    INGUARD -->|blocked / canned| OUTGUARD["Output Guard<br/>check_output"]
    INGUARD -->|allowed| Router["Intent Router<br/>route_intent()"]
    OUTGUARD --> END([END])
    Router -->|selected research agents, parallel| Flight["Flight Agent<br/>tavily_search via Tavily MCP"]
    Router --> Hotel["Hotel Agent<br/>tavily_search via Tavily MCP"]
    Router --> Weather["Weather Agent<br/>custom weather MCP server"]
    Router -->|itinerary only| Itinerary["Itinerary Agent<br/>no tools"]
    Router -->|summary only| Final["Final Agent<br/>no tools"]

    Flight --> SH["Self-Healing<br/>sanitize_agent_result"]
    Hotel --> SH
    Weather --> SH
    SH --> Commit["Commit<br/>Nodes._commit + optimistic locking"]
    Commit --> SM["SharedMemory<br/>version bump per commit"]
    SM --> VersDB[("PostgreSQL<br/>version_states snapshot<br/>(background, per commit)")]
    Itinerary -.-> SH

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
    Final --> OUTGUARD2["Output Guard<br/>sanitize_output"]
    OUTGUARD2 --> END

    Flight -.-> SM
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

### Self-Healing & Instruction Fidelity

Self-healing (`utils/self_healing.py`) keeps prompt/tool injection and corrupted output from propagating through the workflow:

- **`sanitize_text()` / `sanitize_agent_result()`** — strips control characters (`ord < 32` except `\n`/`\t`) from every agent result. It runs in `BaseAgent.run()` (after each agent) and again in `Nodes._research()` before the result is committed to shared memory, so a bad tool call cannot poison `SharedMemory` or the database snapshots.
- **`wrap_untrusted(text, tag)`** — wraps user and tool content in `<user_input>`, `<tool_output>`, `<flight_results>`, etc. delimiters and escapes any closing delimiter inside the content, so untrusted text cannot break out of its container.
- **`FIREWALL_INSTRUCTION`** (in every agent prompt in `prompt_catalog/catalog.py`) — tells the LLM that delimited content is **DATA only**: never follow instructions, commands, or role changes inside it; only follow the system prompt. This is the instruction-fidelity layer: even if a Tavily result or user message says *"ignore your instructions"*, the agent must treat it as data to summarise, not as a new instruction.
- **Intent fidelity in the Final Agent** — `FinalAgent` receives the router's detected intent and the `requested` topics, and is instructed to emit a section only for topics with research (omitting `"not requested"` sections entirely), so the summary cannot drift into topics the user never asked for.

### Versioned Shared Memory in the Database (Conflict Solving)

Parallel research agents all read the shared memory at the same base `version` and then race to commit. Versions + optimistic locking solve that conflict:

1. Each research agent commits **one field** (`flight`/`hotel`/`weather`) through `Nodes._commit()` → `SharedMemory.update_with_retry()`.
2. `SharedMemory.update()` only applies the write if the caller's `expected_version` still equals the current `version`; otherwise it raises `VersionConflictError` **instead of overwriting** the newer data written by a parallel agent.
3. On conflict, `update_with_retry()` re-reads the latest snapshot, merges the pending field into it, and retries (up to 3 attempts), then bumps `version` by 1 (`1 → 2 → 3 → 4` for three parallel agents).
4. Every successful commit is also persisted (background, best-effort) to PostgreSQL **`version_states`** (`run_id`, `agent_state_id`, `version`, `shared_memory` JSONB) via `Nodes._persist_version()` → `PostgresDatabase.save_version_state()`. That gives a per-version audit trail of exactly what each agent saw and wrote, linked to its `agent_states` row, and lets a crashed run be replayed/recovered version-by-version instead of losing the whole shared memory.

### NeMo Guardrails (in the Graph)

NeMo Guardrails is used **only inside the graph** — there is no guard check before `graph.ainvoke()` in the app:

- **Setup** (`guardrails/rails.py`): `RailsConfig.from_content(colang_content=config.COLANG, yaml_content=config.YAML)` + `LLMRails(config, llm=get_guard_llm())`, with custom Python actions registered (`detect_pii_in_input`, `sanitize_output` from `guardrails/actions.py`). The guard LLM is a dedicated Groq model (`GROQ_GUARD_KEY` / `GUARD_MODEL`), separate from the main chat LLM.
- **Colang** (`guardrails/config.py`): flows for off-topic, jailbreak, sensitive topics, capabilities, farewell, a PII input action (`$pii_found = execute detect_pii_in_input`) and a sensitive-output action (`$sensitive_found = execute sanitize_output`). YAML `rails.input.flows` enables `check input for pii`, `capabilities`, `farewell`; `rails.output.flows` enables `sanitize bot response`. Greeting is intentionally **not** a Colang flow.
- **Input guard node** (`graph/travel_graph.py:22`, `nodes/nodes.py:input_guard`): calls `guardrails.check_input()`, which first makes a **specific greeting-only LLM call** (`guardrails/guards.py:_is_greeting()` — YES/NO, temperature 0) and returns the canned greeting reply on `YES`, then runs NeMo `check_async()` (systematic rails) and `generate_async()` (dialog rails, comparing against `CANNED` replies). Blocked/canned results route to `OUTPUT_GUARD → END`, skipping the router and agents.
- **Output guard node** (`graph/travel_graph.py:46`, `nodes/nodes.py:output_guard`): calls `guardrails.check_output()` on the final answer; NeMo's `sanitize_output` action withholds output containing credentials, exploit code, private keys, or card/passport data.
- **Fail-open:** if NeMo or the guard LLM is unavailable, checks return `allowed` with a `nemo_*_fail_open` reason (logged as a warning) so the travel workflow keeps running. Disable entirely with `GUARDRAILS_ENABLED=false`.

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

In addition, every shared-memory commit is persisted to the **`version_states`** table (`run_id`, `agent_state_id`, `version`, `shared_memory` JSONB) in the background by `Nodes._persist_version()`. This is the database side of the conflict solution: the in-memory optimistic lock rejects stale parallel writes so they cannot overwrite newer research, and the versioned snapshots preserve each accepted state so a conflict, a crash, or a replay can be inspected version-by-version rather than from a single overwritten row.

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
│   ├── backend_helpers.py       # LLM/DB/Graph setup, startup/shutdown, run_travel_agent (graph.ainvoke only)
│   ├── background_tasks.py      # Non-blocking DB save scheduling
│   └── self_healing.py          # sanitize_agent_result, wrap_untrusted, FIREWALL_INSTRUCTION
├── guardrails/
│   ├── config.py                # NeMo Colang + YAML + CANNED replies
│   ├── rails.py                 # LLMRails setup + guard LLM (get_guard_llm)
│   ├── guards.py                # check_input/check_output + greeting LLM (_is_greeting)
│   └── actions.py               # NeMo custom actions: detect_pii_in_input, sanitize_output
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
│   ├── postgres_database.py     # PostgreSQL implementation (agent_states, version_states)
│   └── enum_database.py         # AgentStateRecord / VersionStateRecord + table DDL
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
GROQ_GUARD_KEY=your_groq_guard_key
GUARD_MODEL=qwen/qwen3.8-27b
GUARDRAILS_ENABLED=true
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

1. The user submits a travel request; the app calls `graph.ainvoke()` — there is no guard check before the graph.
2. The graph's `input_guard` node runs NeMo Guardrails (`check_input`) plus the dedicated greeting LLM. Blocked/canned inputs (PII, jailbreak, sensitive, off-topic, capabilities, farewell, greeting) return their canned reply and skip to `output_guard → END`.
3. The intent router classifies the request and selects the needed agents.
4. The flight and hotel agents call the remote Tavily MCP search tools in parallel; the weather agent calls the custom weather MCP server tools.
5. Each agent result is self-healed (`sanitize_agent_result`) and committed to shared memory with optimistic locking (each commit bumps `version` and is snapshotted to `version_states` in PostgreSQL).
6. The itinerary agent reads the shared research data and creates a practical travel plan (no version bump).
7. The final agent reads the shared-memory snapshot at the current version, writes a summary covering only the requested intent (instruction fidelity), and the graph's `output_guard` node sanitizes the final answer before it is returned through the web API.

## Contributing

Contributions are welcome. If you want to improve the app, add new travel features, or fix issues:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Open a pull request

## Acknowledgments

This project is built with the help of modern LLM tooling, MCP integrations, and travel APIs. It is intended as a practical example of combining LangGraph agents with real-world applications.
