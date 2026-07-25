from sqlalchemy.orm import Session
from app.models.verification import VerificationLog
from uuid import UUID


def create_verification_log(
    db: Session,
    product_id: UUID,
    seller_id: UUID,
    similarity_score: float,
    detected_category: str,
    liveness_passed: bool,
    verification_hash: str,
    is_successful: bool,
) -> VerificationLog:
    """Create an audit log entry for a verification attempt."""
    db_log = VerificationLog(
        product_id=product_id,
        seller_id=seller_id,
        similarity_score=similarity_score,
        detected_category=detected_category,
        liveness_passed=liveness_passed,
        verification_hash=verification_hash,
        is_successful=is_successful,
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log


def get_verification_logs(db: Session, product_id: UUID):
    """Get all verification attempts for a product."""
    return (
        db.query(VerificationLog)
        .filter(VerificationLog.product_id == product_id)
        .order_by(VerificationLog.created_at.desc())
        .all()
    )
