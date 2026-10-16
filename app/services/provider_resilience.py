"""Small, bounded resilience primitives for synchronous provider SDK calls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import threading
import time
from typing import TypeVar

import requests


Result = TypeVar("Result")


class ProviderCircuitOpenError(RuntimeError):
    def __init__(self, provider: str, retry_after: int):
        super().__init__(f"{provider} provider circuit is open")
        self.provider = provider
        self.retry_after = max(1, retry_after)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    base_delay_seconds: float = 0.1

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.max_attempts > 3:
            raise ValueError("Provider max_attempts must be between 1 and 3")
        if self.base_delay_seconds < 0 or self.base_delay_seconds > 1:
            raise ValueError("Provider base delay must be between 0 and 1 second")


class ProviderCircuitBreaker:
    """Open briefly after repeated transient failures within one process."""

    def __init__(
        self,
        provider: str,
        *,
        failure_threshold: int = 5,
        recovery_seconds: float = 30,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        if recovery_seconds <= 0:
            raise ValueError("recovery_seconds must be positive")
        self.provider = provider
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._open_until = 0.0

    def before_call(self) -> None:
        with self._lock:
            remaining = self._open_until - self._clock()
            if remaining > 0:
                raise ProviderCircuitOpenError(self.provider, int(remaining) + 1)
            if self._open_until:
                self._open_until = 0.0
                self._consecutive_failures = 0

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._open_until = 0.0

    def record_transient_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._open_until = self._clock() + self.recovery_seconds

    def reset(self) -> None:
        self.record_success()


def call_with_resilience(
    operation: Callable[[], Result],
    *,
    circuit: ProviderCircuitBreaker,
    retry_if: Callable[[Exception], bool],
    policy: RetryPolicy = RetryPolicy(),
    sleep: Callable[[float], None] = time.sleep,
) -> Result:
    """Run one logical provider call with a hard retry budget."""
    circuit.before_call()
    for attempt in range(policy.max_attempts):
        try:
            result = operation()
        except Exception as exc:
            transient = retry_if(exc)
            has_retry = transient and attempt + 1 < policy.max_attempts
            if has_retry:
                sleep(policy.base_delay_seconds * (2 ** attempt))
                continue
            if transient:
                circuit.record_transient_failure()
            raise
        circuit.record_success()
        return result
    raise AssertionError("Provider retry loop exhausted without returning or raising")


def is_transient_requests_error(exc: Exception) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError):
        status_code = exc.response.status_code if exc.response is not None else None
        return status_code in {408, 425, 429} or (
            status_code is not None and status_code >= 500
        )
    return False
