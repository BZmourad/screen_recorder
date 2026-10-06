"""Central logging configuration.

Reads `.env` at import time to decide whether logging is enabled, the level,
and whether to print to the console. If logging is disabled, a no-op handler
is installed so `logging.getLogger(...).info(...)` calls remain harmless.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

# Load .env from the project root (parent of this file)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "screen_recorder.log")

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-25s | %(message)s"
_DATE_FORMAT = "%H:%M:%S"

_configured = False


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_level(name: str, default: int) -> int:
    val = os.getenv(name)
    if not val:
        return default
    level = getattr(logging, val.strip().upper(), None)
    return level if isinstance(level, int) else default


def setup_logging() -> None:
    """Configure the root logger according to .env settings."""
    global _configured
    if _configured:
        return

    root = logging.getLogger()

    if not _env_bool("LOGGING_ENABLED", True):
        # Disable logging entirely
        root.addHandler(logging.NullHandler())
        root.setLevel(logging.CRITICAL + 1)
        _configured = True
        return

    level = _env_level("LOG_LEVEL", logging.INFO)
    root.setLevel(level)
    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    if _env_bool("LOG_TO_CONSOLE", True):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(level)
        root.addHandler(console)

    # File handler (rotating)
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root.addHandler(file_handler)

    # Tame noisy third-party loggers
    for noisy in ("PIL", "matplotlib", "numba"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True
    logging.getLogger(__name__).info("Logging enabled → %s", LOG_FILE)


def get_log_file() -> str:
    return LOG_FILE