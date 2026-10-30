"""Small, process-local worker queue for expensive resume rendering.

The queue state itself is persisted on ``GeneratedResume``.  The executor only
controls local CPU work; a restart therefore never makes a completed artifact
ambiguous and failed/queued records can be retried idempotently by the API.
"""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
import threading
from typing import Callable

from app.core.config import settings


class ResumeGenerationQueue:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, settings.resume_generation_global_concurrency),
            thread_name_prefix="resume-generation",
        )
        self._condition = threading.Condition()
        self._active_users: set[str] = set()
        self._pending: deque[tuple[str, Callable[[], None]]] = deque()
        self._active_count = 0
        self._max_concurrency = max(1, settings.resume_generation_global_concurrency)

    def enqueue(self, owner_user_id: str, work: Callable[[], None]) -> None:
        """Run work with one active generation per candidate and a global cap."""
        # Keeping local/test execution synchronous makes the deterministic API
        # contract easy to exercise; production always uses the worker queue.
        if settings.environment.strip().lower() != "production":
            self._run(owner_user_id, work)
            return
        with self._condition:
            self._pending.append((owner_user_id, work))
            self._dispatch_locked()

    def _dispatch_locked(self) -> None:
        """Dispatch only work that can run now; blocked users do not occupy workers."""
        while self._active_count < self._max_concurrency:
            ready_index = next(
                (index for index, (user_id, _) in enumerate(self._pending) if user_id not in self._active_users),
                None,
            )
            if ready_index is None:
                return
            owner_user_id, work = self._pending[ready_index]
            del self._pending[ready_index]
            self._active_users.add(owner_user_id)
            self._active_count += 1
            self._executor.submit(self._run, owner_user_id, work)

    def _run(self, owner_user_id: str, work: Callable[[], None]) -> None:
        with self._condition:
            # Production tasks reach here already claimed by _dispatch_locked.
            # Direct test/development work still needs the same per-user guard.
            direct_execution = settings.environment.strip().lower() != "production"
            if direct_execution:
                while owner_user_id in self._active_users:
                    self._condition.wait()
                self._active_users.add(owner_user_id)
        try:
            work()
        finally:
            with self._condition:
                self._active_users.discard(owner_user_id)
                if not direct_execution:
                    self._active_count -= 1
                    self._dispatch_locked()
                self._condition.notify_all()


resume_generation_queue = ResumeGenerationQueue()
