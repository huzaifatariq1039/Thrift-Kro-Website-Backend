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

from sqlalchemy import func as sa_func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.seller_verification import SellerVerificationRequest
from app.models.user import SellerProfile, VerificationStatusEnum
from app.services.audit import record_audit_event

# Constants
MAX_SUBMISSIONS_PER_DAY = 3
FREEZE_PERIOD_DAYS = 7
SUBMISSION_WINDOW = timedelta(hours=24)
FREEZE_PERIOD = timedelta(days=FREEZE_PERIOD_DAYS)


class VerificationSubmissionError(ValueError):
    pass


class SellerProfileNotFoundError(VerificationSubmissionError):
    pass


class VerificationSubmissionBlockedError(VerificationSubmissionError):
    def __init__(
        self,
        *,
        submissions_in_window: int,
        freeze_until: Optional[datetime],
    ) -> None:
        super().__init__("Seller verification submission is not currently allowed")
        self.submissions_in_window = submissions_in_window
        self.freeze_until = freeze_until


def get_verification_request(db: Session, request_id: UUID) -> Optional[SellerVerificationRequest]:
    return db.query(SellerVerificationRequest).filter(
        SellerVerificationRequest.id == request_id
    ).first()


def get_latest_request_by_seller(
    db: Session,
    seller_profile_id: UUID,
) -> Optional[SellerVerificationRequest]:
    return (
        db.query(SellerVerificationRequest)
        .filter(SellerVerificationRequest.seller_profile_id == seller_profile_id)
        .order_by(
            SellerVerificationRequest.created_at.desc(),
            SellerVerificationRequest.id.desc(),
        )
        .first()
    )


def get_pending_requests(
    db: Session,
    skip: int = 0,
    limit: int = 50,
) -> List[SellerVerificationRequest]:
    """Get all pending verification requests for admin review."""
    return db.query(SellerVerificationRequest).filter(
        SellerVerificationRequest.status == VerificationStatusEnum.PENDING
    ).order_by(SellerVerificationRequest.created_at.asc()).offset(skip).limit(limit).all()


def check_rate_limit(
    db: Session,
    seller_profile_id: UUID,
) -> Tuple[bool, int, Optional[datetime]]:
    """
    Check if the seller can submit a new verification request.
    
    Returns:
        (can_submit, submissions_today, freeze_until)
        - can_submit: True if allowed to submit
        - submissions_today: number of submissions in the current window
        - freeze_until: if frozen, when the freeze ends (None if not frozen)
    """
    now = datetime.now(timezone.utc)
    window_start = now - SUBMISSION_WINDOW

    submissions_in_window, pending_count, approved_count = (
        db.query(
            sa_func.count(SellerVerificationRequest.id).filter(
                SellerVerificationRequest.created_at >= window_start
            ),
            sa_func.count(SellerVerificationRequest.id).filter(
                SellerVerificationRequest.status == VerificationStatusEnum.PENDING
            ),
            sa_func.count(SellerVerificationRequest.id).filter(
                SellerVerificationRequest.status == VerificationStatusEnum.APPROVED
            ),
        )
        .filter(SellerVerificationRequest.seller_profile_id == seller_profile_id)
        .one()
    )
    submissions_in_window = int(submissions_in_window or 0)

    # Derive the most recent threshold-crossing submission from a bounded
    # lookback. This preserves the seven-day freeze after the initial rolling
    # 24-hour window has passed without loading request rows into Python.
    quota_lookback = now - FREEZE_PERIOD - SUBMISSION_WINDOW
    threshold_rows = (
        db.query(
            SellerVerificationRequest.created_at.label("created_at"),
            sa_func.lag(
                SellerVerificationRequest.created_at,
                MAX_SUBMISSIONS_PER_DAY - 1,
            )
            .over(
                order_by=(
                    SellerVerificationRequest.created_at,
                    SellerVerificationRequest.id,
                )
            )
            .label("window_first_submission"),
        )
        .filter(
            SellerVerificationRequest.seller_profile_id == seller_profile_id,
            SellerVerificationRequest.created_at >= quota_lookback,
        )
        .subquery()
    )
    quota_reached_at = (
        db.query(sa_func.max(threshold_rows.c.created_at))
        .filter(
            threshold_rows.c.window_first_submission
            >= threshold_rows.c.created_at - SUBMISSION_WINDOW
        )
        .scalar()
    )
    freeze_until = None
    if quota_reached_at is not None:
        freeze_until = quota_reached_at.astimezone(timezone.utc) + FREEZE_PERIOD
        if freeze_until <= now:
            freeze_until = None

    can_submit = not pending_count and not approved_count and freeze_until is None
    return can_submit, submissions_in_window, freeze_until


def create_verification_request(
    db: Session,
    seller_profile_id: UUID,
    data: dict,
) -> SellerVerificationRequest:
    """Atomically enforce submission quota and create one pending request."""
    try:
        profile = (
            db.query(SellerProfile)
            .filter(SellerProfile.id == seller_profile_id)
            .with_for_update()
            .one_or_none()
        )
        if profile is None:
            raise SellerProfileNotFoundError("Seller profile not found")

        can_submit, submissions_in_window, freeze_until = check_rate_limit(
            db,
            seller_profile_id,
        )
        if not can_submit:
            raise VerificationSubmissionBlockedError(
                submissions_in_window=submissions_in_window,
                freeze_until=freeze_until,
            )

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

        profile.verification_status = VerificationStatusEnum.PENDING
        profile.phone_number = data["phone_number"]
        profile.address = data["address"]
        profile.city = data["city"]
        profile.business_type = data["business_type"]
        profile.cnic_number = data.get("cnic_number")
        profile.shop_name = data["business_name"]

        db.flush()
        db.commit()
        db.refresh(request)
        return request
    except VerificationSubmissionError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        diagnostic = getattr(getattr(exc, "orig", None), "diag", None)
        constraint_name = getattr(diagnostic, "constraint_name", "")
        if constraint_name == "uq_seller_verification_one_pending":
            raise VerificationSubmissionBlockedError(
                submissions_in_window=0,
                freeze_until=None,
            ) from exc
        raise
    except Exception:
        db.rollback()
        raise


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

    record_audit_event(
        db,
        actor_id=admin_id,
        action="seller_verification.reviewed",
        resource_type="seller_verification_request",
        resource_id=request.id,
        details={"decision": status.value},
    )
    
    db.commit()
    db.refresh(request)
    return request
