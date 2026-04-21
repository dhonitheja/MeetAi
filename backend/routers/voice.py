from __future__ import annotations

import asyncio
import re
from typing import Any, AsyncGenerator

import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from src.voice.voice_clone_engine import VoiceCloneEngine
from src.voice.voice_profile import VoiceProfile, VoiceProfileStore
from src.voice.virtual_mic_router import VirtualMicRouter

voice_router = APIRouter(prefix="/voice", tags=["voice"])

# Module-level singletons (initialized at app startup)
_engine: VoiceCloneEngine | None = None
_store: VoiceProfileStore = VoiceProfileStore()
_router_mic: VirtualMicRouter = VirtualMicRouter()


def get_engine() -> VoiceCloneEngine:
    """Dependency that provides the loaded voice cloning engine."""
    if _engine is None:
        raise HTTPException(status_code=503, detail="Voice engine not loaded")
    return _engine


async def load_voice_engine() -> None:
    """Initialize the shared voice engine singleton at app startup."""
    global _engine
    if _engine is not None:
        return

    engine: VoiceCloneEngine = VoiceCloneEngine()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, engine.load)
    _engine = engine


class UploadVoiceRequest(BaseModel):
    name: str
    language: str = "en"

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, value: str) -> str:
        cleaned: str = value.strip()
        if not cleaned:
            raise ValueError("name cannot be empty")
        if len(cleaned) > 120:
            raise ValueError("name too long (max 120 chars)")
        return cleaned

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        cleaned: str = value.strip()
        if not re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", cleaned):
            raise ValueError("language must be a valid code (e.g., en or en-US)")
        return cleaned


class SynthesizeRequest(BaseModel):
    text: str
    profile_id: str

    @field_validator("text")
    @classmethod
    def sanitize_text(cls, value: str) -> str:
        cleaned: str = re.sub(r"[\x00-\x1f\x7f]", " ", value).strip()
        if len(cleaned) > 2000:
            raise ValueError("text too long (max 2000 chars)")
        if not cleaned:
            raise ValueError("text cannot be empty")
        return cleaned

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, value: str) -> str:
        cleaned: str = value.strip()
        if not re.fullmatch(r"[a-f0-9]{16}", cleaned):
            raise ValueError("invalid profile_id format")
        return cleaned


class ProfileResponse(BaseModel):
    profile_id: str
    name: str
    language: str
    created_at: str


class ProfilePathRequest(BaseModel):
    profile_id: str

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, value: str) -> str:
        cleaned: str = value.strip()
        if not re.fullmatch(r"[a-f0-9]{16}", cleaned):
            raise ValueError("invalid profile_id format")
        return cleaned


@voice_router.post("/upload", response_model=ProfileResponse)
async def upload_voice(
    name: str,
    language: str = "en",
    file: UploadFile = File(...),
    engine: VoiceCloneEngine = Depends(get_engine),
) -> ProfileResponse:
    """
    Accept WAV upload, extract embedding, save encrypted profile.
    Raw audio never written to disk - processed in memory only.
    """
    req: UploadVoiceRequest = UploadVoiceRequest(name=name, language=language)

    if file.content_type not in ("audio/wav", "audio/x-wav", "audio/wave"):
        raise HTTPException(status_code=400, detail="Only WAV files accepted")

    max_size: int = 10 * 1024 * 1024
    wav_data: bytes = await file.read(max_size + 1)
    if len(wav_data) > max_size:
        raise HTTPException(status_code=413, detail="Audio file too large (max 10MB)")

    loop = asyncio.get_running_loop()
    embedding = await loop.run_in_executor(None, engine.extract_embedding, wav_data)

    profile: VoiceProfile = VoiceProfile(
        name=req.name,
        language=req.language,
        embedding_bytes=b"",
    )
    await loop.run_in_executor(None, _store.save, profile, embedding)

    return ProfileResponse(
        profile_id=profile.profile_id,
        name=profile.name,
        language=profile.language,
        created_at=profile.created_at,
    )


@voice_router.post("/synthesize")
async def synthesize(
    req: SynthesizeRequest,
    engine: VoiceCloneEngine = Depends(get_engine),
) -> StreamingResponse:
    """
    Stream synthesized audio in cloned voice.
    Returns audio/raw stream of int16 bytes at 48kHz mono.
    """
    loop = asyncio.get_running_loop()

    try:
        _, embedding = await loop.run_in_executor(None, _store.load, req.profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def audio_stream() -> AsyncGenerator[bytes, None]:
        async for chunk in engine.generate_streaming(req.text, embedding):
            int16_chunk: np.ndarray = (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16)
            yield int16_chunk.tobytes()

    return StreamingResponse(audio_stream(), media_type="audio/raw")


@voice_router.post("/synthesize-to-mic")
async def synthesize_to_mic(
    req: SynthesizeRequest,
    engine: VoiceCloneEngine = Depends(get_engine),
) -> dict[str, str]:
    """
    Synthesize and route directly to virtual microphone device.
    Non-streaming - returns 200 when audio routing completes.
    """
    loop = asyncio.get_running_loop()
    try:
        _, embedding = await loop.run_in_executor(None, _store.load, req.profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    audio_generator = engine.generate_streaming(req.text, embedding)
    await _router_mic.route_audio_stream(audio_generator)
    return {"status": "ok"}


@voice_router.get("/profiles", response_model=list[ProfileResponse])
async def list_profiles() -> list[ProfileResponse]:
    """List profile metadata without exposing encrypted embeddings."""
    loop = asyncio.get_running_loop()
    raw_profiles: list[dict[str, Any]] = await loop.run_in_executor(None, _store.list_profiles)
    return [ProfileResponse.model_validate(profile) for profile in raw_profiles]


@voice_router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str) -> dict[str, str]:
    """Delete a stored voice profile by id."""
    validated: ProfilePathRequest = ProfilePathRequest(profile_id=profile_id)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _store.delete, validated.profile_id)
    return {"status": "deleted"}


@voice_router.get("/devices")
async def list_devices() -> list[dict[str, int | str]]:
    """Debug endpoint - list available audio output devices."""
    return _router_mic.list_output_devices()
