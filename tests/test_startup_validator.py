import pytest

from backend.middleware.startup_validator import validate_environment, validate_stripe_keys


def _set_required_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONA_MACHINE_ID", "machine-test")
    monkeypatch.setenv("PERSONA_USER_SALT", "salt-test")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("RECALL_API_KEY", "recall-test-key")
    monkeypatch.setenv("RECALL_WEBHOOK_SECRET", "recall-webhook-secret")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_validformat")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_validformat")
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro_test")
    monkeypatch.setenv("STRIPE_TEAM_PRICE_ID", "price_team_test")
    monkeypatch.setenv("APP_BASE_URL", "https://example.test")


def test_missing_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_baseline(monkeypatch)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    with pytest.raises(EnvironmentError) as exc_info:
        validate_environment()
    assert "STRIPE_SECRET_KEY" in str(exc_info.value)


def test_invalid_stripe_key_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "not_a_real_key")
    with pytest.raises(EnvironmentError):
        validate_stripe_keys()


def test_invalid_webhook_secret_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_validformat")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "notawebhooksecret")
    with pytest.raises(EnvironmentError):
        validate_stripe_keys()


def test_valid_keys_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_abc123")
    validate_stripe_keys()  # must not raise
