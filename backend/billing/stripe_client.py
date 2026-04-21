from __future__ import annotations

import os
import re
from types import SimpleNamespace
from typing import Any

try:
    import stripe  # type: ignore[import-not-found]
except ImportError:
    class _SignatureVerificationError(Exception):
        """Fallback signature verification error when stripe SDK is absent."""

    class _CheckoutSession:
        @staticmethod
        def create(**_: Any) -> Any:
            raise RuntimeError("stripe package not installed")

    class _BillingPortalSession:
        @staticmethod
        def create(**_: Any) -> Any:
            raise RuntimeError("stripe package not installed")

    class _Webhook:
        @staticmethod
        def construct_event(_: bytes, __: str, ___: str) -> Any:
            raise _SignatureVerificationError("stripe package not installed")

    stripe = SimpleNamespace(  # type: ignore[assignment]
        api_key="",
        checkout=SimpleNamespace(Session=_CheckoutSession),
        billing_portal=SimpleNamespace(Session=_BillingPortalSession),
        Webhook=_Webhook,
        error=SimpleNamespace(SignatureVerificationError=_SignatureVerificationError),
        Event=dict,
    )

PRICE_ID_PATTERN = re.compile(r"^price_[a-zA-Z0-9]{14,}$")
CUSTOMER_ID_PATTERN = re.compile(r"^cus_[a-zA-Z0-9]{14,}$")


def get_stripe() -> Any:
    """
    Initialize Stripe with secret key from environment.

    Raises EnvironmentError if STRIPE_SECRET_KEY is missing.
    """
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        raise EnvironmentError("STRIPE_SECRET_KEY not set in environment")
    stripe.api_key = key
    return stripe


def create_checkout_session(
    user_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """
    Create a Stripe Checkout session and return the hosted URL.

    price_id is validated before any API call.
    """
    if not PRICE_ID_PATTERN.fullmatch(price_id):
        raise ValueError(f"Invalid price_id format: {price_id!r}")

    base_url = os.environ.get("APP_BASE_URL", "")
    if not base_url:
        raise EnvironmentError("APP_BASE_URL not set in environment")

    s = get_stripe()
    session = s.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=user_id,
        metadata={"user_id": user_id},
    )
    return str(session.url)


def create_portal_session(customer_id: str, return_url: str) -> str:
    """
    Create a Stripe Customer Portal session and return the hosted URL.
    """
    if not CUSTOMER_ID_PATTERN.fullmatch(customer_id):
        raise ValueError(f"Invalid customer_id format: {customer_id!r}")

    s = get_stripe()
    session = s.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return str(session.url)


def construct_event(payload: bytes, sig_header: str) -> Any:
    """
    Validate and construct a Stripe webhook event.

    This must receive raw request bytes before any JSON parsing.
    """
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise EnvironmentError("STRIPE_WEBHOOK_SECRET not set in environment")

    get_stripe()
    return stripe.Webhook.construct_event(payload, sig_header, secret)
