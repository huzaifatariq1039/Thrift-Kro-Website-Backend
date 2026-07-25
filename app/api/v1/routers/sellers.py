"""
Seller Verification Router.

Endpoints:
- POST /sellers/verify                           — Submit verification request
- GET  /sellers/verification/me                   — Get my verification status
- GET  /sellers/verification/pending              — Admin: list pending requests
- GET  /sellers/verification/{request_id}         — Admin: view specific request
- PUT  /sellers/verification/{request_id}         — Admin: approve or reject
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.models.user import User, VerificationStatusEnum
from app.schemas.seller_verification import (
    SellerVerificationCreate,
    SellerVerificationResponse,
    SellerVerificationReview,
    SellerVerificationStatusResponse,
)
from app.api.deps import get_db, get_current_seller, get_current_admin
import app.crud.seller_verification as crud_sv

router = APIRouter()


# ─── Seller Endpoints ─────────────────────────────────────────────────

@router.post("/verify", response_model=SellerVerificationResponse, status_code=status.HTTP_201_CREATED)
def submit_verification(
    data: SellerVerificationCreate,
    db: Session = Depends(get_db),
    current_seller: User = Depends(get_current_seller),
):
    """
    Submit a verification request with business info and proof documents.
    
    Rate limit: max 3 submissions per day. After hitting the limit, 
    a 1-week freeze period is enforced before new submissions are allowed.
    """
    profile = current_seller.seller_profile
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No seller profile found. Please contact support.",
        )
    
    # Check if already verified
    if profile.verification_status == VerificationStatusEnum.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your account is already verified.",
        )
    
    # Check rate limit
    can_submit, submissions_today, freeze_until = crud_sv.check_rate_limit(db, profile.id)
    
    if not can_submit:
        if freeze_until:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"You have reached the maximum of 3 verification attempts. "
                       f"Please try again after {freeze_until.strftime('%Y-%m-%d %H:%M UTC')}.",
            )
        # Check if there's a pending request
        if profile.verification_status == VerificationStatusEnum.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You already have a pending verification request. Please wait for admin review.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot submit verification request at this time.",
        )
    
    request = crud_sv.create_verification_request(
        db=db,
        seller_profile_id=profile.id,
        data=data.model_dump(),
    )
    return request


@router.get("/verification/me", response_model=SellerVerificationStatusResponse)
def get_my_verification_status(
    db: Session = Depends(get_db),
    current_seller: User = Depends(get_current_seller),
):
    """Get the current seller's verification status, rate-limit info, and latest request."""
    profile = current_seller.seller_profile
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No seller profile found.",
        )
    
    can_submit, submissions_today, freeze_until = crud_sv.check_rate_limit(db, profile.id)
    
    # Get the latest request
    requests = crud_sv.get_requests_by_seller(db, profile.id)
    latest = requests[0] if requests else None
    
    return SellerVerificationStatusResponse(
        verification_status=profile.verification_status,
        is_verified=profile.is_verified,
        submissions_today=submissions_today,
        max_submissions_per_day=crud_sv.MAX_SUBMISSIONS_PER_DAY,
        can_submit=can_submit,
        freeze_until=freeze_until,
        latest_request=latest,
    )


# ─── Admin Endpoints ──────────────────────────────────────────────────

@router.get("/verification/pending", response_model=List[SellerVerificationResponse])
def list_pending_requests(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Admin: list all pending verification requests."""
    return crud_sv.get_pending_requests(db, skip=skip, limit=limit)


@router.get("/verification/{request_id}", response_model=SellerVerificationResponse)
def get_verification_request(
    request_id: UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Admin: view a specific verification request with all submitted documents."""
    request = crud_sv.get_verification_request(db, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Verification request not found")
    return request


@router.put("/verification/{request_id}", response_model=SellerVerificationResponse)
def review_verification_request(
    request_id: UUID,
    review: SellerVerificationReview,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """
    Admin: approve or reject a seller's verification request.
    
    - APPROVED: seller profile is marked as verified, seller can now list products.
    - REJECTED: seller profile stays unverified, a rejection_reason should be provided.
    """
    # Validate the status
    if review.status not in (VerificationStatusEnum.APPROVED, VerificationStatusEnum.REJECTED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be APPROVED or REJECTED.",
        )
    
    if review.status == VerificationStatusEnum.REJECTED and not review.rejection_reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A rejection reason is required when rejecting a verification.",
        )
    
    # Check the request exists and is pending
    existing = crud_sv.get_verification_request(db, request_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Verification request not found")
    if existing.status != VerificationStatusEnum.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This request has already been reviewed (status: {existing.status.value}).",
        )
    
    result = crud_sv.review_verification_request(
        db=db,
        request_id=request_id,
        admin_id=admin.id,
        status=review.status,
        rejection_reason=review.rejection_reason,
    )
    return result
