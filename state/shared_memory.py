import threading
from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any


class VersionConflictError(RuntimeError):
    """Raised when an update is based on a stale version."""

    def __init__(self, expected: int, current: int):
        super().__init__(
            f"Version conflict: update based on version {expected}, "
            f"but shared memory is now at version {current}"
        )
        self.expected = expected
        self.current = current


class SharedMemory:
    """Thread-safe shared memory with optimistic locking.

    Layout:
        {"version": 1, "hotel": None, "flight": None, "weather": None}

    An update must state the version it read. If another agent has
    already advanced the version, the update is rejected
    (VersionConflictError) instead of overwriting newer data.
    """

    FIELDS = ("hotel", "flight", "weather")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {
            "version": 1,
            "hotel": None,
            "flight": None,
            "weather": None,
        }

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of the latest state."""
        with self._lock:
            return deepcopy(self._data)

    @property
    def version(self) -> int:
        with self._lock:
            return int(self._data["version"])

    def update(
        self, expected_version: int, updates: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Apply `updates` only if `expected_version` is still current.

        Rejects unknown fields and version itself. Increments the
        version by 1 only after a successful update.
        Returns the new snapshot.
        """
        invalid = set(updates) - set(self.FIELDS)
        if invalid:
            raise ValueError(f"Invalid shared_memory field(s): {sorted(invalid)}")

        with self._lock:
            current = int(self._data["version"])
            if expected_version != current:
                raise VersionConflictError(expected_version, current)
            for key, value in updates.items():
                self._data[key] = deepcopy(value)
            self._data["version"] = current + 1
            return deepcopy(self._data)

    def update_with_retry(
        self,
        updates: Mapping[str, Any] | Callable[[dict[str, Any]], Mapping[str, Any]],
        expected_version: int | None = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Update, re-reading and merging on a version conflict.

        `updates` may be a plain mapping, or a callable receiving the
        latest snapshot (without relying on a stale one) and returning
        the mapping to apply. On conflict the latest state is re-read,
        the result is merged into it, and the update is retried with
        the latest version. Raises VersionConflictError after
        `max_retries` unsuccessful attempts.
        """
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1")

        last_error: VersionConflictError | None = None
        for attempt in range(max_retries):
            snapshot = self.snapshot()
            base_version = (
                expected_version
                if attempt == 0 and expected_version is not None
                else int(snapshot["version"])
            )
            pending = updates(snapshot) if callable(updates) else updates
            try:
                return self.update(base_version, pending)
            except VersionConflictError as error:
                last_error = error
                continue

        assert last_error is not None
        raise last_error
