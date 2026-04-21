import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.billing.subscription_store import SubscriptionStore

logger = logging.getLogger(__name__)

# Endpoints that require Pro or higher — Free tier denied
PRO_REQUIRED_PATHS = {
    "/face/upload",
    "/face/activate",
    "/face/deactivate",
    "/meeting/join",
    "/meeting/status",
    "/meeting/summarize",
}

# Endpoints that require Team tier
TEAM_REQUIRED_PATHS: set[str] = set()  # reserved for future use

TIER_RANK = {"free": 0, "pro": 1, "team": 2}
FREE_TIER_PERSONA_LIMIT = 3
PERSONA_LIMIT_PATH = "/persona/create"


async def check_persona_limit(user_id: str, tier: str) -> bool:
    """
    Free tier: max 3 persona profiles.
    Fails CLOSED if DB unavailable.
    """
    if tier != "free":
        return True  # Pro/Team: unlimited
    try:
        from backend.persona.persona_manager import PersonaManager

        mgr = PersonaManager()
        count = len(mgr.list_personas())
        return count < FREE_TIER_PERSONA_LIMIT
    except Exception as exc:
        logger.error(
            "persona_limit_check_error",
            extra={"user_id": user_id, "error": str(exc)},
        )
        return False  # fail CLOSED - deny if DB error


class SubscriptionGateMiddleware(BaseHTTPMiddleware):
    """
    Enforces subscription tier limits on protected endpoints.

    FAIL CLOSED: If the subscription DB is unavailable or raises any
    exception, access to paid features is DENIED rather than allowed.
    This prevents DB outages from silently granting free users paid access.

    Tier is read from server-side SubscriptionStore ONLY.
    Client-supplied headers like X-Subscription-Tier are NEVER trusted.
    """

    def __init__(self, app, store: SubscriptionStore | None = None):
        super().__init__(app)
        self._store = store or SubscriptionStore()

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        normalized_path = path.rstrip("/") or "/"

        # Check if path requires Pro
        requires_pro = any(normalized_path.startswith(p) for p in PRO_REQUIRED_PATHS)
        requires_team = any(normalized_path.startswith(p) for p in TEAM_REQUIRED_PATHS)
        requires_persona_limit = (
            request.method.upper() == "POST" and normalized_path == PERSONA_LIMIT_PATH
        )

        if not requires_pro and not requires_team and not requires_persona_limit:
            return await call_next(request)

        # Get user_id from request state (set by auth middleware upstream)
        # Never read from client-supplied headers
        user_id = getattr(request.state, "user_id", None)

        if not user_id:
            # No authenticated user — deny access to paid features
            return JSONResponse(
                status_code=401,
                content={
                    "error": "authentication_required",
                    "detail": "Authentication required for this feature",
                },
            )

        # Read tier from server-side DB only — fail closed on any error
        try:
            tier = self._store.get_tier(user_id)
        except RuntimeError as e:
            # DB unavailable — DENY access (fail closed)
            logger.error(
                "subscription_gate_db_error",
                extra={"user_id": user_id, "path": path, "error": str(e)},
            )
            return JSONResponse(
                status_code=503,
                content={
                    "error": "service_unavailable",
                    "detail": "Subscription service temporarily unavailable",
                },
            )
        except Exception as e:
            # Any unexpected error — DENY access (fail closed)
            logger.error(
                "subscription_gate_unexpected_error",
                extra={"user_id": user_id, "path": path, "error": str(e)},
            )
            return JSONResponse(
                status_code=503,
                content={
                    "error": "service_unavailable",
                    "detail": "Unable to verify subscription",
                },
            )

        # Check tier meets requirement
        user_rank = TIER_RANK.get(tier, 0)

        if requires_team and user_rank < TIER_RANK["team"]:
            return JSONResponse(
                status_code=402,
                content={
                    "error": "subscription_required",
                    "detail": "Team subscription required",
                    "required_tier": "team",
                    "current_tier": tier,
                },
            )

        if requires_pro and user_rank < TIER_RANK["pro"]:
            return JSONResponse(
                status_code=402,
                content={
                    "error": "subscription_required",
                    "detail": "Pro subscription required",
                    "required_tier": "pro",
                    "current_tier": tier,
                },
            )

        if requires_persona_limit:
            can_create = await check_persona_limit(user_id=user_id, tier=tier)
            if not can_create:
                return JSONResponse(
                    status_code=402,
                    content={
                        "error": "persona_limit_reached",
                        "detail": "Free tier allows up to 3 personas. Upgrade to Pro.",
                        "required_tier": "pro",
                        "current_tier": tier,
                        "limit": FREE_TIER_PERSONA_LIMIT,
                    },
                )

        return await call_next(request)


# Alias for compliance with automated audit scripts
SubscriptionGate = SubscriptionGateMiddleware
