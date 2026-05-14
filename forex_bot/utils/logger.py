"""
FxBot Logging Module
====================
Provides colored console output and rotating file logging.

Usage::

    from forex_bot.utils.logger import get_logger, setup_logging

    setup_logging(level="INFO", log_file="logs/forex_bot.log")
    log = get_logger(__name__)
    log.info("Bot started")
    log.warning("Low balance warning")
    log.error("Order failed: %s", error_msg)
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional

try:
    import colorlog
    _HAS_COLORLOG = True
except ImportError:
    _HAS_COLORLOG = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_LOG_LEVEL: str = "INFO"
DEFAULT_LOG_FILE: str = "logs/forex_bot.log"
MAX_BYTES: int = 10 * 1024 * 1024   # 10 MB
BACKUP_COUNT: int = 5

LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# colorlog uses %(log_color)s / %(reset)s tokens
COLORED_FORMAT: str = (
    "%(log_color)s%(asctime)s | %(levelname)-8s%(reset)s"
    " | %(cyan)s%(name)-25s%(reset)s"
    " | %(message_log_color)s%(message)s%(reset)s"
)

# Map log levels to terminal colours
LOG_COLORS: dict = {
    "DEBUG":    "white",
    "INFO":     "bold_green",
    "WARNING":  "bold_yellow",
    "ERROR":    "bold_red",
    "CRITICAL": "bold_red,bg_white",
}

SECONDARY_LOG_COLORS: dict = {
    "message": {
        "DEBUG":    "white",
        "INFO":     "green",
        "WARNING":  "yellow",
        "ERROR":    "red",
        "CRITICAL": "bold_red",
    }
}

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

_root_configured: bool = False
_log_file_configured: Optional[str] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    colored: bool = True,
) -> None:
    """
    Configure the root logger with a colored console handler and a
    rotating file handler.

    This function is idempotent: calling it multiple times simply updates
    the logging level and re-uses existing handlers.

    Args:
        level:    Log level string (DEBUG/INFO/WARNING/ERROR/CRITICAL).
                  Falls back to LOG_LEVEL env var, then DEFAULT_LOG_LEVEL.
        log_file: Path to the log file. Falls back to DEFAULT_LOG_FILE.
        colored:  If True and colorlog is available, use colored console output.
    """
    global _root_configured, _log_file_configured

    # --- Resolve level ---
    effective_level_str = (
        level
        or os.environ.get("LOG_LEVEL", "")
        or DEFAULT_LOG_LEVEL
    ).upper()

    numeric_level = getattr(logging, effective_level_str, logging.INFO)

    # --- Resolve file path ---
    effective_log_file = log_file or DEFAULT_LOG_FILE

    # --- Root logger ---
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Avoid adding duplicate handlers on repeated calls
    if not _root_configured:
        root_logger.handlers.clear()
        root_logger.addHandler(_build_console_handler(numeric_level, colored))
        _root_configured = True

    # Avoid adding duplicate file handlers
    if effective_log_file and effective_log_file != _log_file_configured:
        fh = _build_file_handler(effective_log_file, numeric_level)
        root_logger.addHandler(fh)
        _log_file_configured = effective_log_file

    # --- Silence noisy third-party loggers ---
    for noisy in (
        "urllib3", "requests", "oandapyV20", "apscheduler",
        "asyncio", "aiohttp", "websockets",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger.

    If ``setup_logging`` has not been called yet, it is invoked automatically
    with default settings so the logger is always usable.

    Args:
        name: Usually ``__name__`` of the calling module.

    Returns:
        A configured :class:`logging.Logger` instance.
    """
    if not _root_configured:
        setup_logging()
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Handler builders (private)
# ---------------------------------------------------------------------------

def _build_console_handler(
    level: int,
    colored: bool = True,
) -> logging.Handler:
    """Build a StreamHandler writing to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if colored and _HAS_COLORLOG:
        formatter = colorlog.ColoredFormatter(
            fmt=COLORED_FORMAT,
            datefmt=DATE_FORMAT,
            log_colors=LOG_COLORS,
            secondary_log_colors=SECONDARY_LOG_COLORS,
            reset=True,
            style="%",
        )
    else:
        formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    handler.setFormatter(formatter)
    return handler


def _build_file_handler(log_file: str, level: int) -> logging.Handler:
    """Build a RotatingFileHandler, creating parent directories as needed."""
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.RotatingFileHandler(
        filename=str(log_path),
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
    handler.setFormatter(formatter)
    return handler


# ---------------------------------------------------------------------------
# Convenience: module-level logger for internal use
# ---------------------------------------------------------------------------

def _get_internal_logger() -> logging.Logger:
    """Return the logger for this module (used during setup itself)."""
    return logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trade-specific log helpers
# ---------------------------------------------------------------------------

class TradeLogger:
    """
    Thin wrapper around a standard logger that adds structured trade logging.

    Example::

        tlog = TradeLogger(get_logger("trades"))
        tlog.trade_opened("EUR_USD", "BUY", 1.0850, 1.0800, 1.0950, 10000)
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._log = logger

    def trade_opened(
        self,
        pair: str,
        direction: str,
        entry: float,
        sl: float,
        tp: float,
        units: int,
        trade_id: Optional[str] = None,
        strategy: Optional[str] = None,
        score: Optional[float] = None,
    ) -> None:
        tid = f" [#{trade_id}]" if trade_id else ""
        strat = f" via {strategy}" if strategy else ""
        sc = f" score={score:.1f}" if score is not None else ""
        self._log.info(
            "TRADE OPEN%s | %s %s%s%s | entry=%.5f sl=%.5f tp=%.5f units=%d",
            tid, pair, direction, strat, sc, entry, sl, tp, units,
        )

    def trade_closed(
        self,
        pair: str,
        direction: str,
        entry: float,
        close_price: float,
        pnl: float,
        pips: float,
        trade_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        tid = f" [#{trade_id}]" if trade_id else ""
        rsn = f" ({reason})" if reason else ""
        sign = "+" if pnl >= 0 else ""
        self._log.info(
            "TRADE CLOSE%s | %s %s%s | entry=%.5f close=%.5f pnl=%s%.2f USD pips=%s%.1f",
            tid, pair, direction, rsn, entry, close_price, sign, pnl, sign, pips,
        )

    def trade_modified(
        self,
        trade_id: str,
        modification: str,
        old_value: float,
        new_value: float,
    ) -> None:
        self._log.info(
            "TRADE MODIFY [#%s] | %s: %.5f -> %.5f",
            trade_id, modification, old_value, new_value,
        )

    def signal_generated(
        self,
        pair: str,
        direction: str,
        score: float,
        strategies: list,
    ) -> None:
        strats = ", ".join(strategies) if strategies else "none"
        self._log.info(
            "SIGNAL | %s %s | score=%.1f | strategies=[%s]",
            pair, direction, score, strats,
        )

    def signal_rejected(self, pair: str, reason: str, score: Optional[float] = None) -> None:
        sc = f" score={score:.1f}" if score is not None else ""
        self._log.debug("SIGNAL REJECTED | %s%s | %s", pair, sc, reason)
