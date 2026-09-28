"""
logger.py — Application-wide structlog configuration.

Call `configure_logging()` once at startup (in main.py) to initialise the
pipeline.  Afterwards, obtain a bound logger anywhere with:

    import structlog
    log = structlog.get_logger()
    log.info("something happened", key="value")

Output format
-------------
* Development  : colourful, human-readable console output (KeyValueRenderer).
* Production   : one JSON object per line (JSONRenderer) — ready for log
                 aggregation tools such as Datadog, Loki, or CloudWatch.
"""
import logging
import sys

import structlog


def configure_logging(json_logs: bool = False) -> None:
    """
    Wire structlog into the standard-library logging system so that
    third-party libraries (uvicorn, SQLAlchemy, etc.) also emit
    structured records.

    Args:
        json_logs: Set True in production to emit newline-delimited JSON.
                   Defaults to False (pretty console output for development).
    """
    # Shared processors run on every log event regardless of renderer
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,       # inject bound context vars (e.g. correlation_id)
        structlog.stdlib.add_logger_name,              # add "logger" field
        structlog.stdlib.add_log_level,                # add "level" field
        structlog.processors.TimeStamper(fmt="iso"),   # ISO-8601 timestamp
        structlog.processors.StackInfoRenderer(),      # render stack_info if present
    ]

    if json_logs:
        # Production: machine-readable JSON
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: colourful key=value lines
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors
        + [
            # Bridge to stdlib so uvicorn/3rd-party logs pass through structlog
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure the stdlib formatter that structlog hands off to
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processor=renderer,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)
