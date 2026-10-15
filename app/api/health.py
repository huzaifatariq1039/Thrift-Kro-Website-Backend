import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.observability import request_metrics
from app.services.health import database_is_ready


router = APIRouter(include_in_schema=False)


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """Confirm that the API process can serve requests without external I/O."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(db: Session = Depends(get_db)):
    """Accept traffic only when the database is reachable and fully migrated."""
    if not database_is_ready(db):
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready"}


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(authorization: str | None = Header(default=None)) -> PlainTextResponse:
    """Expose bounded process metrics only when an operator token is configured."""
    token = os.getenv("METRICS_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=404, detail="Not found")
    supplied = authorization or ""
    if not hmac.compare_digest(supplied, f"Bearer {token}"):
        raise HTTPException(
            status_code=401,
            detail="Invalid metrics credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return PlainTextResponse(request_metrics.render(), media_type="text/plain; version=0.0.4")
