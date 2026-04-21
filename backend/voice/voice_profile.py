import os
import json
import uuid
import base64
from typing import Optional, List, Dict
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet

class VoiceProfileManager:
    """
    Handles encrypted persistence of voice profiles.
    Uses PBKDF2 for key derivation based on machine ID and a local salt.
    """
    
    def __init__(self, storage_path: str = "./profiles/"):
        self.storage_path = storage_path
        self.salt_path = os.path.join(storage_path, "user_salt.bin")
        self.profiles_path = os.path.join(storage_path, "vault.enc")
        self._key = None
        
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)

    def _get_machine_id(self) -> str:
        """Fetch a stable machine-specific identifier."""
        # Using uuid.getnode() as a basic stable hardware ID
        return str(uuid.getnode())

    def _get_or_create_salt(self) -> bytes:
        """Retrieves user_salt or generates a new one if missing."""
        if os.path.exists(self.salt_path):
            with open(self.salt_path, "rb") as f:
                return f.read()
        else:
            salt = os.urandom(16)
            with open(self.salt_path, "wb") as f:
                f.write(salt)
            return salt

    def _derive_key(self):
        """
        Derives a Fernet key using PBKDF2(machine_id + user_salt).
        Follows the 480,000 iterations spec for high security.
        """
        if self._key:
            return self._key
            
        machine_id = self._get_machine_id().encode()
        salt = self._get_or_create_salt()
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        
        derived = kdf.derive(machine_id)
        self._key = base64.urlsafe_b64encode(derived)
        return self._key

    def save_profile(self, name: str, embedding: bytes, language: str = "en"):
        """Encrypts and saves a new voice profile to the local vault."""
        key = self._derive_key()
        fernet = Fernet(key)
        
        # Load existing
        profiles = self.list_profiles()
        
        new_profile = {
            "id": str(uuid.uuid4()),
            "name": name,
            "embedding": base64.b64encode(embedding).decode('utf-8'),
            "language": language,
            "created_at": str(np_datetime_now()) if 'np_datetime_now' in globals() else "2026-04-21"
        }
        
        profiles.append(new_profile)
        
        # Encrypt whole vault
        data = json.dumps(profiles).encode()
        encrypted_data = fernet.encrypt(data)
        
        with open(self.profiles_path, "wb") as f:
            f.write(encrypted_data)
            
        return new_profile["id"]

    def list_profiles(self) -> List[Dict]:
        """Decrypts and lists all saved voice profiles."""
        if not os.path.exists(self.profiles_path):
            return []
            
        key = self._derive_key()
        fernet = Fernet(key)
        
        with open(self.profiles_path, "rb") as f:
            encrypted_data = f.read()
            
        try:
            decrypted_data = fernet.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception:
            # Most likely incorrect key due to machine change or salt loss
            print("[VoiceProfile] Error: Decryption failed. Key mismatch?")
            return []

    def get_embedding(self, profile_id: str) -> Optional[bytes]:
        """Retrieves the raw embedding bytes for a specific profile."""
        profiles = self.list_profiles()
        for p in profiles:
            if p["id"] == profile_id:
                return base64.b64decode(p["embedding"])
        return None

    def delete_profile(self, profile_id: str):
        """Removes a profile from the vault."""
        profiles = self.list_profiles()
        profiles = [p for p in profiles if p["id"] != profile_id]
        
        key = self._derive_key()
        fernet = Fernet(key)
        
        data = json.dumps(profiles).encode()
        encrypted_data = fernet.encrypt(data)
        
        with open(self.profiles_path, "wb") as f:
            f.write(encrypted_data)
