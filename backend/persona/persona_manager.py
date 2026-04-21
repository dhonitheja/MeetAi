from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PERSONAS_DIR = Path("./data/personas")
HEX16_PATTERN = re.compile(r"[a-f0-9]{16}")


@dataclass
class Persona:
    display_name: str
    voice_id: str
    face_id: str
    system_prompt: str = "Be concise and accurate."
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    persona_id: str = ""

    def __post_init__(self) -> None:
        if not self.display_name.strip():
            raise ValueError("display_name cannot be empty")
        if not HEX16_PATTERN.fullmatch(self.voice_id):
            raise ValueError("voice_id must be a 16-char hex string")
        if not HEX16_PATTERN.fullmatch(self.face_id):
            raise ValueError("face_id must be a 16-char hex string")
        if len(self.system_prompt) > 2000:
            raise ValueError("system_prompt too long (max 2000 chars)")

        if not self.persona_id:
            seed = (
                f"{self.display_name}{self.voice_id}{self.face_id}{self.created_at}"
            ).encode("utf-8")
            self.persona_id = hashlib.sha256(seed).hexdigest()[:16]
        if not HEX16_PATTERN.fullmatch(self.persona_id):
            raise ValueError("persona_id must be a 16-char hex string")


class PersonaManager:
    """
    Stores persona metadata as encrypted payload files keyed by persona_id.
    """

    def _validate_id(self, persona_id: str) -> str:
        if not HEX16_PATTERN.fullmatch(persona_id):
            raise ValueError(f"Invalid persona_id: {persona_id!r}")
        return persona_id

    def _derive_key(self, stored_salt: bytes) -> bytes:
        machine_id = os.environ.get("PERSONA_MACHINE_ID", "")
        user_salt = os.environ.get("PERSONA_USER_SALT", "")
        if not machine_id or not user_salt:
            raise EnvironmentError(
                "PERSONA_MACHINE_ID and PERSONA_USER_SALT must be set in environment."
            )
        password = (machine_id + user_salt).encode("utf-8")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=stored_salt,
            iterations=480000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password))

    def _path_for(self, persona_id: str) -> Path:
        validated = self._validate_id(persona_id)
        return PERSONAS_DIR / f"{validated}.json"

    def save(self, persona: Persona) -> Path:
        """
        Encrypt and persist a persona profile.
        """
        self._validate_id(persona.persona_id)
        PERSONAS_DIR.mkdir(parents=True, exist_ok=True)

        stored_salt = os.urandom(16)
        key = self._derive_key(stored_salt)
        fernet = Fernet(key)

        plaintext_payload = {
            "persona_id": persona.persona_id,
            "display_name": persona.display_name,
            "voice_id": persona.voice_id,
            "face_id": persona.face_id,
            "system_prompt": persona.system_prompt,
            "created_at": persona.created_at,
        }
        encrypted = fernet.encrypt(
            json.dumps(plaintext_payload, separators=(",", ":")).encode("utf-8")
        )

        out_data = {
            "persona_id": persona.persona_id,
            "display_name": persona.display_name,
            "voice_id": persona.voice_id,
            "face_id": persona.face_id,
            "created_at": persona.created_at,
            "salt": base64.b64encode(stored_salt).decode("utf-8"),
            "ciphertext": base64.b64encode(encrypted).decode("utf-8"),
        }

        out_path = self._path_for(persona.persona_id)
        out_path.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
        return out_path

    def load(self, persona_id: str) -> Persona:
        """
        Load and decrypt a persona profile.
        """
        path = self._path_for(persona_id)
        if not path.exists():
            raise FileNotFoundError(f"Persona not found: {persona_id}")

        envelope: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        stored_salt = base64.b64decode(str(envelope["salt"]))
        encrypted = base64.b64decode(str(envelope["ciphertext"]))

        key = self._derive_key(stored_salt)
        fernet = Fernet(key)
        payload: dict[str, Any] = json.loads(fernet.decrypt(encrypted).decode("utf-8"))

        return Persona(
            persona_id=str(payload["persona_id"]),
            display_name=str(payload["display_name"]),
            voice_id=str(payload["voice_id"]),
            face_id=str(payload["face_id"]),
            system_prompt=str(payload["system_prompt"]),
            created_at=str(payload["created_at"]),
        )

    def list_personas(self) -> list[dict[str, str]]:
        """
        Return non-sensitive persona metadata only.
        """
        if not PERSONAS_DIR.exists():
            return []

        personas: list[dict[str, str]] = []
        for persona_file in PERSONAS_DIR.glob("*.json"):
            try:
                envelope = json.loads(persona_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue

            persona_id = str(envelope.get("persona_id", ""))
            if not HEX16_PATTERN.fullmatch(persona_id):
                continue

            personas.append(
                {
                    "persona_id": persona_id,
                    "display_name": str(envelope.get("display_name", "")),
                    "voice_id": str(envelope.get("voice_id", "")),
                    "face_id": str(envelope.get("face_id", "")),
                    "created_at": str(envelope.get("created_at", "")),
                }
            )
        return personas

    def delete(self, persona_id: str) -> None:
        """
        Delete a saved persona profile file.
        """
        path = self._path_for(persona_id)
        if not path.exists():
            raise FileNotFoundError(f"Persona not found: {persona_id}")
        path.unlink()
