"""
CRUD operations for Seller Verification Requests.

Rate-limit rule: 
  - Max 3 submissions per rolling 24-hour window.
  - After hitting the limit, seller enters a 1-week freeze.
  - After the freeze, the counter resets and they get 3 more attempts.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.models.seller_verification import SellerVerificationRequest
from app.models.user import SellerProfile, VerificationStatusEnum
from app.models.product import Product, ConditionEnum

# Constants
MAX_SUBMISSIONS_PER_DAY = 3
FREEZE_PERIOD_DAYS = 7


def get_verification_request(db: Session, request_id: UUID) -> Optional[SellerVerificationRequest]:
    return db.query(SellerVerificationRequest).filter(
        SellerVerificationRequest.id == request_id
    ).first()


def get_requests_by_seller(db: Session, seller_profile_id: UUID) -> List[SellerVerificationRequest]:
    return db.query(SellerVerificationRequest).filter(
        SellerVerificationRequest.seller_profile_id == seller_profile_id
    ).order_by(SellerVerificationRequest.created_at.desc()).all()


def get_pending_requests(db: Session, skip: int = 0, limit: int = 50) -> List[SellerVerificationRequest]:
    """Get all pending verification requests for admin review."""
    return db.query(SellerVerificationRequest).filter(
        SellerVerificationRequest.status == VerificationStatusEnum.PENDING
    ).order_by(SellerVerificationRequest.created_at.asc()).offset(skip).limit(limit).all()


def check_rate_limit(db: Session, seller_profile_id: UUID) -> Tuple[bool, int, Optional[datetime]]:
    """
    Check if the seller can submit a new verification request.
    
    Returns:
        (can_submit, submissions_today, freeze_until)
        - can_submit: True if allowed to submit
        - submissions_today: number of submissions in the current window
        - freeze_until: if frozen, when the freeze ends (None if not frozen)
    """
    now = datetime.now(timezone.utc)
    
    # Get all requests from this seller ordered by newest first
    all_requests = db.query(SellerVerificationRequest).filter(
        SellerVerificationRequest.seller_profile_id == seller_profile_id
    ).order_by(SellerVerificationRequest.created_at.desc()).all()
    
    if not all_requests:
        return True, 0, None
    
    # Check if seller has a currently PENDING request
    has_pending = any(r.status == VerificationStatusEnum.PENDING for r in all_requests)
    if has_pending:
        return False, 0, None  # Can't submit while one is pending
    
    # Check if already approved
    has_approved = any(r.status == VerificationStatusEnum.APPROVED for r in all_requests)
    if has_approved:
        return False, 0, None  # Already verified, no need to re-submit
    
    # Count submissions in the last 24 hours
    window_start = now - timedelta(hours=24)
    recent_submissions = [
        r for r in all_requests 
        if r.created_at and r.created_at.replace(tzinfo=timezone.utc) >= window_start
    ]
    submissions_today = len(recent_submissions)
    
    # If they hit the limit in the last 24 hours, enforce a 1-week freeze
    # from the time of the 3rd submission
    if submissions_today >= MAX_SUBMISSIONS_PER_DAY:
        third_submission = recent_submissions[0]  # Most recent = the one that hit limit
        freeze_until = third_submission.created_at.replace(tzinfo=timezone.utc) + timedelta(days=FREEZE_PERIOD_DAYS)
        if now < freeze_until:
            return False, submissions_today, freeze_until
        else:
            # Freeze has expired, reset counter (these old ones are outside the window)
            return True, 0, None
    
    return True, submissions_today, None


def create_verification_request(
    db: Session,
    seller_profile_id: UUID,
    data: dict,
) -> SellerVerificationRequest:
    """Create a new verification request and set seller profile to PENDING."""
    request = SellerVerificationRequest(
        seller_profile_id=seller_profile_id,
        business_name=data["business_name"],
        business_type=data["business_type"],
        phone_number=data["phone_number"],
        address=data["address"],
        city=data["city"],
        cnic_number=data.get("cnic_number"),
        cnic_front_url=data["cnic_front_url"],
        cnic_back_url=data["cnic_back_url"],
        business_reg_url=data.get("business_reg_url"),
        shop_photo_urls=data.get("shop_photo_urls", []),
        products_proof=data.get("products_proof", []),
        ai_verified=data.get("ai_verified", False),
        status=VerificationStatusEnum.PENDING,
    )
    db.add(request)
    
    # Update seller profile status to PENDING
    profile = db.query(SellerProfile).filter(SellerProfile.id == seller_profile_id).first()
    if profile:
        profile.verification_status = VerificationStatusEnum.PENDING
        # Also update the business info on the profile
        profile.phone_number = data["phone_number"]
        profile.address = data["address"]
        profile.city = data["city"]
        profile.business_type = data["business_type"]
        profile.cnic_number = data.get("cnic_number")
        profile.shop_name = data["business_name"]
    
    db.commit()
    db.refresh(request)
    return request


def review_verification_request(
    db: Session,
    request_id: UUID,
    admin_id: UUID,
    status: VerificationStatusEnum,
    rejection_reason: Optional[str] = None,
) -> Optional[SellerVerificationRequest]:
    """Admin approves or rejects a verification request."""
    request = get_verification_request(db, request_id)
    if not request:
        return None
    
    now = datetime.now(timezone.utc)
    
    request.status = status
    request.rejection_reason = rejection_reason
    request.reviewed_by = admin_id
    request.reviewed_at = now
    
    # Update the seller profile based on the decision
    profile = db.query(SellerProfile).filter(
        SellerProfile.id == request.seller_profile_id
    ).first()
    
    if profile:
        if status == VerificationStatusEnum.APPROVED:
            profile.is_verified = True
            profile.verification_status = VerificationStatusEnum.APPROVED
            profile.verified_at = now
        elif status == VerificationStatusEnum.REJECTED:
            profile.is_verified = False
            profile.verification_status = VerificationStatusEnum.REJECTED
    
    db.commit()
    db.refresh(request)
    return request
