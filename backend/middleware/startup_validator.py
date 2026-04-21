import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EnvVar:
    name: str
    required: bool = True
    description: str = ""


# All environment variables required by MeetAI
# Server fails immediately at startup if any REQUIRED var is missing
REQUIRED_ENV_VARS: list[EnvVar] = [
    # Encryption (Sprints 2-5)
    EnvVar("PERSONA_MACHINE_ID", True, "Machine-specific encryption key component"),
    EnvVar("PERSONA_USER_SALT", True, "User-specific encryption key component"),
    # LLM providers (Sprint 1)
    EnvVar("GEMINI_API_KEY", True, "Google Gemini API key"),
    EnvVar("OPENAI_API_KEY", False, "OpenAI API key (optional if using Gemini only)"),
    EnvVar("ANTHROPIC_API_KEY", False, "Anthropic Claude API key (optional)"),
    # Recall.ai (Sprint 4)
    EnvVar("RECALL_API_KEY", True, "Recall.ai bot API key"),
    EnvVar("RECALL_WEBHOOK_SECRET", True, "Recall.ai webhook HMAC secret"),
    EnvVar("RECALL_WEBHOOK_URL", False, "Public URL for Recall.ai webhook delivery"),
    # Stripe (Sprint 6)
    EnvVar("STRIPE_SECRET_KEY", True, "Stripe secret API key"),
    EnvVar("STRIPE_WEBHOOK_SECRET", True, "Stripe webhook signing secret"),
    EnvVar("STRIPE_PRO_PRICE_ID", True, "Stripe price ID for Pro tier"),
    EnvVar("STRIPE_TEAM_PRICE_ID", True, "Stripe price ID for Team tier"),
    # App config
    EnvVar("APP_BASE_URL", True, "Public base URL for Stripe redirect"),
    EnvVar("LOG_LEVEL", False, "Application logging level (for example: INFO, WARNING, ERROR)"),
]


def validate_environment() -> None:
    """
    Validate all required environment variables are present.
    Raises EnvironmentError with full list of missing vars if any are absent.
    Call this at server startup BEFORE any other initialization.

    Logs WARNING for optional missing vars.
    Raises EnvironmentError for required missing vars - server must not start.
    """
    missing_required = []
    missing_optional = []

    for var in REQUIRED_ENV_VARS:
        value = os.environ.get(var.name, "")
        if not value:
            if var.required:
                missing_required.append(var)
            else:
                missing_optional.append(var)

    # Log optional missing vars as warnings
    for var in missing_optional:
        logger.warning(
            "optional_env_var_missing",
            extra={"var": var.name, "description": var.description},
        )

    # Fail hard on missing required vars
    if missing_required:
        lines = [f"  - {v.name}: {v.description}" for v in missing_required]
        msg = (
            "Server startup failed - missing required environment variables:\n"
            + "\n".join(lines)
        )
        raise EnvironmentError(msg)

    logger.info(
        "environment_validated",
        extra={"required_ok": len(REQUIRED_ENV_VARS) - len(missing_optional)},
    )


def validate_startup() -> None:
    """
    Validate all required environment variables are present.
    Required for Sprint 6 security audit:
    - PERSONA_MACHINE_ID
    - PERSONA_USER_SALT
    - STRIPE_SECRET_KEY
    - STRIPE_WEBHOOK_SECRET
    """
    validate_environment()


# Alias for compliance with automated audit scripts
# validate_startup = validate_environment


def validate_stripe_keys() -> None:
    """
    Additional Stripe key format validation.
    Stripe secret keys start with 'sk_' - reject obviously wrong values.
    Stripe webhook secrets start with 'whsec_'.
    """
    sk = os.environ.get("STRIPE_SECRET_KEY", "")
    ws = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    if sk and not sk.startswith(("sk_live_", "sk_test_")):
        raise EnvironmentError(
            "STRIPE_SECRET_KEY format invalid - must start with 'sk_live_' or 'sk_test_'"
        )
    if ws and not ws.startswith("whsec_"):
        raise EnvironmentError(
            "STRIPE_WEBHOOK_SECRET format invalid - must start with 'whsec_'"
        )
