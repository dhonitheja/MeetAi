import os
import pytest
import numpy as np
from backend.face.face_profile_manager import FaceProfileManager, FaceProfile

# Set required env vars for tests
os.environ["PERSONA_MACHINE_ID"] = "test-machine-id"
os.environ["PERSONA_USER_SALT"] = "test-user-salt-1234"


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.face.face_profile_manager.PROFILES_DIR", tmp_path
    )
    manager = FaceProfileManager()
    embedding = np.random.rand(512).astype(np.float32)
    profile = FaceProfile(name="test", source_image_hash="abc123")
    manager.save(profile, embedding)
    loaded_profile, loaded_embedding = manager.load(profile.profile_id)
    assert loaded_profile.name == "test"
    assert np.allclose(embedding, loaded_embedding)


def test_path_traversal_rejected():
    manager = FaceProfileManager()
    with pytest.raises(ValueError):
        manager.load("../../etc/passwd")
    with pytest.raises(ValueError):
        manager.delete("../server.py")


def test_missing_env_vars_raises(monkeypatch):
    monkeypatch.delenv("PERSONA_MACHINE_ID", raising=False)
    monkeypatch.delenv("PERSONA_USER_SALT", raising=False)
    manager = FaceProfileManager()
    with pytest.raises(EnvironmentError):
        manager._derive_key(b"fakesalt1234abcd")


def test_allow_pickle_false(tmp_path, monkeypatch):
    """np.load must use allow_pickle=False — no arbitrary code execution."""
    import inspect
    import backend.face.face_profile_manager as mod
    source = inspect.getsource(mod.FaceProfileManager.load)
    assert "allow_pickle=False" in source, \
        "CRITICAL: np.load() must use allow_pickle=False"
