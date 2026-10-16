"""Fail-closed HTTP exposure policy for development and production."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import logging
import os
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)
PRODUCTION_ENVIRONMENTS = frozenset({"production", "prod"})


@dataclass(frozen=True)
class HttpSecurityPolicy:
    environment: str
    allowed_origins: tuple[str, ...]
    docs_enabled: bool

    @property
    def is_production(self) -> bool:
        return self.environment in PRODUCTION_ENVIRONMENTS


def _normalized_origin(raw_origin: str) -> str:
    origin = raw_origin.strip().rstrip("/")
    if origin == "*":
        return origin

    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "ALLOWED_ORIGINS entries must be absolute HTTP(S) origins without paths"
        )
    return origin


def load_http_security_policy(
    environment: Mapping[str, str] | None = None,
) -> HttpSecurityPolicy:
    values = os.environ if environment is None else environment
    app_environment = values.get("APP_ENV", "development").strip().lower()
    raw_allowed_origins = values.get("ALLOWED_ORIGINS", "").strip()
    is_production = app_environment in PRODUCTION_ENVIRONMENTS

    if not raw_allowed_origins:
        if is_production:
            raise RuntimeError("ALLOWED_ORIGINS is required when APP_ENV=production")
        allowed_origins = ()
    else:
        allowed_origins = tuple(
            dict.fromkeys(
                _normalized_origin(origin)
                for origin in raw_allowed_origins.split(",")
                if origin.strip()
            )
        )
        if not allowed_origins:
            raise RuntimeError("ALLOWED_ORIGINS must contain at least one origin")

    if "*" in allowed_origins:
        raise RuntimeError("Wildcard CORS is forbidden; list every trusted origin")

    requested_docs = values.get("ENABLE_API_DOCS", "false").strip().lower()
    docs_enabled = not is_production and requested_docs in {"1", "true", "yes", "on"}
    return HttpSecurityPolicy(
        environment=app_environment,
        allowed_origins=allowed_origins,
        docs_enabled=docs_enabled,
    )


async def unhandled_exception_response(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Log diagnostics server-side and return a stable, redacted response."""
    request_id = str(request.scope.get("request_id") or "unavailable")
    logger.error(
        "Unhandled application exception",
        extra={
            "event": "unhandled_exception",
            "request_id": request_id,
            "error_type": type(exc).__name__,
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": "internal_error",
            "detail": "An unexpected error occurred",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )
