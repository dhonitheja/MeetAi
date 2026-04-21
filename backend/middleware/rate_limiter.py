"""Global request rate limiting helpers for MeetAI backend."""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def get_rate_limit_key(request: Request) -> str:
    """
    Build the rate-limit key for a request.

    Priority:
    1. `request.state.user_id` when present (authenticated user scope)
    2. Direct client IP via `get_remote_address(request)`

    This explicitly avoids using client-provided `X-Forwarded-For`.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return str(user_id)
    return get_remote_address(request)


# Global limiter instance imported by routers and server bootstrap.
limiter = Limiter(key_func=get_rate_limit_key)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Return a safe structured 429 response.

    The response intentionally avoids leaking internal stack traces or debug data.
    """
    logger.warning(
        "rate_limit_exceeded",
        extra={
            "path": request.url.path,
            "key": get_rate_limit_key(request),
            "limit": str(exc.detail),
        },
    )
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": "Too many requests. Please slow down.",
            "retry_after": "60",
        },
    )


LIMITS: dict[str, str] = {
    "upload": "5/minute",
    "synthesize": "20/minute",
    "face": "30/minute",
    "rag": "30/minute",
    "meeting": "10/minute",
    "billing": "10/minute",
    "default": "60/minute",
}

