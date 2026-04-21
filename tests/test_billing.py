import os

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_placeholder")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_testplaceholder")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_testpro1234567890")
os.environ.setdefault("STRIPE_TEAM_PRICE_ID", "price_testteam1234567890")
os.environ.setdefault("APP_BASE_URL", "http://localhost:3000")

from backend.billing import subscription_store as store_mod
from backend.routers import billing as billing_mod

app = FastAPI()


@app.middleware("http")
async def _inject_test_user(request: Request, call_next):
    request.state.user_id = request.headers.get("X-Test-User-Id")
    return await call_next(request)


app.include_router(billing_mod.billing_router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_subscriptions_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "subscriptions.db")
    billing_mod._store = store_mod.SubscriptionStore()
    yield


def test_checkout_invalid_tier_rejected():
    res = client.post("/billing/checkout", json={"tier": "enterprise", "user_id": "user_12345678"})
    assert res.status_code == 422


def test_checkout_returns_checkout_url(monkeypatch):
    monkeypatch.setattr(
        billing_mod,
        "create_checkout_session",
        lambda user_id, price_id, success_url, cancel_url: "https://checkout.test/session",
    )
    res = client.post("/billing/checkout", json={"tier": "pro", "user_id": "user_12345678"})
    assert res.status_code == 200
    assert res.json()["checkout_url"] == "https://checkout.test/session"


def test_portal_no_customer_record_returns_404():
    res = client.post("/billing/portal", headers={"X-Test-User-Id": "user_12345678"})
    assert res.status_code == 404


def test_portal_returns_portal_url(monkeypatch):
    billing_mod._store.upsert(
        user_id="user_12345678",
        customer_id="cus_1234567890abcdef",
        tier="pro",
        status="active",
    )
    monkeypatch.setattr(
        billing_mod,
        "create_portal_session",
        lambda customer_id, return_url: "https://billing.test/portal",
    )
    res = client.post("/billing/portal", headers={"X-Test-User-Id": "user_12345678"})
    assert res.status_code == 200
    assert res.json()["portal_url"] == "https://billing.test/portal"


def test_portal_requires_authentication():
    res = client.post("/billing/portal")
    assert res.status_code == 401


def test_webhook_missing_signature_rejected_without_processing(monkeypatch):
    called = {"value": False}

    def _fake_construct(payload, sig_header):
        called["value"] = True
        return {}

    monkeypatch.setattr(billing_mod, "construct_event", _fake_construct)

    res = client.post("/billing/webhook", content=b'{"type":"checkout.session.completed"}')
    assert res.status_code == 400
    assert called["value"] is False


def test_webhook_invalid_signature_returns_400(monkeypatch):
    def _raise_signature(payload, sig_header):
        raise billing_mod.stripe.error.SignatureVerificationError("bad", sig_header, payload)

    monkeypatch.setattr(billing_mod, "construct_event", _raise_signature)

    res = client.post(
        "/billing/webhook",
        content=b'{"type":"checkout.session.completed"}',
        headers={"Stripe-Signature": "invalid"},
    )
    assert res.status_code == 400


def test_webhook_checkout_completed_upserts_subscription(monkeypatch):
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "user_12345678",
                "customer": "cus_1234567890abcdef",
                "metadata": {"user_id": "user_12345678"},
            }
        },
    }
    monkeypatch.setattr(billing_mod, "construct_event", lambda payload, sig: event)

    res = client.post(
        "/billing/webhook",
        content=b'{"mock":"payload"}',
        headers={"Stripe-Signature": "valid"},
    )
    assert res.status_code == 200
    assert billing_mod._store.get_tier("user_12345678") == "pro"


def test_webhook_subscription_deleted_downgrades_to_free(monkeypatch):
    billing_mod._store.upsert(
        user_id="user_12345678",
        customer_id="cus_1234567890abcdef",
        tier="pro",
        status="active",
    )
    event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_1234567890abcdef"}},
    }
    monkeypatch.setattr(billing_mod, "construct_event", lambda payload, sig: event)

    res = client.post(
        "/billing/webhook",
        content=b'{"mock":"payload"}',
        headers={"Stripe-Signature": "valid"},
    )
    assert res.status_code == 200
    assert billing_mod._store.get_tier("user_12345678") == "free"


def test_get_tier_unknown_user_defaults_to_free():
    res = client.get("/billing/tier/unknown_user")
    assert res.status_code == 200
    assert res.json()["tier"] == "free"
