import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import BaseTool

from agents.utils_agents import message_text
from utils.background_tasks import schedule
from database import AgentStateRecord, BaseDatabase
from enums import StateKey
from tools.mcp_tools import mcp_tools

logger = logging.getLogger(__name__)

# The workflow state is a plain dict, so agents stay independent of backend.py.
AgentState = Mapping[str, Any]


class BaseAgent(ABC):
    """Interface every TripMate agent implements.

    A concrete agent only declares its role prompt, the MCP tools it is
    allowed to use, and how the shared state becomes its input. This base
    class runs the agent and, when a database is configured, saves the
    result after every run so a crashed run can be recovered.
    """

    name: str = "agent"
    mcp_server: str | None = None
    mcp_tool_names: tuple[str, ...] | None = None

    def __init__(self, model: BaseChatModel, database: BaseDatabase | None = None):
        self.model = model
        self.database = database

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The role definition this agent runs with."""

    @abstractmethod
    def build_prompt(self, state: AgentState) -> str:
        """Build this agent's input from the shared workflow state."""

    async def run(self, state: AgentState) -> tuple[str, int]:
        """Run the agent on the workflow state.

        Returns the agent's answer and how many LLM calls it made. If this
        agent already completed for the same run, the saved answer is reused.
        """

        run_id = str(state.get(StateKey.RUN_ID, ""))
        thread_id = str(state.get(StateKey.THREAD_ID, ""))

        saved = await self._load_saved_state(run_id)
        if saved is not None:
            logger.info(
                "[%s] recovering saved output for run %s", self.name, run_id
            )
            return saved.output, 0

        self._begin(run_id, thread_id)
        logger.info("[%s] START run=%s", self.name, run_id)
        started = time.perf_counter()

        try:
            answer, llm_calls = await self._invoke_with_mcp(state)
        except Exception as error:
            logger.error("[%s] FAILED run=%s elapsed=%.1fs error=%s", self.name, run_id, time.perf_counter() - started, error)
            self._fail(run_id, str(error))
            raise

        self._complete(run_id, answer)
        logger.info(
            "[%s] DONE run=%s elapsed=%.1fs llm_calls=%s chars=%d -> result returned, DB save queued in background",
            self.name, run_id, time.perf_counter() - started, llm_calls, len(answer),
        )

        return answer, llm_calls

    async def _invoke_with_mcp(self, state: AgentState) -> tuple[str, int]:
        if not self.mcp_server:
            return await self._invoke(state, tools=[])

        async with mcp_tools(self.mcp_server) as tools:
            if self.mcp_tool_names:
                tools = [t for t in tools if t.name in self.mcp_tool_names]
            logger.info("[%s] create_agent(tools=%s)", self.name, [t.name for t in tools])
            return await self._invoke(state, tools=tools)

    async def _invoke(self, state: AgentState, tools: Sequence[BaseTool]) -> tuple[str, int]:
        graph = create_agent(
            model=self.model,
            tools=list(tools),
            system_prompt=self.system_prompt,
            name=self.name,
        )

        result = await graph.ainvoke(
            {StateKey.MESSAGES: [HumanMessage(content=self.build_prompt(state))]}
        )

        messages = result[StateKey.MESSAGES]

        return message_text(messages[-1]), sum(
            1 for message in messages if isinstance(message, AIMessage)
        )

    @property
    def _persistence_enabled(self) -> bool:
        return self.database is not None and self.database.connected

    async def _load_saved_state(self, run_id: str) -> AgentStateRecord | None:
        if not run_id or not self._persistence_enabled:
            return None

        try:
            record = await self.database.get_agent_state(run_id, self.name)
        except Exception as error:
            logger.warning("[%s] could not read saved state: %s", self.name, error)
            return None

        return record if record is not None and record.is_completed else None

    def _begin(self, run_id: str, thread_id: str) -> None:
        if not run_id or not self._persistence_enabled:
            return
        schedule(f"{run_id}:{self.name}", lambda: self._save_start(run_id, thread_id))

    async def _save_start(self, run_id: str, thread_id: str) -> None:
        try:
            await self.database.start_agent(run_id, thread_id, self.name)
        except Exception as error:
            logger.warning("[%s] could not record start: %s", self.name, error)

    def _complete(self, run_id: str, output: str) -> None:
        if not run_id or not self._persistence_enabled:
            return
        schedule(f"{run_id}:{self.name}", lambda: self._save_complete(run_id, output))

    async def _save_complete(self, run_id: str, output: str) -> None:
        try:
            await self.database.finish_agent(run_id, self.name, output)
        except Exception as error:
            logger.warning("[%s] could not save output: %s", self.name, error)

    def _fail(self, run_id: str, error: str) -> None:
        if not run_id or not self._persistence_enabled:
            return
        schedule(f"{run_id}:{self.name}", lambda: self._save_fail(run_id, error))

    async def _save_fail(self, run_id: str, error: str) -> None:
        try:
            await self.database.fail_agent(run_id, self.name, error)
        except Exception as db_error:
            logger.warning("[%s] could not record failure: %s", self.name, db_error)
