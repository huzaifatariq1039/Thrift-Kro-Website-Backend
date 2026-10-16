"""Truthful product-verification API contracts.

The production inference architecture is intentionally deferred. Read-only
status remains available, while inference entry points report that the
capability is unavailable instead of executing placeholder or obsolete code.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from sqlalchemy.orm import Session

from app.api.deps import get_current_seller, get_db
from app.models.user import RoleEnum, User, VerificationStatusEnum
from app.schemas.ai import VerificationResultResponse
from app.services.websocket_auth import (
    WebSocketAuthenticationError,
    authenticate_websocket_user,
    get_websocket_bearer_token,
)
import app.crud.product as crud_product
import app.crud.verification as crud_verification


router = APIRouter()

VERIFICATION_UNAVAILABLE_DETAIL = (
    "AI product verification is not available in this release"
)


@router.post("/verify-product", status_code=503)
async def verify_product(
    current_seller: User = Depends(get_current_seller),
):
    """Reject inference requests until a production engine is approved."""
    del current_seller
    raise HTTPException(status_code=503, detail=VERIFICATION_UNAVAILABLE_DETAIL)


@router.get(
    "/verification-status/{product_id}",
    response_model=VerificationResultResponse,
)
def get_verification_status(
    product_id: UUID,
    db: Session = Depends(get_db),
) -> VerificationResultResponse:
    """Return status backed by a successful server-side verification event."""
    product = crud_product.get_product(db, product_id=product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    evidence = None
    if product.is_ai_verified and product.verification_hash:
        evidence = crud_verification.get_successful_verification(
            db,
            product_id=product.id,
            verification_hash=product.verification_hash,
        )

    return VerificationResultResponse(
        is_verified=evidence is not None,
        similarity_score=evidence.similarity_score if evidence else None,
        detected_category=evidence.detected_category if evidence else None,
        verification_hash=evidence.verification_hash if evidence else None,
        verified_at=evidence.created_at if evidence else None,
    )


@router.websocket("/ws/verify/{product_id}")
async def websocket_verify(
    websocket: WebSocket,
    product_id: str,
    db: Session = Depends(get_db),
):
    """Authenticate securely, then report that inference remains deferred."""
    del product_id
    try:
        token = get_websocket_bearer_token(websocket)
        current_user = authenticate_websocket_user(token, db)
        if (
            current_user.role != RoleEnum.SELLER
            or current_user.seller_profile is None
            or current_user.seller_profile.verification_status
            != VerificationStatusEnum.APPROVED
        ):
            raise WebSocketAuthenticationError("Verified seller access required")
    except WebSocketAuthenticationError as exc:
        await websocket.close(code=1008, reason=str(exc))
        return

    await websocket.close(code=1013, reason=VERIFICATION_UNAVAILABLE_DETAIL)
