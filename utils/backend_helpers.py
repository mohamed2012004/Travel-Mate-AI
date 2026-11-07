import asyncio
import logging
import os
import time
import uuid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("workflow")

import certifi
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from langchain_core.messages import HumanMessage

from agents import message_text
from utils.background_tasks import drain_background_tasks
from database import PostgresDatabase, get_database_url
from enums import CheckpointerBackend, StateKey
from graph import build_graph
from llm import create_llm
from nodes import Nodes

# =========================
# LLM
# =========================
llm = create_llm()

# =========================
# Database
# =========================
DATABASE_URL = get_database_url()
database = PostgresDatabase(DATABASE_URL)

# =========================
# Nodes / Graph
# =========================
nodes = Nodes(llm, database)
graph = build_graph(nodes)

# =========================
# Conversation Checkpointer
# =========================
checkpointer_backend = CheckpointerBackend.UNSET
travel_graph = None


def create_checkpointer():
    global checkpointer_backend
    checkpointer_backend = CheckpointerBackend.NONE
    print("[backend] Running without checkpoints.")
    return None


def ensure_travel_graph():
    global travel_graph
    if travel_graph is None:
        travel_graph = graph.compile(checkpointer=create_checkpointer())
    return travel_graph

# Backwards-compatible private aliases
_create_checkpointer = create_checkpointer
_ensure_travel_graph = ensure_travel_graph


async def startup_database() -> dict:
    await asyncio.to_thread(ensure_travel_graph)
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
    await drain_background_tasks()
    await database.close()


async def run_travel_agent(
    user_input: str,
    thread_id: str | None = None,
    run_id: str | None = None
):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"
    if not run_id:
        run_id = f"run_{uuid.uuid4().hex}"
    started = time.perf_counter()
    logger.info("[workflow] START run=%s thread=%s query=%r", run_id, thread_id, user_input[:80])
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }
    result = await ensure_travel_graph().ainvoke(
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
            StateKey.VERSION: 1,
            StateKey.SHARED_MEMORY: {
                "version": 1,
                "hotel": None,
                "flight": None,
                "weather": None,
            },
            StateKey.LLM_CALLS: 0
        },
        config=config
    )
    final_answer = message_text(result[StateKey.MESSAGES][-1])
    logger.info(
        "[workflow] DONE run=%s elapsed=%.1fs intent=%s llm_calls=%s version=%s answer_chars=%d (DB saves continue in background)",
        run_id, time.perf_counter() - started, result.get(StateKey.INTENT),
        result.get(StateKey.LLM_CALLS), result.get(StateKey.VERSION), len(final_answer),
    )
    return {
        "thread_id": thread_id,
        "run_id": run_id,
        "intent": result.get(StateKey.INTENT, ""),
        "answer": final_answer,
        "flight_results": result.get(StateKey.FLIGHT_RESULTS, ""),
        "hotel_results": result.get(StateKey.HOTEL_RESULTS, ""),
        "weather_results": result.get(StateKey.WEATHER_RESULTS, ""),
        "itinerary": result.get(StateKey.ITINERARY, ""),
        "version": result.get(StateKey.VERSION, 1),
        "shared_memory": result.get(StateKey.SHARED_MEMORY, {}),
        "llm_calls": result.get(StateKey.LLM_CALLS, 0),
    }
