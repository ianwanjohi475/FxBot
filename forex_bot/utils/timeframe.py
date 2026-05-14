"""Timeframe utilities and conversions."""
from enum import Enum
from datetime import datetime
import pytz


class TimeFrame(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"


TIMEFRAMES = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
    "W1": 604800,
}

TF_ORDER = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"]

OANDA_GRANULARITY = {
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "M30": "M30",
    "H1": "H1",
    "H4": "H4",
    "D1": "D",
    "W1": "W",
}

MT5_TIMEFRAMES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
    "W1": 10080,
}


def get_higher_timeframe(tf: str) -> str:
    idx = TF_ORDER.index(tf)
    if idx < len(TF_ORDER) - 1:
        return TF_ORDER[idx + 1]
    return tf


def get_lower_timeframe(tf: str) -> str:
    idx = TF_ORDER.index(tf)
    if idx > 0:
        return TF_ORDER[idx - 1]
    return tf


def tf_to_oanda_granularity(tf: str) -> str:
    return OANDA_GRANULARITY.get(tf, tf)


def tf_to_mt5_timeframe(tf: str) -> int:
    return MT5_TIMEFRAMES.get(tf, 1)


def align_to_timeframe(dt: datetime, tf: str) -> datetime:
    """Snap datetime to the start of the current timeframe period."""
    seconds = TIMEFRAMES.get(tf, 60)
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    ts = int(dt.timestamp())
    aligned_ts = (ts // seconds) * seconds
    return datetime.fromtimestamp(aligned_ts, tz=pytz.utc)


def candles_per_day(tf: str) -> int:
    seconds = TIMEFRAMES.get(tf, 60)
    return int(86400 / seconds)


def is_higher_timeframe(tf1: str, tf2: str) -> bool:
    """Return True if tf1 is higher than tf2."""
    return TIMEFRAMES.get(tf1, 0) > TIMEFRAMES.get(tf2, 0)


def timeframe_to_seconds(tf: str) -> int:
    return TIMEFRAMES.get(tf, 60)


def tf_to_pandas_freq(tf: str) -> str:
    mapping = {
        "M1": "1min",
        "M5": "5min",
        "M15": "15min",
        "M30": "30min",
        "H1": "1h",
        "H4": "4h",
        "D1": "1D",
        "W1": "1W",
    }
    return mapping.get(tf, "1min")
