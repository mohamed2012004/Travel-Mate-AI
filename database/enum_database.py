MAX_ERROR_LENGTH = 2000
CONNECT_TIMEOUT_SECONDS = 5

CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

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

# agent_states originally had no surrogate key (PK is
# (run_id, agent_name)), so version_states could not reference
# it by id. Add a unique identity column; existing rows are
# back-filled with sequential values.
ADD_AGENT_STATE_ID_SQL = """
ALTER TABLE agent_states
ADD COLUMN IF NOT EXISTS id BIGINT GENERATED ALWAYS AS IDENTITY
"""

CREATE_AGENT_STATE_ID_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS agent_states_id_uidx
ON agent_states (id)
"""

# One row per shared-memory version increment. Linked to the
# main table two ways: run_id groups a run's history, and
# agent_state_id is a FK to agent_states(id) recording which
# agent's commit produced the version.
CREATE_VERSION_STATES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS version_states (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id TEXT NOT NULL,
    agent_state_id BIGINT NOT NULL REFERENCES agent_states(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    shared_memory JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, version)
)
"""

CREATE_VERSION_RUN_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS version_states_run_idx
ON version_states (run_id)
"""

CREATE_VERSION_AGENT_STATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS version_states_agent_state_idx
ON version_states (agent_state_id)
"""

__all__ = [
    "ADD_AGENT_STATE_ID_SQL",
    "CONNECT_TIMEOUT_SECONDS",
    "CREATE_AGENT_STATE_ID_INDEX_SQL",
    "CREATE_STATUS_INDEX_SQL",
    "CREATE_TABLE_SQL",
    "CREATE_THREAD_INDEX_SQL",
    "CREATE_USERS_TABLE_SQL",
    "CREATE_VERSION_AGENT_STATE_INDEX_SQL",
    "CREATE_VERSION_RUN_INDEX_SQL",
    "CREATE_VERSION_STATES_TABLE_SQL",
    "MAX_ERROR_LENGTH",
]
