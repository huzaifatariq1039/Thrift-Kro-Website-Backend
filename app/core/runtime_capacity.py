"""Validated process and database capacity settings for this deployment."""

from dataclasses import dataclass
import os
from typing import Mapping


class RuntimeCapacityError(ValueError):
    """Raised when a deployment can exceed its declared safe capacity."""


@dataclass(frozen=True)
class RuntimeCapacity:
    database_pool_size: int
    database_max_overflow: int
    database_pool_timeout_seconds: int
    database_pool_recycle_seconds: int
    database_connection_budget: int
    web_concurrency: int
    app_replica_count: int

    @property
    def process_count(self) -> int:
        return self.web_concurrency * self.app_replica_count

    @property
    def maximum_app_connections(self) -> int:
        return self.process_count * (
            self.database_pool_size + self.database_max_overflow
        )


def _integer_setting(
    environ: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
) -> int:
    raw_value = environ.get(name, str(default))
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise RuntimeCapacityError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RuntimeCapacityError(f"{name} must be at least {minimum}")
    return value


def load_runtime_capacity(
    environ: Mapping[str, str] | None = None,
) -> RuntimeCapacity:
    """Load capacity limits and reject a pool configuration over its budget."""
    values = os.environ if environ is None else environ
    capacity = RuntimeCapacity(
        database_pool_size=_integer_setting(
            values, "DATABASE_POOL_SIZE", 5, minimum=1
        ),
        database_max_overflow=_integer_setting(
            values, "DATABASE_MAX_OVERFLOW", 5, minimum=0
        ),
        database_pool_timeout_seconds=_integer_setting(
            values, "DATABASE_POOL_TIMEOUT_SECONDS", 30, minimum=1
        ),
        database_pool_recycle_seconds=_integer_setting(
            values, "DATABASE_POOL_RECYCLE_SECONDS", 1800, minimum=1
        ),
        database_connection_budget=_integer_setting(
            values, "DATABASE_CONNECTION_BUDGET", 10, minimum=1
        ),
        web_concurrency=_integer_setting(values, "WEB_CONCURRENCY", 1, minimum=1),
        app_replica_count=_integer_setting(
            values, "APP_REPLICA_COUNT", 1, minimum=1
        ),
    )
    if capacity.maximum_app_connections > capacity.database_connection_budget:
        raise RuntimeCapacityError(
            "Configured application processes can open "
            f"{capacity.maximum_app_connections} database connections, exceeding "
            "DATABASE_CONNECTION_BUDGET="
            f"{capacity.database_connection_budget}. Reduce replicas, workers, pool "
            "size, or overflow before starting."
        )
    return capacity


def assert_local_chat_topology(capacity: RuntimeCapacity) -> None:
    """Prevent silent message loss while WebSocket delivery is process-local."""
    if capacity.process_count != 1:
        raise RuntimeCapacityError(
            "Chat delivery is process-local and requires exactly one application "
            "process. Keep WEB_CONCURRENCY=1 and APP_REPLICA_COUNT=1 until a shared "
            "pub/sub backplane is implemented."
        )

