"""Privacy-gated seller verification endpoints.

KYC collection and review remain unavailable until private object storage,
retention, deletion, and breach-response policies have been approved. Existing
request rows are exposed only as non-sensitive metadata.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_seller, get_db
from app.models.user import User
from app.schemas.kyc import (
    KYCRequestMetadataResponse,
    KYCVerificationStateResponse,
)
from app.services.audit import record_audit_event
import app.crud.seller_verification as crud_sv


router = APIRouter()

KYC_UNAVAILABLE_DETAIL = (
    "Seller identity verification is unavailable until private document "
    "storage and retention policy are configured"
)


@router.post("/verify", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
def submit_verification(
    current_seller: User = Depends(get_current_seller),
):
    """Fail closed instead of collecting identity data through public URLs."""
    del current_seller
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=KYC_UNAVAILABLE_DETAIL,
    )


@router.get("/verification/me", response_model=KYCVerificationStateResponse)
def get_my_verification_status(
    db: Session = Depends(get_db),
    current_seller: User = Depends(get_current_seller),
) -> KYCVerificationStateResponse:
    """Return workflow metadata without identity fields or document locations."""
    profile = current_seller.seller_profile
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No seller profile found.",
        )

    _, submissions_today, freeze_until = crud_sv.check_rate_limit(db, profile.id)
    requests = crud_sv.get_requests_by_seller(db, profile.id)
    latest = requests[0] if requests else None

    return KYCVerificationStateResponse(
        verification_status=profile.verification_status,
        is_verified=profile.is_verified,
        submissions_today=submissions_today,
        can_submit=False,
        freeze_until=freeze_until,
        latest_request=latest,
    )


@router.get(
    "/verification/pending",
    response_model=list[KYCRequestMetadataResponse],
)
def list_pending_requests(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """List non-sensitive pending-request metadata and audit the access."""
    requests = crud_sv.get_pending_requests(db, skip=skip, limit=limit)
    record_audit_event(
        db,
        actor_id=admin.id,
        action="seller_verification.metadata_listed",
        resource_type="seller_verification_request",
        resource_id=None,
        details={"result_count": len(requests)},
    )
    db.commit()
    return requests


@router.get(
    "/verification/{request_id}",
    response_model=KYCRequestMetadataResponse,
)
def get_verification_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Return non-sensitive request metadata and audit the administrator."""
    request = crud_sv.get_verification_request(db, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Verification request not found")

    record_audit_event(
        db,
        actor_id=admin.id,
        action="seller_verification.metadata_viewed",
        resource_type="seller_verification_request",
        resource_id=request.id,
    )
    db.commit()
    return request


@router.put(
    "/verification/{request_id}",
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
)
def review_verification_request(
    request_id: UUID,
    admin: User = Depends(get_current_admin),
):
    """Block review decisions when supporting evidence cannot be accessed safely."""
    del request_id, admin
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=KYC_UNAVAILABLE_DETAIL,
    )
