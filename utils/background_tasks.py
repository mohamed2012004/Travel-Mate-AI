import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_tasks: set[asyncio.Task] = set()
_chains: dict[str, asyncio.Task] = {}


def schedule(key: str, coro_factory: Callable[[], Awaitable[None]]) -> asyncio.Task | None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("[background] no running loop; DB write skipped")
        return None

    previous = _chains.get(key)

    async def runner() -> None:
        if previous is not None:
            try:
                await previous
            except Exception:
                pass
        await coro_factory()

    task = loop.create_task(runner())
    _chains[key] = task
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    logger.info("[background] queued DB save key=%s (non-blocking)", key)
    return task


async def drain_background_tasks(timeout: float = 10.0) -> None:
    while _tasks:
        done, pending = await asyncio.wait(set(_tasks), timeout=timeout)
        for task in done:
            if task.exception() is not None:
                logger.warning("[background] task failed: %s", task.exception())
        if pending:
            logger.warning("[background] %d task(s) still pending on shutdown", len(pending))
            break
