import asyncio
import json
import logging

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from database.base_database import (
    AgentStateRecord,
    BaseDatabase,
    UserRecord,
    VersionStateRecord,
)
from database.enum_database import (
    ADD_AGENT_STATE_ID_SQL,
    CONNECT_TIMEOUT_SECONDS,
    CREATE_AGENT_STATE_ID_INDEX_SQL,
    CREATE_STATUS_INDEX_SQL,
    CREATE_TABLE_SQL,
    CREATE_THREAD_INDEX_SQL,
    CREATE_USERS_TABLE_SQL,
    CREATE_VERSION_AGENT_STATE_INDEX_SQL,
    CREATE_VERSION_RUN_INDEX_SQL,
    CREATE_VERSION_STATES_TABLE_SQL,
    MAX_ERROR_LENGTH,
)
from database.utils_database import (
    _to_record,
    _to_user_record,
    _to_version_record,
    get_database_url,
)
from enums import AgentStatus

logger = logging.getLogger(__name__)


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
            SELECT id, run_id, thread_id, agent_name, status, output, error,
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
            SELECT id, run_id, thread_id, agent_name, status, output, error,
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
            SELECT id, run_id, thread_id, agent_name, status, output, error,
                   attempts, updated_at
            FROM agent_states
            WHERE status <> %s
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (AgentStatus.COMPLETED, limit),
        )

        return [_to_record(row) for row in rows]

    async def save_version_state(
        self,
        run_id: str,
        agent_state_id: int,
        version: int,
        shared_memory: dict,
    ) -> VersionStateRecord:
        rows = await asyncio.to_thread(
            self._fetch_all_sync,
            """
            INSERT INTO version_states (run_id, agent_state_id, version, shared_memory)
            VALUES (%s, %s, %s, %s::jsonb)
            ON CONFLICT (run_id, version) DO UPDATE
            SET agent_state_id = EXCLUDED.agent_state_id,
                shared_memory = EXCLUDED.shared_memory,
                updated_at = NOW()
            RETURNING id, run_id, agent_state_id, version, shared_memory,
                      created_at, updated_at
            """,
            (run_id, agent_state_id, version, json.dumps(shared_memory)),
        )
        return _to_version_record(rows[0])

    async def get_latest_version_state(self, run_id: str) -> VersionStateRecord | None:
        rows = await asyncio.to_thread(
            self._fetch_all_sync,
            """
            SELECT id, run_id, agent_state_id, version, shared_memory,
                   created_at, updated_at
            FROM version_states
            WHERE run_id = %s
            ORDER BY version DESC, id DESC
            LIMIT 1
            """,
            (run_id,),
        )
        return _to_version_record(rows[0]) if rows else None

    async def get_version_states(self, run_id: str) -> list[VersionStateRecord]:
        rows = await asyncio.to_thread(
            self._fetch_all_sync,
            """
            SELECT id, run_id, agent_state_id, version, shared_memory,
                   created_at, updated_at
            FROM version_states
            WHERE run_id = %s
            ORDER BY version ASC, id ASC
            """,
            (run_id,),
        )
        return [_to_version_record(row) for row in rows]

    async def create_user(self, email: str, hashed_password: str) -> UserRecord:
        try:
            rows = await asyncio.to_thread(
                self._fetch_all_sync,
                """
                INSERT INTO users (email, hashed_password)
                VALUES (%s, %s)
                RETURNING id, email, hashed_password, is_active, created_at, updated_at
                """,
                (email.lower(), hashed_password),
            )
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise ValueError("User with this email already exists") from exc
            raise
        return _to_user_record(rows[0])

    async def get_user_by_email(self, email: str) -> UserRecord | None:
        rows = await asyncio.to_thread(
            self._fetch_all_sync,
            """
            SELECT id, email, hashed_password, is_active, created_at, updated_at
            FROM users WHERE email = %s
            """,
            (email.lower(),),
        )
        return _to_user_record(rows[0]) if rows else None

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
        # version_states references agent_states(id), so the
        # surrogate id must exist before that table is created.
        self._execute_sync(ADD_AGENT_STATE_ID_SQL)
        self._execute_sync(CREATE_AGENT_STATE_ID_INDEX_SQL)
        self._execute_sync(CREATE_VERSION_STATES_TABLE_SQL)
        self._execute_sync(CREATE_VERSION_RUN_INDEX_SQL)
        self._execute_sync(CREATE_VERSION_AGENT_STATE_INDEX_SQL)
        self._execute_sync(CREATE_USERS_TABLE_SQL)

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
