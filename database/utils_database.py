import json
import os

from database.base_database import AgentStateRecord, UserRecord, VersionStateRecord


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
        id=row.get("id"),
    )


def _to_version_record(row: dict) -> VersionStateRecord:
    shared_memory = row.get("shared_memory") or {}
    if isinstance(shared_memory, str):
        shared_memory = json.loads(shared_memory)
    return VersionStateRecord(
        run_id=row["run_id"],
        agent_state_id=row["agent_state_id"],
        version=row["version"],
        shared_memory=shared_memory,
        id=row.get("id"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _to_user_record(row: dict) -> UserRecord:
    return UserRecord(
        email=row["email"],
        hashed_password=row["hashed_password"],
        is_active=row.get("is_active", True),
        id=row.get("id"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


__all__ = [
    "get_database_url",
]
