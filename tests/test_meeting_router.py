import hashlib
import hmac
import json
import os

from fastapi.testclient import TestClient

os.environ.setdefault("RECALL_API_KEY", "test-key")
os.environ.setdefault("RECALL_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("PERSONA_MACHINE_ID", "test")
os.environ.setdefault("PERSONA_USER_SALT", "test-salt")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
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

# ... (rest of signatures helpers)


def make_sig(payload: bytes) -> str:
    secret = os.environ.get("RECALL_WEBHOOK_SECRET", "")
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_webhook_missing_signature_returns_401():
    res = client.post(
        "/meeting/webhook",
        content=b'{"event":"transcript.data"}',
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 401


def test_webhook_invalid_signature_returns_401():
    payload = b'{"event":"transcript.data"}'
    res = client.post(
        "/meeting/webhook",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Recall-Signature": "invalidsignature",
        },
    )
    assert res.status_code == 401


def test_webhook_valid_signature_accepted():
    payload = json.dumps(
        {
            "event": "transcript.data",
            "data": {
                "bot_id": "bot12345678",
                "transcript": {
                    "speaker": "Alice",
                    "words": [{"text": "Hello"}],
                },
            },
        }
    ).encode()
    sig = make_sig(payload)
    res = client.post(
        "/meeting/webhook",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Recall-Signature": sig,
        },
    )
    assert res.status_code == 200


def test_join_invalid_url_rejected():
    res = client.post(
        "/meeting/join",
        json={"url": "https://evil.com/steal", "bot_name": "Bot"},
        headers={"X-User-ID": "test-pro-user"},
    )
    assert res.status_code == 422


def test_status_invalid_bot_id_rejected():
    res = client.get(
        "/meeting/status/../etc/passwd",
        headers={"X-User-ID": "test-pro-user"},
    )
    assert res.status_code in (400, 404)


def test_active_bots_returns_dict():
    res = client.get("/meeting/active")
    assert res.status_code == 200
    assert "bots" in res.json()
