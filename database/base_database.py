from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from enums import AgentStatus


@dataclass
class AgentStateRecord:
    """What the database remembers about one agent's work inside one run."""

    run_id: str
    thread_id: str
    agent_name: str
    status: str
    output: str = ""
    error: str = ""
    attempts: int = 0
    updated_at: datetime | None = None

    @property
    def is_completed(self) -> bool:
        return self.status == AgentStatus.COMPLETED and bool(self.output)


class BaseDatabase(ABC):
    """Interface every workflow persistence backend implements.

    An agent calls `start_agent` before it works, `finish_agent` once it has
    an answer and `fail_agent` if it crashes. `get_agent_state` is what makes
    recovery possible: a completed record means the agent's work can be
    replayed instead of repeated.
    """

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether the backend is ready to accept queries."""

    @abstractmethod
    async def connect(self) -> None:
        """Open the connection / pool."""

    @abstractmethod
    async def close(self) -> None:
        """Close the connection / pool."""

    @abstractmethod
    async def setup(self) -> None:
        """Create the tables this backend needs."""

    @abstractmethod
    async def start_agent(self, run_id: str, thread_id: str, agent_name: str) -> None:
        """Mark an agent as running for this run."""

    @abstractmethod
    async def finish_agent(self, run_id: str, agent_name: str, output: str) -> None:
        """Store an agent's successful output for recovery."""

    @abstractmethod
    async def fail_agent(self, run_id: str, agent_name: str, error: str) -> None:
        """Store an agent's failure for recovery."""

    @abstractmethod
    async def get_agent_state(self, run_id: str, agent_name: str) -> AgentStateRecord | None:
        """Return the stored state of one agent in one run."""

    @abstractmethod
    async def get_run_states(self, run_id: str) -> dict[str, AgentStateRecord]:
        """Return the stored state of every agent in one run, keyed by agent name."""

    @abstractmethod
    async def get_unfinished_agents(self, limit: int = 20) -> list[AgentStateRecord]:
        """Return agent runs that started but never completed."""
