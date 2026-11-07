import asyncio
import os
import uuid

import certifi
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import psycopg
from psycopg.rows import dict_row

from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.postgres import PostgresSaver

from agents import message_text
from database import CONNECT_TIMEOUT_SECONDS, PostgresDatabase, get_database_url
from enums import CheckpointerBackend, StateKey
from graph import build_graph
from nodes import Nodes


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing. Please add it to your .env file.")


# =========================
# LLM
# =========================

llm = ChatGroq(
    model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    api_key=GROQ_API_KEY
)


# =========================
# Database
# =========================

DATABASE_URL = get_database_url()

# Agent state store: every agent saves its result here so a crashed run can
# be recovered instead of started over.
database = PostgresDatabase(DATABASE_URL)


# =========================
# Nodes
# =========================

nodes = Nodes(llm, database)


# =========================
# Build Graph
# =========================

graph = build_graph(nodes)


# =========================
# Conversation Checkpointer
# =========================

checkpointer_backend = CheckpointerBackend.UNSET
travel_graph = None



def _create_checkpointer():
    """Run without checkpoint persistence."""

    global checkpointer_backend

    checkpointer_backend = CheckpointerBackend.NONE

    print(
        "[backend] Running without checkpoints."
    )

    return None

 

def _ensure_travel_graph():
    global travel_graph

    if travel_graph is None:
        travel_graph = graph.compile(checkpointer=_create_checkpointer())

    return travel_graph


# =========================
# Database startup / shutdown
# =========================

async def startup_database() -> dict:
    """Connect to the database and report any agent work left unfinished.

    Called once when the app starts. A run that never finished shows up here,
    so a crashed run can be retried with its own run_id and its completed
    agents replayed from the database.
    """

    await asyncio.to_thread(_ensure_travel_graph)

    report = {
        "connected": False,
        "error": "",
        "unfinished": [],
        "checkpointer": checkpointer_backend,
    }

    try:
        await database.connect()
        await database.setup()
    except Exception as error:
        report["error"] = str(error)
        print(f"[database] connection failed: {error}")
        return report

    report["connected"] = True

    try:
        unfinished = await database.get_unfinished_agents()
    except Exception as error:
        report["error"] = str(error)
        print(f"[database] could not read unfinished agent runs: {error}")
        return report

    report["unfinished"] = [
        {
            "run_id": record.run_id,
            "thread_id": record.thread_id,
            "agent_name": record.agent_name,
            "status": record.status,
            "error": record.error,
            "attempts": record.attempts,
        }
        for record in unfinished
    ]

    print(f"[database] connected; {len(unfinished)} unfinished agent run(s) found")

    for item in report["unfinished"]:
        print(
            f"  - run={item['run_id']} thread={item['thread_id']} "
            f"agent={item['agent_name']} status={item['status']}"
        )

    return report


async def shutdown_database() -> None:
    await database.close()


# =========================
# Function for FastAPI
# =========================

async def run_travel_agent(
    user_input: str,
    thread_id: str | None = None,
    run_id: str | None = None
):
    """Run the travel workflow.

    Pass the same `run_id` again to resume a crashed run: agents that already
    completed load their saved output instead of running a second time.
    """

    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    if not run_id:
        run_id = f"run_{uuid.uuid4().hex}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    result = await _ensure_travel_graph().ainvoke(
        {
            StateKey.MESSAGES: [
                HumanMessage(content=user_input)
            ],
            StateKey.RUN_ID: run_id,
            StateKey.THREAD_ID: thread_id,
            StateKey.USER_QUERY: user_input,
            StateKey.INTENT: "",
            StateKey.SELECTED_AGENTS: [],
            StateKey.FLIGHT_RESULTS: "",
            StateKey.HOTEL_RESULTS: "",
            StateKey.WEATHER_RESULTS: "",
            StateKey.ITINERARY: "",
            StateKey.LLM_CALLS: 0
        },
        config=config
    )

    final_answer = message_text(result[StateKey.MESSAGES][-1])

    return {
        "thread_id": thread_id,
        "run_id": run_id,
        "intent": result.get(StateKey.INTENT, ""),
        "answer": final_answer,
        "flight_results": result.get(StateKey.FLIGHT_RESULTS, ""),
        "hotel_results": result.get(StateKey.HOTEL_RESULTS, ""),
        "weather_results": result.get(StateKey.WEATHER_RESULTS, ""),
        "itinerary": result.get(StateKey.ITINERARY, ""),
        "llm_calls": result.get(StateKey.LLM_CALLS, 0),
    }
