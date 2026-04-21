import os
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import face as face_module
from backend.routers.face import face_router

os.environ["PERSONA_MACHINE_ID"] = "test-machine"
os.environ["PERSONA_USER_SALT"] = "test-salt-1234"


class _DummyEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._target_face = None

    def set_target_face(self, image_bytes: bytes) -> bool:
        return False

    def set_target_from_embedding(self, embedding):
        self._target_face = object()

    def clear_target(self) -> None:
        self._target_face = None


def _build_test_client(tmp_dir: Path) -> TestClient:
    face_module._engine = _DummyEngine()
    # Redirect profile storage to an isolated tmp dir for deterministic tests.
    import backend.face.face_profile_manager as profile_mod

    profile_mod.PROFILES_DIR = tmp_dir
    app = FastAPI()
    app.include_router(face_router)
    return TestClient(app)


def test_face_status_returns_200(tmp_path: Path):
    client = _build_test_client(tmp_path)
    res = client.get("/face/status")
    assert res.status_code == 200
    data = res.json()
    assert "active" in data
    assert "engine_loaded" in data


def test_list_profiles_returns_list(tmp_path: Path):
    client = _build_test_client(tmp_path)
    res = client.get("/face/profiles")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_upload_invalid_mime_rejected(tmp_path: Path):
    client = _build_test_client(tmp_path)
    res = client.post(
        "/face/upload?name=test",
        files=[("files", ("test.pdf", b"fake pdf content", "application/pdf"))],
    )
    assert res.status_code == 400


def test_upload_oversized_rejected(tmp_path: Path):
    client = _build_test_client(tmp_path)
    big = b"\xff\xd8\xff" + b"x" * (5 * 1024 * 1024 + 1)
    res = client.post(
        "/face/upload?name=test",
        files=[("files", ("big.jpg", big, "image/jpeg"))],
    )
    assert res.status_code == 413


def test_invalid_profile_id_rejected(tmp_path: Path):
    client = _build_test_client(tmp_path)
    res = client.delete("/face/profiles/not-a-valid-id")
    assert res.status_code == 400

    res = client.post("/face/activate/not-a-valid-id")
    assert res.status_code == 400


def test_delete_nonexistent_returns_404(tmp_path: Path):
    client = _build_test_client(tmp_path)
    res = client.delete("/face/profiles/abcdef1234567890")
    assert res.status_code == 404
