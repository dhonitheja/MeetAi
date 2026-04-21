"""Tests for backend rate limiting keying and static limit configuration."""

from unittest.mock import MagicMock

from backend.middleware.rate_limiter import LIMITS, get_rate_limit_key, limiter


def make_request(user_id=None, client_host="1.2.3.4"):
    req = MagicMock()
    req.state.user_id = user_id
    req.client.host = client_host
    req.headers = {}
    return req


def test_uses_user_id_when_available():
    req = make_request(user_id="user_abc123")
    key = get_rate_limit_key(req)
    assert key == "user_abc123"


def test_falls_back_to_ip_when_no_user():
    req = make_request(user_id=None, client_host="1.2.3.4")
    key = get_rate_limit_key(req)
    assert key == "1.2.3.4"


def test_all_limit_strings_parseable():
    import re

    pattern = re.compile(r"^\d+/(second|minute|hour|day)$")
    for name, limit in LIMITS.items():
        assert pattern.match(limit), f"Invalid limit format for {name}: {limit}"


def test_limiter_uses_custom_key_function():
    req = make_request(user_id="user_xyz")
    key = limiter._key_func(req)
    assert key == "user_xyz"

