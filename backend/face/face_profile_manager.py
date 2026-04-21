import os
import json
import base64
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet

PROFILES_DIR = Path("./data/face_profiles")


@dataclass
class FaceProfile:
    name: str
    source_image_hash: str   # SHA256 of original photo — dedup only, photo never stored
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    profile_id: str = ""

    def __post_init__(self) -> None:
        """Generate profile_id if one was not supplied."""
        if not self.profile_id:
            self.profile_id = hashlib.sha256(
                f"{self.name}{self.created_at}".encode()
            ).hexdigest()[:16]


class FaceProfileManager:
    """
    Saves and loads FaceProfile objects with encrypted numpy embeddings.

    KEY DERIVATION:
    - password = PERSONA_MACHINE_ID + PERSONA_USER_SALT (env vars, never defaults)
    - salt = os.urandom(16) per profile, stored in JSON
    - PBKDF2HMAC(SHA256, 480000 iterations) -> Fernet key
    - embedding serialized via np.save() to BytesIO, then Fernet-encrypted
    - Original photo NEVER stored — SHA256 hash only for deduplication
    - profile_id validated as hex16 before ANY path construction
    """

    def _validate_profile_id(self, profile_id: str) -> str:
        """Reject anything that is not a 16-char hex string. Prevents path traversal."""
        if not re.fullmatch(r"[a-f0-9]{16}", profile_id):
            raise ValueError(f"Invalid profile_id: {profile_id!r}")
        return profile_id

    def _derive_key(self, stored_salt: bytes) -> bytes:
        """
        Derive a Fernet key using PBKDF2HMAC with machine/user secret inputs.
        """
        machine_id = os.environ.get("PERSONA_MACHINE_ID", "")
        user_salt = os.environ.get("PERSONA_USER_SALT", "")
        if not machine_id or not user_salt:
            raise EnvironmentError(
                "PERSONA_MACHINE_ID and PERSONA_USER_SALT must be set in .env"
            )
        password = (machine_id + user_salt).encode()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=stored_salt,
            iterations=480000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password))

    def save(self, profile: FaceProfile, embedding: np.ndarray) -> Path:
        """
        Encrypt and save face profile + embedding.
        embedding: numpy array from InsightFace — encrypted before any disk write.
        Returns path to saved JSON file.
        """
        self._validate_profile_id(profile.profile_id)
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)

        buf = io.BytesIO()
        np.save(buf, embedding)
        embedding_raw = buf.getvalue()

        stored_salt = os.urandom(16)
        key = self._derive_key(stored_salt)
        fernet = Fernet(key)
        encrypted = fernet.encrypt(embedding_raw)

        data = {
            "profile_id": profile.profile_id,
            "name": profile.name,
            "source_image_hash": profile.source_image_hash,
            "created_at": profile.created_at,
            "salt": base64.b64encode(stored_salt).decode(),
            "embedding": base64.b64encode(encrypted).decode(),
        }

        out_path = PROFILES_DIR / f"{profile.profile_id}.json"
        out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return out_path

    def load(self, profile_id: str) -> tuple[FaceProfile, np.ndarray]:
        """
        Load and decrypt face profile.
        Validates profile_id before path construction.
        Returns (FaceProfile, numpy embedding array).
        """
        self._validate_profile_id(profile_id)
        path = PROFILES_DIR / f"{profile_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Face profile not found: {profile_id}")

        data: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
        stored_salt = base64.b64decode(data["salt"])
        key = self._derive_key(stored_salt)
        fernet = Fernet(key)
        embedding_raw = fernet.decrypt(base64.b64decode(data["embedding"]))

        embedding = np.load(io.BytesIO(embedding_raw), allow_pickle=False)

        profile = FaceProfile(
            name=data["name"],
            source_image_hash=data["source_image_hash"],
            created_at=data["created_at"],
            profile_id=data["profile_id"],
        )
        return profile, embedding

    def list_profiles(self) -> list[dict]:
        """
        Return profile metadata — embeddings and salts never included.
        """
        if not PROFILES_DIR.exists():
            return []
        result: list[dict] = []
        for p in PROFILES_DIR.glob("*.json"):
            data = json.loads(p.read_text(encoding="utf-8"))
            result.append({
                k: v for k, v in data.items()
                if k not in ("embedding", "salt")
            })
        return result

    def delete(self, profile_id: str) -> None:
        """
        Delete profile file. Validates profile_id before path construction.
        """
        self._validate_profile_id(profile_id)
        path = PROFILES_DIR / f"{profile_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Face profile not found: {profile_id}")
        path.unlink()
