from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import sys
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

assert torch.__version__ >= "2.0", (
    f"torch >= 2.0 required. Current: {torch.__version__}. "
    "Run: pip install torch>=2.0"
)

PROFILES_DIR: Path = Path("./data/voice_profiles")


@dataclass
class VoiceProfile:
    name: str
    embedding_bytes: bytes
    language: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    profile_id: str = ""

    def __post_init__(self) -> None:
        if not self.profile_id:
            raw_id: bytes = f"{self.name}{self.created_at}".encode("utf-8")
            self.profile_id = hashlib.sha256(raw_id).hexdigest()[:16]


class VoiceProfileStore:
    """
    Saves/loads VoiceProfile objects to disk as encrypted JSON.

    KEY DERIVATION (important - read carefully):
    - Key = PBKDF2HMAC(password=machine_id + user_salt, salt=stored_salt, iterations=480000)
    - machine_id: read from PERSONA_MACHINE_ID env var (set during install)
    - user_salt: read from PERSONA_USER_SALT env var (16 random bytes, hex-encoded)
    - stored_salt: random 16 bytes generated per-profile, stored in profile JSON
    - Raw WAV audio is NEVER stored - embedding tensor only
    - Embedding is serialized via torch.save() to BytesIO, then encrypted
    """

    def _derive_key(self, stored_salt: bytes) -> bytes:
        machine_id: str = os.environ.get("PERSONA_MACHINE_ID", "")
        user_salt: str = os.environ.get("PERSONA_USER_SALT", "")
        if not machine_id or not user_salt:
            raise EnvironmentError(
                "PERSONA_MACHINE_ID and PERSONA_USER_SALT must be set in .env"
            )
        password: bytes = (machine_id + user_salt).encode("utf-8")
        kdf: PBKDF2HMAC = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=stored_salt,
            iterations=480000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password))

    def save(self, profile: VoiceProfile, embedding: torch.Tensor) -> Path:
        """Encrypt and save profile + embedding. Returns saved file path."""
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)

        buffer: io.BytesIO = io.BytesIO()
        torch.save(embedding.detach().cpu(), buffer)
        embedding_raw: bytes = buffer.getvalue()

        stored_salt: bytes = os.urandom(16)
        key: bytes = self._derive_key(stored_salt)
        fernet: Fernet = Fernet(key)
        encrypted: bytes = fernet.encrypt(embedding_raw)

        profile.embedding_bytes = encrypted
        payload: dict[str, str] = {
            "profile_id": profile.profile_id,
            "name": profile.name,
            "language": profile.language,
            "created_at": profile.created_at,
            "salt": base64.b64encode(stored_salt).decode("utf-8"),
            "embedding": base64.b64encode(encrypted).decode("utf-8"),
        }

        out_path: Path = PROFILES_DIR / f"{profile.profile_id}.json"
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return out_path

    def load(self, profile_id: str) -> tuple[VoiceProfile, torch.Tensor]:
        """Load and decrypt profile. Returns (VoiceProfile, embedding tensor)."""
        path: Path = PROFILES_DIR / f"{profile_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Profile {profile_id} not found")

        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        stored_salt: bytes = base64.b64decode(str(data["salt"]))
        key: bytes = self._derive_key(stored_salt)
        fernet: Fernet = Fernet(key)
        encrypted: bytes = base64.b64decode(str(data["embedding"]))
        embedding_raw: bytes = fernet.decrypt(encrypted)

        # PATCHED — safe, no fallback
        embedding = torch.load(io.BytesIO(embedding_raw), weights_only=True)

        if isinstance(embedding, torch.Tensor):
            pass
        elif isinstance(embedding, np.ndarray):
            embedding = torch.from_numpy(embedding)
        else:
            embedding = torch.as_tensor(embedding)

        profile: VoiceProfile = VoiceProfile(
            name=str(data["name"]),
            language=str(data["language"]),
            created_at=str(data["created_at"]),
            profile_id=str(data["profile_id"]),
            embedding_bytes=b"",
        )
        return profile, embedding

    def list_profiles(self) -> list[dict[str, str]]:
        """Return list of profile metadata (no embeddings)."""
        if not PROFILES_DIR.exists():
            return []

        profiles: list[dict[str, str]] = []
        for profile_path in PROFILES_DIR.glob("*.json"):
            data: dict[str, str] = json.loads(profile_path.read_text(encoding="utf-8"))
            metadata: dict[str, str] = {k: v for k, v in data.items() if k != "embedding"}
            profiles.append(metadata)
        return profiles

    def delete(self, profile_id: str) -> None:
        path: Path = PROFILES_DIR / f"{profile_id}.json"
        if path.exists():
            path.unlink()
