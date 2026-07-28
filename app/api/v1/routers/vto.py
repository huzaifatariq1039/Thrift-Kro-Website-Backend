from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from app.schemas.vto import VTORequest, VTOResponse
from app.models.user import User
from app.api.deps import get_current_active_user
from gradio_client import Client, handle_file
import tempfile
import shutil
import os
import time
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Hugging Face VTON client (lazy singleton)
# ---------------------------------------------------------------------------
_vton_client = None

def get_vton_client():
    global _vton_client
    if _vton_client is None:
        _vton_client = Client("huzaifa39/thriftkro-vton-engine")
    return _vton_client


# ---------------------------------------------------------------------------
# Existing mock endpoint – preserved for backwards compatibility
# ---------------------------------------------------------------------------
@router.post("/inference", response_model=VTOResponse)
async def run_vto_inference(
    product_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user)
):
    # Mocking VTO model inference processing time
    time.sleep(2)
    
    # Returning a mock output image URL
    mock_result_url = "https://mock-s3-bucket.s3.amazonaws.com/vto-results/mock_result_123.jpg"
    return {"composite_image_url": mock_result_url}


# ---------------------------------------------------------------------------
# Real VTON generation endpoint
# ---------------------------------------------------------------------------
@router.post("/generate")
async def generate_vton(
    person_image: UploadFile = File(...),
    garment_image: UploadFile = File(...),
    category: str = Form(...),
    current_user: User = Depends(get_current_active_user),
):
    """
    Virtual Try-On generation.

    Accepts a person photo and a garment photo, forwards them to the
    Hugging Face Space **huzaifa39/thriftkro-vton-engine**, and streams
    the resulting composite image back to the client.
    """
    temp_person_path: str | None = None
    temp_garment_path: str | None = None

    try:
        # ---- write uploaded files to temp dir ----
        temp_dir = tempfile.mkdtemp()

        person_ext = os.path.splitext(person_image.filename or "img.png")[1] or ".png"
        garment_ext = os.path.splitext(garment_image.filename or "img.png")[1] or ".png"

        temp_person_path = os.path.join(temp_dir, f"person{person_ext}")
        temp_garment_path = os.path.join(temp_dir, f"garment{garment_ext}")

        with open(temp_person_path, "wb") as f:
            shutil.copyfileobj(person_image.file, f)

        with open(temp_garment_path, "wb") as f:
            shutil.copyfileobj(garment_image.file, f)

        # ---- call the Hugging Face Space ----
        client = get_vton_client()
        result = client.predict(
            person_image_path=handle_file(temp_person_path),
            garment_image_path=handle_file(temp_garment_path),
            category=category,
            api_name="/process_vton",
        )

        # `result` is expected to be a local file path to the output image
        if not result or not os.path.isfile(result):
            raise HTTPException(
                status_code=502,
                detail="VTON model did not return a valid image.",
            )

        return FileResponse(
            path=result,
            media_type="image/png",
            filename="vton_result.png",
        )

    except HTTPException:
        raise  # re-raise FastAPI HTTP exceptions as-is
    except Exception as exc:
        logger.exception("VTON generation failed")
        err_str = str(exc).lower()
        if "timeout" in err_str or "time out" in err_str:
            detail_msg = "The AI Engine took too long to respond. Please try again later."
        else:
            detail_msg = f"VTON generation failed: {str(exc)}"
            
        raise HTTPException(
            status_code=500,
            detail=detail_msg,
        )
    finally:
        # ---- cleanup temp upload files ----
        if temp_person_path and os.path.exists(temp_person_path):
            os.remove(temp_person_path)
        if temp_garment_path and os.path.exists(temp_garment_path):
            os.remove(temp_garment_path)
        # remove the temp directory itself (if empty)
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
