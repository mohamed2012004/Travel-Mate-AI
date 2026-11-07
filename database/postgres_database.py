import asyncio
import logging
import os

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from database.base_database import (
    AgentStateRecord,
    BaseDatabase,
)
from enums import AgentStatus

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 2000
CONNECT_TIMEOUT_SECONDS = 5

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS agent_states (
    run_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    status TEXT NOT NULL,
    output TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, agent_name)
)
"""

CREATE_THREAD_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS agent_states_thread_idx
ON agent_states (thread_id)
"""

CREATE_STATUS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS agent_states_status_idx
ON agent_states (status)
"""


def get_database_url() -> str:
    """Read and normalise the PostgreSQL connection URL."""

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Please add your Render PostgreSQL External Database URL to .env"
        )

    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    return database_url


def _to_record(row: dict) -> AgentStateRecord:
    return AgentStateRecord(
        run_id=row["run_id"],
        thread_id=row["thread_id"],
        agent_name=row["agent_name"],
        status=row["status"],
        output=row["output"] or "",
        error=row["error"] or "",
        attempts=row["attempts"],
        updated_at=row["updated_at"],
    )


class PostgresDatabase(BaseDatabase):
    """PostgreSQL backend used by the travel workflow.

    psycopg's async connections cannot run on the default Windows event loop,
    so this backend uses a thread-safe connection pool and runs each query in
    a worker thread. The public API stays async for the agents.
    """

    def __init__(self, database_url: str, min_size: int = 1, max_size: int = 5):
        self.database_url = database_url
        self.min_size = min_size
        self.max_size = max_size
        self._pool: ConnectionPool | None = None

    @property
    def connected(self) -> bool:
        return self._pool is not None and not self._pool.closed

    async def connect(self) -> None:
        if self.connected:
            return

        await asyncio.to_thread(self._connect_sync)

    async def close(self) -> None:
        if self._pool is None:
            return

        pool, self._pool = self._pool, None

        await asyncio.to_thread(pool.close)

    async def setup(self) -> None:
        await asyncio.to_thread(self._setup_sync)

    async def start_agent(self, run_id: str, thread_id: str, agent_name: str) -> None:
        await asyncio.to_thread(
            self._execute_sync,
            """
            INSERT INTO agent_states
                (run_id, thread_id, agent_name, status, output, error, attempts)
            VALUES (%s, %s, %s, %s, '', '', 1)
            ON CONFLICT (run_id, agent_name) DO UPDATE
            SET status = EXCLUDED.status,
                error = '',
                attempts = agent_states.attempts + 1,
                updated_at = NOW()
            """,
            (run_id, thread_id, agent_name, AgentStatus.RUNNING),
        )

    async def finish_agent(self, run_id: str, agent_name: str, output: str) -> None:
        await asyncio.to_thread(
            self._execute_sync,
            """
            UPDATE agent_states
            SET status = %s, output = %s, error = '', updated_at = NOW()
            WHERE run_id = %s AND agent_name = %s
            """,
            (AgentStatus.COMPLETED, output, run_id, agent_name),
        )

    async def fail_agent(self, run_id: str, agent_name: str, error: str) -> None:
        await asyncio.to_thread(
            self._execute_sync,
            """
            UPDATE agent_states
            SET status = %s, error = %s, updated_at = NOW()
            WHERE run_id = %s AND agent_name = %s
            """,
            (AgentStatus.FAILED, error[:MAX_ERROR_LENGTH], run_id, agent_name),
        )

    async def get_agent_state(self, run_id: str, agent_name: str) -> AgentStateRecord | None:
        rows = await asyncio.to_thread(
            self._fetch_all_sync,
            """
            SELECT run_id, thread_id, agent_name, status, output, error,
                   attempts, updated_at
            FROM agent_states
            WHERE run_id = %s AND agent_name = %s
            """,
            (run_id, agent_name),
        )

        return _to_record(rows[0]) if rows else None

    async def get_run_states(self, run_id: str) -> dict[str, AgentStateRecord]:
        rows = await asyncio.to_thread(
            self._fetch_all_sync,
            """
            SELECT run_id, thread_id, agent_name, status, output, error,
                   attempts, updated_at
            FROM agent_states
            WHERE run_id = %s
            """,
            (run_id,),
        )

        records = [_to_record(row) for row in rows]

        return {record.agent_name: record for record in records}

    async def get_unfinished_agents(self, limit: int = 20) -> list[AgentStateRecord]:
        rows = await asyncio.to_thread(
            self._fetch_all_sync,
            """
            SELECT run_id, thread_id, agent_name, status, output, error,
                   attempts, updated_at
            FROM agent_states
            WHERE status <> %s
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (AgentStatus.COMPLETED, limit),
        )

        return [_to_record(row) for row in rows]

    def _connect_sync(self) -> None:
        pool = ConnectionPool(
            conninfo=self.database_url,
            min_size=self.min_size,
            max_size=self.max_size,
            open=False,
            kwargs={
                "autocommit": True,
                "row_factory": dict_row,
                "connect_timeout": CONNECT_TIMEOUT_SECONDS,
            },
            timeout=CONNECT_TIMEOUT_SECONDS,
        )

        pool.open(wait=True, timeout=CONNECT_TIMEOUT_SECONDS)

        self._pool = pool

    def _setup_sync(self) -> None:
        self._execute_sync(CREATE_TABLE_SQL)
        self._execute_sync(CREATE_THREAD_INDEX_SQL)
        self._execute_sync(CREATE_STATUS_INDEX_SQL)

    def _execute_sync(self, sql: str, params: tuple | None = None) -> None:
        pool = self._require_pool()

        with pool.connection() as connection:
            connection.execute(sql, params)

    def _fetch_all_sync(self, sql: str, params: tuple | None = None) -> list[dict]:
        pool = self._require_pool()

        with pool.connection() as connection:
            cursor = connection.execute(sql, params)

            return cursor.fetchall()

    def _require_pool(self) -> ConnectionPool:
        if self._pool is None:
            raise RuntimeError("Database is not connected. Call connect() first.")

        return self._pool
