import logging
import sys

try:
    import structlog
except ImportError:
    structlog = None


def configure_logging(log_level: str = "INFO") -> None:
    """
    Configure structlog for JSON output to stdout.
    All loggers in the application use this configuration.
    No raw print() statements - all output goes through structlog.
    Call once at server startup before any other initialization.
    """
    if structlog is None:
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.INFO),
            stream=sys.stdout,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        return

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Silence noisy third-party loggers
    for noisy in ["uvicorn.access", "httpx", "chromadb"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)
