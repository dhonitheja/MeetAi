import os
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

os.environ.setdefault("PERSONA_MACHINE_ID", "test")
os.environ.setdefault("PERSONA_USER_SALT", "test-salt")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_x")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_x")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_x")
os.environ.setdefault("STRIPE_TEAM_PRICE_ID", "price_y")
os.environ.setdefault("APP_BASE_URL", "http://localhost:3000")

from backend.billing.subscription_gate import SubscriptionGateMiddleware


class _HeaderAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        user_id = request.headers.get("X-User-Id")
        if user_id:
            request.state.user_id = user_id
        return await call_next(request)


def make_test_app(tier: str = "free", db_raises: bool = False):
    app = FastAPI()
    mock_store = MagicMock()

    if db_raises:
        mock_store.get_tier.side_effect = RuntimeError("DB down")
    else:
        mock_store.get_tier.return_value = tier

    # Add gate first, then auth middleware so auth runs upstream.
    app.add_middleware(SubscriptionGateMiddleware, store=mock_store)
    app.add_middleware(_HeaderAuthMiddleware)

    @app.get("/face/activate/test")
    async def face():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/persona/create")
    async def persona_create():
        return {"ok": True}

    return app, mock_store


def test_protected_path_requires_authentication():
    app, _ = make_test_app(tier="pro")
    client = TestClient(app)
    res = client.get("/face/activate/test")
    assert res.status_code == 401
    assert res.json()["error"] == "authentication_required"


def test_free_user_blocked_from_pro_feature():
    app, _ = make_test_app(tier="free")
    client = TestClient(app)
    res = client.get("/face/activate/test", headers={"X-User-Id": "user1"})
    assert res.status_code == 402
    assert res.json()["required_tier"] == "pro"


def test_pro_user_allowed_on_pro_feature():
    app, _ = make_test_app(tier="pro")
    client = TestClient(app)
    res = client.get("/face/activate/test", headers={"X-User-Id": "user1"})
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_db_error_denies_access_fail_closed():
    app, _ = make_test_app(db_raises=True)
    client = TestClient(app)
    res = client.get("/face/activate/test", headers={"X-User-Id": "user1"})
    assert res.status_code == 503
    assert res.json()["error"] == "service_unavailable"


def test_free_path_not_gated():
    app, mock_store = make_test_app(tier="free")
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    mock_store.get_tier.assert_not_called()


def test_client_subscription_header_is_ignored():
    app, _ = make_test_app(tier="free")
    client = TestClient(app)
    res = client.get(
        "/face/activate/test",
        headers={"X-User-Id": "user1", "X-Subscription-Tier": "team"},
    )
    assert res.status_code == 402
    assert res.json()["current_tier"] == "free"


def test_persona_create_requires_authentication():
    app, _ = make_test_app(tier="free")
    client = TestClient(app)
    res = client.post("/persona/create")
    assert res.status_code == 401
    assert res.json()["error"] == "authentication_required"


def test_free_user_blocked_when_persona_limit_reached():
    app, _ = make_test_app(tier="free")
    client = TestClient(app)

    with patch(
        "backend.billing.subscription_gate.check_persona_limit",
        new=AsyncMock(return_value=False),
    ):
        res = client.post("/persona/create", headers={"X-User-Id": "user1"})

    assert res.status_code == 402
    assert res.json()["error"] == "persona_limit_reached"
    assert res.json()["limit"] == 3


def test_free_user_allowed_when_persona_limit_available():
    app, _ = make_test_app(tier="free")
    client = TestClient(app)
    mock_check = AsyncMock(return_value=True)

    with patch("backend.billing.subscription_gate.check_persona_limit", new=mock_check):
        res = client.post("/persona/create", headers={"X-User-Id": "user1"})

    assert res.status_code == 200
    assert res.json() == {"ok": True}
    mock_check.assert_awaited_once_with(user_id="user1", tier="free")
