import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("PERSONA_MACHINE_ID", "test")
os.environ.setdefault("PERSONA_USER_SALT", "test-salt")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("RECALL_API_KEY", "test-recall-key")
os.environ.setdefault("RECALL_WEBHOOK_SECRET", "test-recall-secret")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_abc123")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_abc123")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_pro_test")
os.environ.setdefault("STRIPE_TEAM_PRICE_ID", "price_team_test")
os.environ.setdefault("APP_BASE_URL", "http://localhost:8765")

from server import app

from backend.billing.subscription_store import SubscriptionStore
_store = SubscriptionStore()
_store.upsert("test-pro-user", "cus_test1234567890abcdef", "pro", "active")

client = TestClient(app)


def test_list_personas_returns_list() -> None:
    res = client.get("/persona/list")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_create_invalid_voice_id_rejected() -> None:
    res = client.post(
        "/persona/create",
        json={
            "display_name": "Test",
            "voice_id": "not-hex",
            "face_id": "a1b2c3d4e5f6a1b2",
        },
        headers={"X-User-ID": "test-pro-user"},
    )
    assert res.status_code == 422


def test_create_invalid_face_id_rejected() -> None:
    res = client.post(
        "/persona/create",
        json={
            "display_name": "Test",
            "voice_id": "a1b2c3d4e5f6a1b2",
            "face_id": "../../etc/passwd1",
        },
        headers={"X-User-ID": "test-pro-user"},
    )
    assert res.status_code == 422


def test_activate_path_traversal_rejected() -> None:
    res = client.post("/persona/activate/../../etc/passwd")
    assert res.status_code in (400, 404)


def test_activate_newline_rejected() -> None:
    res = client.post("/persona/activate/a1b2c3d4e5f6a1b2%0A")
    assert res.status_code in (400, 404)


def test_delete_nonexistent_returns_404() -> None:
    res = client.delete("/persona/delete/a1b2c3d4e5f6a1b2")
    assert res.status_code == 404


def test_active_returns_dict() -> None:
    res = client.get("/persona/active")
    assert res.status_code == 200
    assert "active" in res.json()
