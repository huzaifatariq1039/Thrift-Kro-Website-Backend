"""
AI Verification Router.

Endpoints:
- POST /ai/verify-product          — Legacy simple image analysis
- WS   /ws/verify/{product_id}     — Real-time 4-phase verification pipeline
- GET  /ai/verification-status/{product_id} — Check verification status
"""

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from app.core.config import settings
from app.core.database import SessionLocal
from app.schemas.ai import AIVerificationResponse, VerificationResultResponse
from app.models.user import User, RoleEnum
from app.api.deps import get_db, get_current_seller
from app.services.cv_service import (
    YOLOService,
    CLIPService,
    LivenessTracker,
    decode_base64_frame,
    load_image_from_url,
    generate_verification_hash,
    analyze_product_image,
)
import app.crud.product as crud_product
import app.crud.user as crud_user
import app.crud.verification as crud_verification

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Helper: Authenticate WebSocket via JWT token in query param ──────

def authenticate_ws_user(token: str, db: Session) -> User:
    """Validate a JWT token and return the User, or raise ValueError."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise ValueError("Invalid token: no subject")
    except JWTError:
        raise ValueError("Invalid or expired token")

    user = crud_user.get_user(db, user_id=user_id)
    if user is None:
        raise ValueError("User not found")
    if user.role != RoleEnum.SELLER:
        raise ValueError("Only sellers can verify products")
    return user


# ─── Helper: Send JSON message over WebSocket ─────────────────────────

async def ws_send(websocket: WebSocket, **kwargs):
    """Send a JSON message to the WebSocket client."""
    await websocket.send_text(json.dumps(kwargs))


# ─── Legacy Endpoint (kept for backward compatibility) ─────────────────

@router.post("/verify-product", response_model=AIVerificationResponse)
async def verify_product(
    file: UploadFile = File(...),
    current_seller: User = Depends(get_current_seller),
):
    """Legacy endpoint: upload an image for simple AI analysis."""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload an image.")

    try:
        image_bytes = await file.read()
        result = await analyze_product_image(image_bytes)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI processing failed: {str(e)}")


# ─── REST: Check Verification Status ──────────────────────────────────

@router.get("/verification-status/{product_id}", response_model=VerificationResultResponse)
def get_verification_status(product_id: UUID, db: Session = Depends(get_db)):
    """Check whether a product has been AI-verified."""
    product = crud_product.get_product(db, product_id=product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return VerificationResultResponse(
        is_verified=product.is_ai_verified,
        similarity_score=product.condition_score / 100.0 if product.condition_score else None,
        detected_category=product.category,
        verification_hash=product.verification_hash,
        verified_at=product.verified_at,
    )


# ─── WebSocket: Real-Time Verification Pipeline ───────────────────────

@router.websocket("/ws/verify/{product_id}")
async def websocket_verify(websocket: WebSocket, product_id: str, token: str = Query(...)):
    """
    Real-time AI verification over WebSocket.
    
    Query params:
        token: JWT access token for authentication
    
    Client sends:
        {"frame": "<base64 JPEG>"} — camera frames
    
    Server sends phase updates:
        {"phase": "detection|liveness|matching|complete|error", ...}
    
    Phases:
        1. detection — YOLO scans frames until an object is detected
        2. liveness  — Track bbox movement to confirm 3D physical object
        3. matching  — CLIP compares live frame to listing photos
        4. complete  — Verification result with hash
    """
    # --- Setup: Authenticate and load product ---
    db = SessionLocal()
    try:
        user = authenticate_ws_user(token, db)
    except ValueError as e:
        await websocket.close(code=4001, reason=str(e))
        db.close()
        return

    try:
        product_uuid = UUID(product_id)
    except ValueError:
        await websocket.close(code=4002, reason="Invalid product ID")
        db.close()
        return

    product = crud_product.get_product(db, product_id=product_uuid)
    if not product:
        await websocket.close(code=4004, reason="Product not found")
        db.close()
        return

    if product.seller_id != user.id:
        await websocket.close(code=4003, reason="You can only verify your own products")
        db.close()
        return

    # Accept the connection
    await websocket.accept()

    # Initialize AI services
    yolo_service = YOLOService()
    clip_service = CLIPService()
    liveness_tracker = LivenessTracker()

    # Load reference images from the product listing
    reference_urls = []
    if product.image_url:
        reference_urls.append(product.image_url)
    if product.images:
        reference_urls.extend(product.images)

    # State tracking
    current_phase = "detection"
    best_detection = None
    best_frame_pil = None  # Best frame for CLIP matching
    best_confidence = 0.0

    try:
        # ─── Phase 1: Detection ───────────────────────────────
        await ws_send(
            websocket,
            phase="detection",
            message="Hold your item in front of the camera. We're scanning for it...",
        )

        while current_phase == "detection":
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                frame_b64 = data.get("frame", "")
            except (json.JSONDecodeError, AttributeError):
                frame_b64 = raw

            if not frame_b64:
                continue

            try:
                numpy_frame, pil_image = decode_base64_frame(frame_b64)
            except Exception:
                await ws_send(websocket, phase="error", message="Failed to decode frame")
                continue

            # Run YOLO detection
            detection = yolo_service.detect_any_object(numpy_frame)

            if detection and detection.confidence >= settings.DETECTION_CONFIDENCE:
                best_detection = detection
                best_frame_pil = pil_image
                best_confidence = detection.confidence
                current_phase = "liveness"

                await ws_send(
                    websocket,
                    phase="detection",
                    message=f"Detected: {detection.class_name}",
                    detected_category=detection.class_name,
                    confidence=round(detection.confidence, 2),
                )
            else:
                await ws_send(
                    websocket,
                    phase="detection",
                    message="No item detected. Hold it closer to the camera.",
                )

        # ─── Phase 2: Liveness Check ─────────────────────────
        await ws_send(
            websocket,
            phase="liveness",
            message="Item detected! Now slowly rotate it to prove it's a real, physical item.",
            liveness_progress=liveness_tracker.progress,
        )

        while current_phase == "liveness":
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                frame_b64 = data.get("frame", "")
            except (json.JSONDecodeError, AttributeError):
                frame_b64 = raw

            if not frame_b64:
                continue

            try:
                numpy_frame, pil_image = decode_base64_frame(frame_b64)
            except Exception:
                continue

            detection = yolo_service.detect_any_object(numpy_frame)
            if not detection:
                await ws_send(
                    websocket,
                    phase="liveness",
                    message="Lost sight of the item. Keep it in frame while rotating.",
                    liveness_progress=liveness_tracker.progress,
                )
                continue

            # Track movement
            is_live = liveness_tracker.update(detection)

            # Keep the clearest frame for CLIP matching
            if detection.confidence > best_confidence:
                best_confidence = detection.confidence
                best_frame_pil = pil_image
                best_detection = detection

            if is_live:
                current_phase = "matching"
                await ws_send(
                    websocket,
                    phase="liveness",
                    message="Liveness confirmed! Preparing to match against your listing...",
                    liveness_progress=liveness_tracker.progress,
                )
            else:
                await ws_send(
                    websocket,
                    phase="liveness",
                    message="Keep rotating slowly...",
                    liveness_progress=liveness_tracker.progress,
                )

        # ─── Phase 3: CLIP Similarity Matching ───────────────
        await ws_send(
            websocket,
            phase="matching",
            message="Comparing your item against the listing photos...",
        )

        # Load reference images
        reference_images = []
        for url in reference_urls:
            img = load_image_from_url(url)
            if img:
                reference_images.append(img)

        # If no reference images could be loaded, use a degraded check
        if not reference_images and best_frame_pil:
            # No references available — pass with a note
            similarity_score = 0.0
            await ws_send(
                websocket,
                phase="matching",
                message="No listing images available for comparison. Verification based on detection only.",
            )
        elif best_frame_pil:
            similarity_score = clip_service.compare_to_references(best_frame_pil, reference_images)
        else:
            similarity_score = 0.0

        # ─── Phase 4: Result ─────────────────────────────────
        now = datetime.now(timezone.utc)
        is_verified = similarity_score >= settings.SIMILARITY_THRESHOLD

        # Generate cryptographic hash
        v_hash = generate_verification_hash(
            user_id=str(user.id),
            product_id=str(product.id),
            timestamp=now.isoformat(),
            similarity_score=similarity_score,
        )

        # Log the verification attempt
        crud_verification.create_verification_log(
            db=db,
            product_id=product.id,
            seller_id=user.id,
            similarity_score=similarity_score,
            detected_category=best_detection.class_name if best_detection else "unknown",
            liveness_passed=True,
            verification_hash=v_hash,
            is_successful=is_verified,
        )

        # If verified, update the product
        if is_verified:
            crud_product.mark_product_verified(
                db=db,
                product_id=product.id,
                verification_hash=v_hash,
                similarity_score=similarity_score,
            )

        await ws_send(
            websocket,
            phase="complete",
            message="Verification complete!" if is_verified else "Verification failed. The item doesn't match the listing photos closely enough.",
            verified=is_verified,
            similarity_score=round(similarity_score, 4),
            verification_hash=v_hash if is_verified else None,
            detected_category=best_detection.class_name if best_detection else None,
            confidence=round(best_confidence, 2),
        )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected during verification for product {product_id}")
    except Exception as e:
        logger.error(f"Verification error for product {product_id}: {e}", exc_info=True)
        try:
            await ws_send(websocket, phase="error", message=f"Verification failed: {str(e)}")
        except Exception:
            pass
    finally:
        db.close()
        try:
            await websocket.close()
        except Exception:
            pass
