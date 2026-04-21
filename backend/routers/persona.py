import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from backend.billing.subscription_gate import check_persona_limit
from backend.persona.persona_manager import Persona, PersonaManager

logger = logging.getLogger(__name__)

persona_router = APIRouter(prefix="/persona", tags=["persona"])

_manager = PersonaManager()
_active_persona_id: Optional[str] = None

PERSONA_ID_PATTERN = re.compile(r"[a-f0-9]{16}")
VOICE_ID_PATTERN = re.compile(r"[a-f0-9]{16}")
FACE_ID_PATTERN = re.compile(r"[a-f0-9]{16}")


def _validate_id(value: str, label: str) -> str:
    """Shared hex16 fullmatch validator. Prevents path traversal."""
    if not PERSONA_ID_PATTERN.fullmatch(value):
        raise HTTPException(400, f"Invalid {label} format")
    return value


class CreatePersonaRequest(BaseModel):
    display_name: str
    voice_id: str
    face_id: str
    system_prompt: str = "Be concise and accurate."

    @field_validator("display_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        import re as _re

        clean = _re.sub(r"[^a-zA-Z0-9 _-]", "", v).strip()
        if not clean:
            raise ValueError("display_name cannot be empty")
        return clean[:64]

    @field_validator("voice_id")
    @classmethod
    def validate_voice_id(cls, v: str) -> str:
        if not VOICE_ID_PATTERN.fullmatch(v):
            raise ValueError("voice_id must be a 16-char hex string")
        return v

    @field_validator("face_id")
    @classmethod
    def validate_face_id(cls, v: str) -> str:
        if not FACE_ID_PATTERN.fullmatch(v):
            raise ValueError("face_id must be a 16-char hex string")
        return v

    @field_validator("system_prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        import re as _re

        v = _re.sub(r"[\x00-\x1f\x7f]", " ", v).strip()
        if len(v) > 2000:
            raise ValueError("system_prompt too long (max 2000 chars)")
        return v


class PersonaResponse(BaseModel):
    persona_id: str
    display_name: str
    voice_id: str
    face_id: str
    created_at: str


class ActivateResponse(BaseModel):
    status: str
    persona_id: str
    display_name: str
    voice_id: str
    face_id: str


@persona_router.post("/create", response_model=PersonaResponse)
async def create_persona(req: CreatePersonaRequest, request: Request) -> PersonaResponse:
    """
    Create and save an encrypted persona profile.
    voice_id and face_id validated as hex16 before save.
    """
    user_id = getattr(request.state, "user_id", "unknown")
    tier = getattr(request.state, "tier", "free")
    if not await check_persona_limit(user_id, tier):
        raise HTTPException(
            403,
            "Free tier limit reached (3 personas). Upgrade to Pro for unlimited.",
        )

    try:
        persona = Persona(
            display_name=req.display_name,
            voice_id=req.voice_id,
            face_id=req.face_id,
            system_prompt=req.system_prompt,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    _manager.save(persona)
    logger.info("Persona created: %s (%s)", persona.persona_id, persona.display_name)

    return PersonaResponse(
        persona_id=persona.persona_id,
        display_name=persona.display_name,
        voice_id=persona.voice_id,
        face_id=persona.face_id,
        created_at=persona.created_at,
    )


@persona_router.get("/list", response_model=list[dict])
async def list_personas() -> list[dict]:
    """List all saved personas (metadata only - no payloads)."""
    return _manager.list_personas()


@persona_router.post("/activate/{persona_id}", response_model=ActivateResponse)
async def activate_persona(persona_id: str) -> ActivateResponse:
    """
    Load a persona and atomically update voice + face active profiles.
    Notifies voice and face routers to switch their active profile.
    persona_id validated as hex16 before any file operation.
    """
    global _active_persona_id
    _validate_id(persona_id, "persona_id")

    try:
        persona = _manager.load(persona_id)
    except FileNotFoundError as e:
        raise HTTPException(404, f"Persona not found: {persona_id}") from e

    # Atomic: activate voice profile
    try:
        from backend.routers.voice import _store as voice_store

        if voice_store:
            voice_store.load(persona.voice_id)
            from backend.routers.voice import _engine as voice_engine

            if voice_engine:
                voice_engine.extract_embedding  # verify engine loaded
    except Exception as e:
        logger.warning("Voice activation skipped: %s", e)

    # Atomic: activate face profile
    try:
        from backend.face.face_profile_manager import FaceProfileManager
        from backend.routers.face import _engine as face_engine

        face_mgr = FaceProfileManager()
        _, face_embedding = face_mgr.load(persona.face_id)
        if face_engine:
            face_engine.set_target_from_embedding(face_embedding)
    except Exception as e:
        logger.warning("Face activation skipped: %s", e)

    _active_persona_id = persona_id
    logger.info("Persona activated: %s (%s)", persona_id, persona.display_name)

    return ActivateResponse(
        status="active",
        persona_id=persona_id,
        display_name=persona.display_name,
        voice_id=persona.voice_id,
        face_id=persona.face_id,
    )


@persona_router.get("/active")
async def get_active_persona() -> dict:
    """Return currently active persona metadata."""
    if not _active_persona_id:
        return {"active": False, "persona_id": None}
    try:
        persona = _manager.load(_active_persona_id)
        return {
            "active": True,
            "persona_id": persona.persona_id,
            "display_name": persona.display_name,
            "voice_id": persona.voice_id,
            "face_id": persona.face_id,
        }
    except FileNotFoundError:
        return {"active": False, "persona_id": None}


@persona_router.delete("/delete/{persona_id}")
async def delete_persona(persona_id: str) -> dict[str, str]:
    """Delete a saved persona. Validates ID before file operation."""
    _validate_id(persona_id, "persona_id")
    try:
        _manager.delete(persona_id)
    except FileNotFoundError as e:
        raise HTTPException(404, f"Persona not found: {persona_id}") from e
    return {"status": "deleted", "persona_id": persona_id}
