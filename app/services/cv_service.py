"""
AI Services for Object Verification Pipeline.

Contains:
- YOLOService: Real-time object detection using YOLOv8
- CLIPService: Visual similarity matching using OpenCLIP
- LivenessTracker: Anti-spoofing via bounding box motion analysis
- generate_verification_hash: Tamper-proof verification receipts
"""

import hashlib
import io
import logging
import math
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── YOLO Category Mapping ────────────────────────────────────────────
# Maps YOLO COCO class names to Thrift Kro product categories
YOLO_TO_CATEGORY = {
    # Clothing
    "person": None,  # Ignore people in frame
    "tie": "Accessories",
    "handbag": "Bags",
    "backpack": "Bags",
    "suitcase": "Bags",
    "umbrella": "Accessories",
    # Footwear (COCO doesn't have shoe classes, but custom models might)
    "shoe": "Shoes",
    "sneaker": "Shoes",
    "boot": "Shoes",
    # Generic — YOLO COCO doesn't have clothing classes out of the box,
    # so for clothing items we rely on CLIP similarity as the primary signal.
    # The YOLO step serves to confirm a physical object is present in frame.
}

# Categories that YOLO can reasonably detect from COCO classes
GENERIC_OBJECT_CLASSES = {
    "handbag", "backpack", "suitcase", "tie", "umbrella",
    "bottle", "cup", "book", "cell phone", "laptop",
    "keyboard", "mouse", "remote", "scissors", "clock",
}


# ─── Detection Result ─────────────────────────────────────────────────

class Detection:
    """A single detected object from YOLO."""
    def __init__(self, class_name: str, confidence: float, bbox: Tuple[float, float, float, float]):
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox  # (x1, y1, x2, y2)

    @property
    def center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.bbox
        return (x2 - x1) * (y2 - y1)

    @property
    def aspect_ratio(self) -> float:
        x1, y1, x2, y2 = self.bbox
        w = x2 - x1
        h = y2 - y1
        return w / h if h > 0 else 0


# ─── YOLO Service (Singleton) ─────────────────────────────────────────

class YOLOService:
    """
    Lazy-loading singleton for YOLOv8 inference.
    Detects objects in camera frames and returns bounding boxes with class labels.
    """
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_model(self):
        if self._model is None:
            try:
                from ultralytics import YOLO
                logger.info(f"Loading YOLO model: {settings.YOLO_MODEL}")
                self._model = YOLO(settings.YOLO_MODEL)
                logger.info("YOLO model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load YOLO model: {e}")
                raise

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run object detection on a single frame.
        
        Args:
            frame: numpy array (H, W, 3) in BGR or RGB format
            
        Returns:
            List of Detection objects with class names, confidences, and bboxes
        """
        self._load_model()

        results = self._model(frame, conf=settings.DETECTION_CONFIDENCE, verbose=False)
        detections = []

        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0])
                class_name = self._model.names[cls_id]
                confidence = float(box.conf[0])
                bbox = tuple(box.xyxy[0].tolist())
                detections.append(Detection(class_name, confidence, bbox))

        return detections

    def detect_any_object(self, frame: np.ndarray) -> Optional[Detection]:
        """
        Detect any significant object in the frame (excluding people).
        For clothing items that COCO YOLO can't classify directly,
        we just need to confirm a physical object exists.
        
        Returns the highest-confidence non-person detection, or None.
        """
        detections = self.detect(frame)
        # Filter out people and low-confidence detections
        valid = [d for d in detections if d.class_name != "person" and d.confidence >= settings.DETECTION_CONFIDENCE]
        if valid:
            return max(valid, key=lambda d: d.confidence)
        # If no non-person object, check if there's any large bounding box
        # (clothing held up by a person will be detected as part of the person bbox)
        person_detections = [d for d in detections if d.class_name == "person"]
        if person_detections:
            # Return a synthetic detection — the person is likely holding the item
            largest = max(person_detections, key=lambda d: d.area)
            return Detection("object_in_frame", largest.confidence * 0.8, largest.bbox)
        return None


# ─── CLIP Service (Singleton) ─────────────────────────────────────────

class CLIPService:
    """
    Lazy-loading singleton for CLIP visual similarity.
    Embeds images into a shared vector space and computes cosine similarity.
    """
    _instance = None
    _model = None
    _preprocess = None
    _tokenizer = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_model(self):
        if self._model is None:
            try:
                import open_clip
                import torch

                self._device = "cuda" if torch.cuda.is_available() else "cpu"
                logger.info(f"Loading CLIP model: {settings.CLIP_MODEL} on {self._device}")

                self._model, _, self._preprocess = open_clip.create_model_and_transforms(
                    settings.CLIP_MODEL,
                    pretrained=settings.CLIP_PRETRAINED,
                )
                self._model = self._model.to(self._device)
                self._model.eval()
                self._tokenizer = open_clip.get_tokenizer(settings.CLIP_MODEL)
                logger.info("CLIP model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load CLIP model: {e}")
                raise

    def get_embedding(self, image: Image.Image) -> np.ndarray:
        """
        Extract a normalized feature vector from a PIL image.
        
        Returns:
            numpy array of shape (512,) — the CLIP embedding
        """
        import torch

        self._load_model()
        image_tensor = self._preprocess(image).unsqueeze(0).to(self._device)

        with torch.no_grad():
            features = self._model.encode_image(image_tensor)
            features = features / features.norm(dim=-1, keepdim=True)

        return features.cpu().numpy().flatten()

    def compute_similarity(self, embedding_a: np.ndarray, embedding_b: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings.
        
        Returns:
            Float in range [0, 1] where 1 = identical
        """
        dot = np.dot(embedding_a, embedding_b)
        norm_a = np.linalg.norm(embedding_a)
        norm_b = np.linalg.norm(embedding_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        similarity = dot / (norm_a * norm_b)
        # Clamp to [0, 1] — negative similarity means unrelated
        return float(max(0.0, similarity))

    def compare_to_references(self, live_image: Image.Image, reference_images: List[Image.Image]) -> float:
        """
        Compare a live frame against multiple reference listing photos.
        
        Returns:
            The maximum similarity score across all reference images.
        """
        if not reference_images:
            return 0.0

        live_embedding = self.get_embedding(live_image)
        max_similarity = 0.0

        for ref_img in reference_images:
            ref_embedding = self.get_embedding(ref_img)
            sim = self.compute_similarity(live_embedding, ref_embedding)
            max_similarity = max(max_similarity, sim)

        return max_similarity


# ─── Liveness Tracker (Per-Session, Stateful) ─────────────────────────

class LivenessTracker:
    """
    Tracks bounding box movement across consecutive frames to detect
    if the item is a physical 3D object being rotated (liveness pass)
    or a static 2D image on a screen (liveness fail).
    
    Checks:
    1. Center position shift — item must move in the frame
    2. Aspect ratio change — rotating a 3D object changes its proportions
    3. Area change — depth changes from rotation affect apparent size
    """

    def __init__(self, frames_required: int = None, movement_threshold: float = None):
        self.frames_required = frames_required or settings.LIVENESS_FRAMES_REQUIRED
        self.movement_threshold = movement_threshold or settings.LIVENESS_MOVEMENT_THRESHOLD
        self._history: List[Detection] = []
        self._movement_frames = 0

    @property
    def progress(self) -> str:
        return f"{self._movement_frames}/{self.frames_required}"

    @property
    def is_complete(self) -> bool:
        return self._movement_frames >= self.frames_required

    def update(self, detection: Detection) -> bool:
        """
        Feed a new frame's detection. Returns True when liveness is confirmed.
        
        Compares the current detection's bbox against the previous frame to
        detect 3D movement (centroid shift + aspect ratio change).
        """
        if not self._history:
            self._history.append(detection)
            return False

        prev = self._history[-1]
        self._history.append(detection)

        # Calculate centroid shift
        cx_prev, cy_prev = prev.center
        cx_curr, cy_curr = detection.center
        centroid_shift = math.sqrt((cx_curr - cx_prev) ** 2 + (cy_curr - cy_prev) ** 2)

        # Calculate aspect ratio change (3D rotation changes proportions)
        ar_change = abs(detection.aspect_ratio - prev.aspect_ratio)

        # Calculate area change (depth shift from rotation)
        area_change = abs(detection.area - prev.area) / max(prev.area, 1)

        # A frame counts as "movement" if centroid shifted OR aspect ratio changed
        has_movement = (
            centroid_shift >= self.movement_threshold
            or ar_change >= 0.05  # 5% aspect ratio change
            or area_change >= 0.08  # 8% area change
        )

        if has_movement:
            self._movement_frames += 1

        return self.is_complete

    def reset(self):
        """Reset the tracker for a new attempt."""
        self._history.clear()
        self._movement_frames = 0


# ─── Utility Functions ────────────────────────────────────────────────

def decode_base64_frame(base64_str: str) -> Tuple[np.ndarray, Image.Image]:
    """
    Decode a base64-encoded JPEG frame into both numpy array (for YOLO)
    and PIL Image (for CLIP).
    
    Returns:
        (numpy_frame, pil_image)
    """
    import base64

    # Strip data URL prefix if present
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]

    image_bytes = base64.b64decode(base64_str)
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    numpy_frame = np.array(pil_image)

    return numpy_frame, pil_image


def load_image_from_url(url: str) -> Optional[Image.Image]:
    """Download an image from a URL and return as PIL Image."""
    try:
        import requests
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")
    except Exception as e:
        logger.warning(f"Failed to load image from {url}: {e}")
        return None


def generate_verification_hash(
    user_id: str,
    product_id: str,
    timestamp: str,
    similarity_score: float,
) -> str:
    """
    Generate a SHA-256 hash as tamper-proof receipt of a verification event.
    
    Combines user ID, product ID, timestamp, score, and server secret key
    so the hash cannot be forged without knowing the secret.
    """
    payload = f"{user_id}:{product_id}:{timestamp}:{similarity_score:.4f}:{settings.SECRET_KEY}"
    return hashlib.sha256(payload.encode()).hexdigest()


# ─── Legacy mock function (kept for backward compatibility) ───────────

async def analyze_product_image(image_bytes: bytes):
    """
    Simulates a Computer Vision model analyzing an image.
    Kept for backward compatibility with the POST /ai/verify-product endpoint.
    """
    import random
    import time

    time.sleep(1.5)

    is_authentic = random.choice([True, True, True, False])
    condition_score = random.randint(50, 98) if is_authentic else random.randint(10, 40)
    categories = ["Sneakers", "Jacket", "Hoodie", "T-Shirt", "Jeans", "Bag"]
    detected_category = random.choice(categories)
    possible_flaws = ["minor scuff", "faded color", "small stain", "loose thread", "creasing"]
    detected_flaws = random.sample(possible_flaws, k=random.randint(0, 2)) if condition_score < 90 else []

    return {
        "is_authentic": is_authentic,
        "condition_score": condition_score,
        "detected_category": detected_category,
        "detected_flaws": detected_flaws,
    }
