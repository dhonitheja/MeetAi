from __future__ import annotations

import hashlib
import re
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from backend.face.face_profile_manager import FaceProfile, FaceProfileManager
from backend.face.face_swap_engine import FaceSwapEngine

face_router = APIRouter(prefix="/face", tags=["face"])

_engine: Optional[FaceSwapEngine] = None
_manager = FaceProfileManager()

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_IMAGES = 5


def get_engine() -> FaceSwapEngine:
    """Return loaded FaceSwapEngine or raise service-unavailable."""
    if _engine is None:
        raise HTTPException(503, "Face engine not loaded. Check server startup logs.")
    return _engine


def _validate_profile_id(profile_id: str) -> str:
    """Reject anything that is not a 16-char hex string. Prevents path traversal."""
    if not re.fullmatch(r"[a-f0-9]{16}", profile_id):
        raise HTTPException(400, "Invalid profile_id format")
    return profile_id


def _validate_magic_bytes(data: bytes, mime_type: str) -> bool:
    """Check file magic bytes match declared MIME type. Prevents disguised uploads."""
    if mime_type == "image/jpeg" and data[:3] == b"\xff\xd8\xff":
        return True
    if mime_type == "image/png" and data[:4] == b"\x89PNG":
        return True
    if mime_type == "image/webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return False


class ProfileResponse(BaseModel):
    profile_id: str
    name: str
    source_image_hash: str
    created_at: str

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, value: str) -> str:
        """Ensure response profile_id matches expected hex16 format."""
        if not re.fullmatch(r"[a-f0-9]{16}", value):
            raise ValueError("Invalid profile_id format")
        return value


class StatusResponse(BaseModel):
    active: bool
    profile_id: Optional[str]
    engine_loaded: bool


@face_router.post("/upload", response_model=ProfileResponse)
async def upload_face(
    name: str = Query(..., min_length=1, max_length=100),
    files: list[UploadFile] = File(...),
    engine: FaceSwapEngine = Depends(get_engine),
):
    """
    Accept 1-5 reference photos. Extract face embedding. Save encrypted profile.
    MIME type and magic bytes both validated.
    Photo bytes never written to disk - processed in memory only.
    Returns HTTP 422 if no face detected in any uploaded image.
    """
    if len(files) > MAX_IMAGES:
        raise HTTPException(400, f"Maximum {MAX_IMAGES} images per upload")

    for upload_file in files:
        if upload_file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                400,
                f"File type not allowed: {upload_file.content_type}. Use JPEG, PNG, or WebP.",
            )

    face_detected = False
    last_image_bytes: bytes | None = None

    for upload in files:
        image_bytes = await upload.read(MAX_IMAGE_SIZE + 1)
        if len(image_bytes) > MAX_IMAGE_SIZE:
            raise HTTPException(413, f"Image too large (max 5MB): {upload.filename}")

        content_type = upload.content_type or ""
        if not _validate_magic_bytes(image_bytes, content_type):
            raise HTTPException(
                400,
                f"File content does not match declared type: {upload.filename}",
            )

        try:
            detected = engine.set_target_face(image_bytes)
            if detected:
                face_detected = True
                last_image_bytes = image_bytes
                break
        except ValueError:
            continue

    if not face_detected or last_image_bytes is None:
        raise HTTPException(
            422,
            "No face detected in any uploaded image. Please upload a clear, well-lit photo.",
        )

    source_hash = hashlib.sha256(last_image_bytes).hexdigest()
    profile = FaceProfile(name=name, source_image_hash=source_hash)

    embedding = engine.get_target_embedding()
    if embedding is None:
        raise HTTPException(500, "Failed to extract face embedding")
    _manager.save(profile, embedding)

    return ProfileResponse(
        profile_id=profile.profile_id,
        name=profile.name,
        source_image_hash=source_hash,
        created_at=profile.created_at,
    )


@face_router.post("/activate/{profile_id}")
async def activate_face(
    profile_id: str,
    engine: FaceSwapEngine = Depends(get_engine),
):
    """Load saved face profile and set as active swap target via safe public interface."""
    _validate_profile_id(profile_id)
    try:
        profile, embedding = _manager.load(profile_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Profile {profile_id} not found")

    engine.set_target_from_embedding(embedding)
    return {"status": "active", "profile_id": profile_id, "name": profile.name}


@face_router.post("/deactivate")
async def deactivate_face(engine: FaceSwapEngine = Depends(get_engine)):
    """Clear active face target. Webcam shows real face again."""
    engine.clear_target()
    return {"status": "idle"}


@face_router.get("/profiles", response_model=list[ProfileResponse])
async def list_face_profiles():
    """List all saved face profiles. Embeddings never returned."""
    return _manager.list_profiles()


@face_router.delete("/profiles/{profile_id}")
async def delete_face_profile(profile_id: str):
    """Delete a saved face profile."""
    _validate_profile_id(profile_id)
    try:
        _manager.delete(profile_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Profile {profile_id} not found")
    return {"status": "deleted", "profile_id": profile_id}


@face_router.get("/status", response_model=StatusResponse)
async def face_status():
    """Return current face clone status."""
    active = _engine is not None and _engine._target_face is not None
    return StatusResponse(
        active=active,
        profile_id=None,
        engine_loaded=_engine is not None,
    )
