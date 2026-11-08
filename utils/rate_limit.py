import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, status

from database.base_database import RateLimitRecord, UserRecord
from utils.auth import get_current_user

load_dotenv()

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_ENDPOINT = "/api/travel"


async def enforce_rate_limit(
    request: Request,
    current_user: UserRecord = Depends(get_current_user),
) -> RateLimitRecord:
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    from utils.backend_helpers import database

    record = await database.check_and_increment_rate_limit(
        user_id=current_user.id,
        endpoint=RATE_LIMIT_ENDPOINT,
        max_requests=RATE_LIMIT_REQUESTS,
        window_seconds=RATE_LIMIT_WINDOW_SECONDS,
    )
    if record.request_count > RATE_LIMIT_REQUESTS:
        retry_after = RATE_LIMIT_WINDOW_SECONDS
        if record.window_start is not None:
            reset_at = record.window_start + timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
            retry_after = max(1, int((reset_at - datetime.now(timezone.utc)).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW_SECONDS}s",
            headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(RATE_LIMIT_REQUESTS)},
        )
    return record
