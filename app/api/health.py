from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
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
