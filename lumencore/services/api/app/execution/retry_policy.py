from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .task_models import ExecutionTask


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    delay_seconds: int
    next_available_at: datetime | None


class ExecutionRetryPolicy:
    def __init__(self, *, base_delay_seconds: int = 2, max_delay_seconds: int = 30) -> None:
        self.base_delay_seconds = max(1, int(base_delay_seconds))
        self.max_delay_seconds = max(self.base_delay_seconds, int(max_delay_seconds))

    def evaluate(self, task: ExecutionTask) -> RetryDecision:
        if task.retries >= task.max_retries:
            return RetryDecision(False, 0, None)
        delay = min(self.base_delay_seconds * (2 ** int(task.retries)), self.max_delay_seconds)
        next_available_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        return RetryDecision(True, delay, next_available_at)
