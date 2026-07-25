import logging
import structlog
from structlog.typing import Processor

from app.core.config import Settings


def setup_logging(settings: Settings):
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
    ]

    renderer: Processor
    if settings.DEBUG:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        logger_factory=structlog.PrintLoggerFactory(),
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )
