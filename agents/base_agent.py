import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.tools import BaseTool

from database import AgentStateRecord, BaseDatabase
from enums import StateKey

logger = logging.getLogger(__name__)

# The workflow state is a plain dict, so agents stay independent of backend.py.
AgentState = Mapping[str, Any]


def message_text(message: AnyMessage) -> str:
    """Flatten a message's content into plain text."""

    content = getattr(message, "content", message)

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(part for part in parts if part)

    return str(content)


class BaseAgent(ABC):
    """Interface every TripMate agent implements.

    A concrete agent only declares its role prompt, the MCP tools it is
    allowed to use, and how the shared state becomes its input. This base
    class runs the agent and, when a database is configured, saves the
    result after every run so a crashed run can be recovered.
    """

    name: str = "agent"

    def __init__(self, model: BaseChatModel, database: BaseDatabase | None = None):
        self.model = model
        self.database = database
        self._graph = None

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The role definition this agent runs with."""

    @abstractmethod
    def build_prompt(self, state: AgentState) -> str:
        """Build this agent's input from the shared workflow state."""

    async def load_tools(self) -> Sequence[BaseTool]:
        """MCP tools this agent is allowed to use.

        Override in agents that need external data. Returns no tools by default.
        """

        return []

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

        await self._begin(run_id, thread_id)

        try:
            answer, llm_calls = await self._invoke(state)
        except Exception as error:
            await self._fail(run_id, str(error))
            raise

        await self._complete(run_id, answer)

        return answer, llm_calls

    async def _invoke(self, state: AgentState) -> tuple[str, int]:
        graph = await self._compiled()

        result = await graph.ainvoke(
            {StateKey.MESSAGES: [HumanMessage(content=self.build_prompt(state))]}
        )

        messages = result[StateKey.MESSAGES]

        return message_text(messages[-1]), sum(
            1 for message in messages if isinstance(message, AIMessage)
        )

    async def _compiled(self):
        if self._graph is None:
            self._graph = create_agent(
                model=self.model,
                tools=await self.load_tools(),
                system_prompt=self.system_prompt,
                name=self.name
            )

        return self._graph

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

    async def _begin(self, run_id: str, thread_id: str) -> None:
        if not run_id or not self._persistence_enabled:
            return

        try:
            await self.database.start_agent(run_id, thread_id, self.name)
        except Exception as error:
            logger.warning("[%s] could not record start: %s", self.name, error)

    async def _complete(self, run_id: str, output: str) -> None:
        if not run_id or not self._persistence_enabled:
            return

        try:
            await self.database.finish_agent(run_id, self.name, output)
        except Exception as error:
            logger.warning("[%s] could not save output: %s", self.name, error)

    async def _fail(self, run_id: str, error: str) -> None:
        if not run_id or not self._persistence_enabled:
            return

        try:
            await self.database.fail_agent(run_id, self.name, error)
        except Exception as db_error:
            logger.warning("[%s] could not record failure: %s", self.name, db_error)
