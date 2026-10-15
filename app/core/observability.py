"""Privacy-safe request correlation, structured logs, and bounded metrics."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any


REQUEST_ID_HEADER = b"x-request-id"
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def current_request_id() -> str | None:
    """Return the correlation ID for the active request, if one exists."""
    return _request_id.get()


def _validated_request_id(raw_value: str | None) -> str:
    if raw_value:
        try:
            return str(uuid.UUID(raw_value.strip()))
        except (ValueError, AttributeError):
            pass
    return str(uuid.uuid4())


class _JsonRequestFormatter(logging.Formatter):
    """Serialize only explicitly approved fields; arbitrary messages are ignored."""

    _fields = (
        "event",
        "request_id",
        "method",
        "route",
        "status_code",
        "duration_ms",
        "error_type",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }
        for field in self._fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _build_request_logger() -> logging.Logger:
    logger = logging.getLogger("app.request")
    if not any(getattr(handler, "_thrift_request_handler", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonRequestFormatter())
        handler._thrift_request_handler = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


request_logger = _build_request_logger()


class RequestMetrics:
    """Small in-process Prometheus registry with bounded route/status labels."""

    _duration_bounds = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf"))

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self._duration_seconds: dict[tuple[str, str], float] = defaultdict(float)
        self._duration_counts: dict[tuple[str, str], int] = defaultdict(int)
        self._duration_buckets: dict[tuple[str, str, float], int] = defaultdict(int)
        self._events: dict[tuple[str, str, str], int] = defaultdict(int)
        self._event_labels: set[tuple[str, str]] = set()
        self._in_flight = 0

    def started(self) -> None:
        with self._lock:
            self._in_flight += 1

    def finished(self, method: str, route: str, status_code: int, duration: float) -> None:
        status_class = f"{status_code // 100}xx"
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            self._requests[(method, route, status_class)] += 1
            self._duration_seconds[(method, route)] += duration
            self._duration_counts[(method, route)] += 1
            for bound in self._duration_bounds:
                if duration <= bound:
                    self._duration_buckets[(method, route, bound)] += 1

    def operational_event(self, category: str, event: str, outcome: str) -> None:
        """Count a staged business/security event with a hard cardinality ceiling."""
        if not re.fullmatch(r"[a-z0-9_.-]{1,96}", category):
            category = "other"
        if not re.fullmatch(r"[a-z0-9_.-]{1,96}", event):
            event = "other"
        if outcome not in {"success", "failure"}:
            outcome = "other"
        with self._lock:
            label = (category, event)
            if label not in self._event_labels:
                if len(self._event_labels) >= 64:
                    label = ("other", "other")
                else:
                    self._event_labels.add(label)
            self._events[(label[0], label[1], outcome)] += 1

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')

    def render(self) -> str:
        with self._lock:
            requests = dict(self._requests)
            durations = dict(self._duration_seconds)
            duration_counts = dict(self._duration_counts)
            duration_buckets = dict(self._duration_buckets)
            events = dict(self._events)
            in_flight = self._in_flight

        lines = [
            "# HELP thrift_http_requests_total Total HTTP requests.",
            "# TYPE thrift_http_requests_total counter",
        ]
        for (method, route, status_class), count in sorted(requests.items()):
            labels = (
                f'method="{self._escape(method)}",'
                f'route="{self._escape(route)}",'
                f'status_class="{status_class}"'
            )
            lines.append(f"thrift_http_requests_total{{{labels}}} {count}")

        lines.extend(
            [
                "# HELP thrift_http_request_duration_seconds Request duration histogram.",
                "# TYPE thrift_http_request_duration_seconds histogram",
            ]
        )
        for (method, route, bound), count in sorted(
            duration_buckets.items(),
            key=lambda item: (item[0][0], item[0][1], item[0][2]),
        ):
            labels = f'method="{self._escape(method)}",route="{self._escape(route)}"'
            le = "+Inf" if bound == float("inf") else f"{bound:g}"
            lines.append(
                f'thrift_http_request_duration_seconds_bucket{{{labels},le="{le}"}} {count}'
            )
        for (method, route), duration in sorted(durations.items()):
            labels = f'method="{self._escape(method)}",route="{self._escape(route)}"'
            lines.append(f"thrift_http_request_duration_seconds_sum{{{labels}}} {duration:.6f}")
            lines.append(
                f"thrift_http_request_duration_seconds_count{{{labels}}} "
                f"{duration_counts[(method, route)]}"
            )

        lines.extend(
            [
                "# HELP thrift_http_requests_in_flight Requests currently being processed.",
                "# TYPE thrift_http_requests_in_flight gauge",
                f"thrift_http_requests_in_flight {in_flight}",
            ]
        )
        lines.extend(
            [
                "# HELP thrift_operational_events_total Staged business and security events.",
                "# TYPE thrift_operational_events_total counter",
            ]
        )
        for (category, event, outcome), count in sorted(events.items()):
            labels = f'category="{category}",event="{event}",outcome="{outcome}"'
            lines.append(f"thrift_operational_events_total{{{labels}}} {count}")

        return "\n".join(lines) + "\n"


request_metrics = RequestMetrics()


class ObservabilityMiddleware:
    """Pure ASGI middleware that never records request content or identity data."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        raw_request_id = headers.get(REQUEST_ID_HEADER, b"").decode("ascii", errors="ignore")
        request_id = _validated_request_id(raw_request_id)
        token = _request_id.set(request_id)
        method = str(scope.get("method", "UNKNOWN")).upper()
        status_code = 500
        started_at = time.perf_counter()
        request_metrics.started()

        async def send_with_request_id(message: dict) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
                response_headers = list(message.get("headers") or [])
                response_headers = [
                    (name, value) for name, value in response_headers
                    if name.lower() != REQUEST_ID_HEADER
                ]
                response_headers.append((REQUEST_ID_HEADER, request_id.encode("ascii")))
                message["headers"] = response_headers
            await send(message)

        error_type: str | None = None
        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            duration = time.perf_counter() - started_at
            route = getattr(scope.get("route"), "path", "unmatched")
            if not isinstance(route, str) or not route.startswith("/"):
                route = "unmatched"
            request_metrics.finished(method, route, status_code, duration)
            request_logger.info(
                "request",
                extra={
                    "event": "http_request_completed",
                    "request_id": request_id,
                    "method": method,
                    "route": route,
                    "status_code": status_code,
                    "duration_ms": round(duration * 1000, 3),
                    "error_type": error_type,
                },
            )
            _request_id.reset(token)
