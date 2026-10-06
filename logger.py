"""Central logging configuration.

Reads `.env` at import time to decide whether logging is enabled, the level,
and whether to print to the console. If logging is disabled, a no-op handler
is installed so `logging.getLogger(...).info(...)` calls remain harmless.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv


# --------------------------------------------------------------------------- #
# .env loading
# --------------------------------------------------------------------------- #
def _candidate_env_paths():
    """List of .env locations, by priority."""
    paths = []
    if getattr(sys, "frozen", False):
        # Running as PyInstaller .exe
        paths.append(os.path.join(os.path.dirname(sys.executable), ".env"))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.append(os.path.join(meipass, ".env"))
    else:
        # Running from source
        paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    return paths


for _p in _candidate_env_paths():
    if os.path.isfile(_p):
        load_dotenv(dotenv_path=_p)
        break


# --------------------------------------------------------------------------- #
# Logging paths
# --------------------------------------------------------------------------- #
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "screen_recorder.log")

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-25s | %(message)s"
_DATE_FORMAT = "%H:%M:%S"

_configured = False


# --------------------------------------------------------------------------- #
# .env helpers
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
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
    """Return the absolute path to the current log file."""
    return LOG_FILE


def get_countdown_seconds() -> int:
    """Return the countdown duration from .env, clamped to [0, 10]."""
    try:
        value = int(os.getenv("COUNTDOWN_SECONDS", "3"))
    except (TypeError, ValueError):
        value = 3
    return max(0, min(value, 10))

def get_test_env() -> bool:
    """Return True if TEST_ENV is enabled in .env.

    When True, the recorder bakes a visible "TEST" watermark into the video.
    Accepts: 1 / true / yes / on (case-insensitive). Anything else → False.
    """
    return _env_bool("TEST_ENV", False)