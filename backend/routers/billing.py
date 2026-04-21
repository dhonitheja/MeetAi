from __future__ import annotations

import logging
import os
import re
from typing import Optional

try:
    import stripe  # type: ignore[import-not-found]
except ImportError:
    from backend.billing.stripe_client import stripe  # type: ignore[assignment]

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, field_validator

from backend.billing.stripe_client import (
    construct_event,
    create_checkout_session,
    create_portal_session,
)
from backend.billing.constants import CUSTOMER_ID_PATTERN, USER_ID_PATTERN
from backend.billing.subscription_store import SubscriptionStore

logger = logging.getLogger(__name__)

billing_router = APIRouter(prefix="/billing", tags=["billing"])
_store = SubscriptionStore()

TIER_PRICE_MAP = {
    "pro": lambda: os.environ.get("STRIPE_PRO_PRICE_ID", ""),
    "team": lambda: os.environ.get("STRIPE_TEAM_PRICE_ID", ""),
}


class CheckoutRequest(BaseModel):
    tier: str
    user_id: str

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        if v not in ("pro", "team"):
            raise ValueError("tier must be 'pro' or 'team'")
        return v

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not USER_ID_PATTERN.fullmatch(v):
            raise ValueError("Invalid user_id format")
        return v


@billing_router.post("/checkout")
async def create_checkout(req: CheckoutRequest):
    """
    Create Stripe Checkout session for subscription upgrade.
    """
    price_id = TIER_PRICE_MAP[req.tier]()
    if not price_id:
        raise HTTPException(500, f"Price ID for tier '{req.tier}' not configured")

    base_url = os.environ.get("APP_BASE_URL", "http://localhost:3000")
    try:
        url = create_checkout_session(
            user_id=req.user_id,
            price_id=price_id,
            success_url=f"{base_url}/billing/success",
            cancel_url=f"{base_url}/billing/cancel",
        )
    except Exception as exc:
        logger.error("checkout_failed", extra={"error": str(exc)})
        raise HTTPException(502, "Failed to create checkout session") from exc

    return {"checkout_url": url}


@billing_router.post("/portal")
async def customer_portal(request: Request):
    """
    Create Stripe customer portal session.

    user_id is read from request.state (auth middleware), never query params.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Not authenticated")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", user_id):
        raise HTTPException(400, "Invalid user session")

    record = _store.get_by_user_id(user_id)
    if not record or not record.get("customer_id"):
        raise HTTPException(404, "No billing account found for this user")
    customer_id = str(record["customer_id"])
    if not CUSTOMER_ID_PATTERN.fullmatch(customer_id):
        raise HTTPException(400, "Invalid customer_id format")

    base_url = os.environ.get("APP_BASE_URL", "http://localhost:3000")
    try:
        url = create_portal_session(
            customer_id=customer_id,
            return_url=f"{base_url}/billing",
        )
    except Exception as exc:
        logger.error("portal_failed", extra={"error": str(exc)})
        raise HTTPException(502, "Failed to create portal session") from exc

    return {"portal_url": url}


@billing_router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
):
    """
    Handle Stripe webhook events.

    Signature verification uses raw bytes before any payload parsing.
    """
    payload = await request.body()

    if not stripe_signature:
        logger.warning("webhook_missing_signature")
        raise HTTPException(400, "Missing Stripe-Signature header")

    try:
        event = construct_event(payload, stripe_signature)
    except stripe.error.SignatureVerificationError as exc:
        logger.warning("webhook_invalid_signature")
        raise HTTPException(400, "Invalid webhook signature") from exc
    except EnvironmentError as exc:
        logger.error("webhook_config_error", extra={"error": str(exc)})
        raise HTTPException(500, "Webhook configuration error") from exc

    event_type = event["type"]
    data = event["data"]["object"]

    try:
        if event_type == "checkout.session.completed":
            user_id = data.get("client_reference_id") or data.get("metadata", {}).get("user_id")
            customer_id = data.get("customer")
            if user_id and customer_id:
                customer_id_str = str(customer_id)
                if not CUSTOMER_ID_PATTERN.fullmatch(customer_id_str):
                    logger.warning("webhook_invalid_customer_id", extra={"customer_id": customer_id_str})
                    return {"status": "ok"}
                _store.upsert(str(user_id), customer_id_str, tier="pro", status="active")
                logger.info("subscription_activated", extra={"user_id": user_id})

        elif event_type == "customer.subscription.updated":
            customer_id = data.get("customer")
            status = data.get("status", "active")
            if customer_id:
                record = _store.get_by_customer_id(str(customer_id))
                if record:
                    tier = str(record.get("tier", "free"))
                    _store.upsert(str(record["user_id"]), str(customer_id), tier=tier, status=str(status))

        elif event_type == "customer.subscription.deleted":
            customer_id = data.get("customer")
            if customer_id:
                record = _store.get_by_customer_id(str(customer_id))
                if record:
                    _store.upsert(
                        str(record["user_id"]),
                        str(customer_id),
                        tier="free",
                        status="cancelled",
                    )
                    logger.info("subscription_cancelled", extra={"customer_id": customer_id})
    except Exception as exc:
        logger.error(
            "webhook_processing_error",
            extra={"event": event_type, "error": str(exc)},
        )
        # Return 200 to avoid retry storms on internal failures.

    return {"status": "ok"}


@billing_router.get("/tier/{user_id}")
async def get_user_tier(user_id: str):
    """Return current subscription tier for a user."""
    if not USER_ID_PATTERN.fullmatch(user_id):
        raise HTTPException(400, "Invalid user_id format")
    try:
        tier = _store.get_tier(user_id)
    except RuntimeError as exc:
        raise HTTPException(503, "Subscription service unavailable") from exc
    return {"user_id": user_id, "tier": tier}
