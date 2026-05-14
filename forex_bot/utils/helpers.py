"""
FxBot General Helpers
=====================
Utility functions for pip math, market-open checks, price formatting,
risk/reward calculation, pair normalisation, and candle geometry.

All functions are pure (no side-effects) unless noted otherwise.
"""

import re
from datetime import datetime, time, timezone
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Pair metadata
# ---------------------------------------------------------------------------

# How many decimal places constitute ONE pip for each pair.
# JPY and XAU pairs: pip = 0.01  (2nd decimal)
# All others:        pip = 0.0001 (4th decimal)
_PIP_DECIMAL_PLACES: dict = {
    "EUR_USD": 4, "GBP_USD": 4, "AUD_USD": 4,
    "NZD_USD": 4, "USD_CAD": 4, "USD_CHF": 4,
    "USD_JPY": 2, "EUR_JPY": 2, "GBP_JPY": 2,
    "AUD_JPY": 2, "NZD_JPY": 2, "CHF_JPY": 2,
    "XAU_USD": 2, "XAG_USD": 4,
}

_DEFAULT_PIP_DECIMALS: int = 4

# Tick sizes (minimum price movement)
_TICK_SIZE: dict = {
    "EUR_USD": 0.00001, "GBP_USD": 0.00001, "AUD_USD": 0.00001,
    "NZD_USD": 0.00001, "USD_CAD": 0.00001, "USD_CHF": 0.00001,
    "USD_JPY": 0.001,   "EUR_JPY": 0.001,   "GBP_JPY": 0.001,
    "AUD_JPY": 0.001,   "NZD_JPY": 0.001,   "CHF_JPY": 0.001,
    "XAU_USD": 0.01,    "XAG_USD": 0.001,
}

_DEFAULT_TICK_SIZE: float = 0.00001

# Standard lot sizes (units of base currency)
_LOT_SIZE: int = 100_000

# Approximate pip values in USD per standard lot (used when live rate unavailable)
# These are rough approximations; use get_pip_value() for accuracy.
_APPROX_PIP_VALUE_USD: dict = {
    "EUR_USD": 10.0, "GBP_USD": 10.0, "AUD_USD": 10.0,
    "NZD_USD": 10.0, "USD_CAD":  7.7, "USD_CHF":  9.8,
    "USD_JPY":  9.1, "EUR_JPY":  9.1, "GBP_JPY":  9.1,
    "XAU_USD":  1.0,
}

# Forex market sessions (UTC): pair -> list of (open, close) tuples
# (close hour may be < open hour when session crosses midnight)
_SESSION_MAP: dict = {
    "EUR_USD": [(7, 17)],   "GBP_USD": [(7, 17)],
    "USD_JPY": [(0, 9), (7, 17)],
    "AUD_USD": [(21, 9)],   "NZD_USD": [(21, 9)],
    "USD_CHF": [(7, 17)],   "USD_CAD": [(12, 21)],
    "XAU_USD": [(7, 17)],
    "GBP_JPY": [(7, 17)],   "EUR_JPY": [(7, 17)],
}


# ---------------------------------------------------------------------------
# Pip conversion
# ---------------------------------------------------------------------------

def _pip_size(pair: str) -> float:
    """Return the size of one pip for *pair* (e.g. 0.0001 for EUR_USD)."""
    pair = normalize_pair(pair)
    decimals = _PIP_DECIMAL_PLACES.get(pair, _DEFAULT_PIP_DECIMALS)
    return 10 ** (-decimals)


def pips_to_price(pips: float, pair: str) -> float:
    """
    Convert a pip count to the equivalent price movement for *pair*.

    Args:
        pips: Number of pips (may be fractional).
        pair: Currency pair symbol (e.g. "EUR_USD" or "EURUSD").

    Returns:
        Price movement in the pair's quote currency.

    Example::

        pips_to_price(10, "EUR_USD")  # -> 0.0010
        pips_to_price(10, "USD_JPY")  # -> 0.10
    """
    return pips * _pip_size(pair)


def price_to_pips(price_diff: float, pair: str) -> float:
    """
    Convert a price movement to pips for *pair*.

    Args:
        price_diff: Absolute price difference (always positive).
        pair:       Currency pair symbol.

    Returns:
        Number of pips (float).

    Example::

        price_to_pips(0.0010, "EUR_USD")  # -> 10.0
        price_to_pips(0.10,   "USD_JPY")  # -> 10.0
    """
    ps = _pip_size(pair)
    if ps == 0:
        return 0.0
    return abs(price_diff) / ps


# ---------------------------------------------------------------------------
# Tick rounding
# ---------------------------------------------------------------------------

def round_to_tick(price: float, pair: str) -> float:
    """
    Round *price* to the nearest valid tick size for *pair*.

    Args:
        price: Raw price to round.
        pair:  Currency pair symbol.

    Returns:
        Price rounded to the pair's minimum tick size.

    Example::

        round_to_tick(1.08523, "EUR_USD")  # -> 1.08523  (already on tick)
        round_to_tick(1.085234, "EUR_USD") # -> 1.08523
    """
    pair = normalize_pair(pair)
    tick = _TICK_SIZE.get(pair, _DEFAULT_TICK_SIZE)
    # Use integer arithmetic to avoid floating-point drift
    factor = 1.0 / tick
    return round(round(price * factor) / factor, 10)


# ---------------------------------------------------------------------------
# Pip value
# ---------------------------------------------------------------------------

def get_pip_value(
    pair: str,
    lot_size: float = 1.0,
    account_currency: str = "USD",
    current_rate: Optional[float] = None,
) -> float:
    """
    Return the monetary value of one pip for *lot_size* lots in *account_currency*.

    The calculation uses the formula::

        pip_value = (pip_size / quote_rate) * lot_size * _LOT_SIZE

    where *quote_rate* is the exchange rate of the quote currency against the
    account currency.  When *current_rate* is not provided the function falls
    back to a hardcoded approximation (USD accounts only).

    Args:
        pair:             Currency pair (e.g. "EUR_USD").
        lot_size:         Position size in standard lots (1 lot = 100,000 units).
        account_currency: The currency of the trading account (default "USD").
        current_rate:     Current market price of the pair (used for JPY crosses).

    Returns:
        Monetary pip value in *account_currency*.

    Example::

        get_pip_value("EUR_USD", lot_size=1.0)               # -> ~10.0
        get_pip_value("USD_JPY", lot_size=0.1, current_rate=150.0)  # -> ~0.667
    """
    pair = normalize_pair(pair)
    ps = _pip_size(pair)
    units = lot_size * _LOT_SIZE

    _, quote = get_base_quote(pair)

    if quote == account_currency:
        # e.g. EUR/USD, account in USD
        pip_value = ps * units
    elif current_rate and current_rate != 0:
        # e.g. USD/JPY, account in USD: pip in JPY, divide by USDJPY rate
        pip_value = (ps / current_rate) * units
    else:
        # Fallback approximation
        approx = _APPROX_PIP_VALUE_USD.get(pair, 10.0)
        pip_value = approx * lot_size

    return pip_value


# ---------------------------------------------------------------------------
# Timeframe helpers
# ---------------------------------------------------------------------------

# Mapping of timeframe string -> duration in seconds
_TF_SECONDS: dict = {
    "M1":  60,
    "M5":  300,
    "M15": 900,
    "M30": 1800,
    "H1":  3600,
    "H4":  14400,
    "D1":  86400,
    "W1":  604800,
    "MN":  2592000,   # ~30 days
}


def timeframe_to_seconds(tf: str) -> int:
    """
    Convert a timeframe string to its duration in seconds.

    Args:
        tf: Timeframe string (e.g. "M5", "H4", "D1").

    Returns:
        Duration in seconds.

    Raises:
        ValueError: If *tf* is not a recognised timeframe.

    Example::

        timeframe_to_seconds("H4")  # -> 14400
        timeframe_to_seconds("D1")  # -> 86400
    """
    tf = tf.upper()
    if tf not in _TF_SECONDS:
        raise ValueError(
            f"Unknown timeframe: {tf!r}. "
            f"Valid options: {sorted(_TF_SECONDS)}"
        )
    return _TF_SECONDS[tf]


# ---------------------------------------------------------------------------
# Market open check
# ---------------------------------------------------------------------------

def is_market_open(pair: str, dt: Optional[datetime] = None) -> bool:
    """
    Determine whether the forex market is open for *pair* at time *dt*.

    The forex market is closed from Friday 22:00 UTC to Sunday 21:00 UTC.
    Within that window, specific pairs have their own active sessions; this
    function checks the pair's primary session(s).

    Args:
        pair: Currency pair symbol.
        dt:   Datetime to check. Defaults to ``datetime.utcnow()``.

    Returns:
        True if the market is open and actively trading *pair*.

    Example::

        is_market_open("EUR_USD")                                  # live check
        is_market_open("USD_JPY", datetime(2024, 1, 15, 10, 0, 0)) # Monday 10:00 UTC
    """
    if dt is None:
        dt = datetime.now(timezone.utc).replace(tzinfo=None)

    weekday = dt.weekday()  # 0=Monday … 6=Sunday
    hour = dt.hour
    minute = dt.minute

    # Forex closes Friday 22:00 UTC, reopens Sunday 21:00 UTC
    if weekday == 4 and (hour > 22 or (hour == 22 and minute >= 0)):
        return False
    if weekday == 5:  # Saturday
        return False
    if weekday == 6 and (hour < 21):
        return False

    # Check pair-specific sessions
    pair = normalize_pair(pair)
    sessions = _SESSION_MAP.get(pair)
    if sessions is None:
        # Unknown pair - assume open on weekdays
        return True

    for open_h, close_h in sessions:
        if open_h < close_h:
            # Same-day session (e.g. 07:00-17:00)
            if open_h <= hour < close_h:
                return True
        else:
            # Overnight session (e.g. 21:00-09:00 next day)
            if hour >= open_h or hour < close_h:
                return True

    return False


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_currency(amount: float, symbol: str = "$") -> str:
    """
    Format *amount* as a currency string with thousand separators.

    Args:
        amount: Monetary amount (may be negative).
        symbol: Currency symbol prepended to the value (default "$").

    Returns:
        Formatted string, e.g. "$1,234.56" or "-$56.78".

    Example::

        format_currency(1234.5678)        # -> "$1,234.57"
        format_currency(-56.789, symbol="€")  # -> "-€56.79"
    """
    negative = amount < 0
    abs_amt = abs(amount)
    formatted = f"{abs_amt:,.2f}"
    if negative:
        return f"-{symbol}{formatted}"
    return f"{symbol}{formatted}"


# ---------------------------------------------------------------------------
# Risk / Reward
# ---------------------------------------------------------------------------

def calculate_rr(
    entry: float,
    sl: float,
    tp: float,
) -> float:
    """
    Calculate the risk/reward ratio for a trade.

    Args:
        entry: Entry price.
        sl:    Stop-loss price.
        tp:    Take-profit price.

    Returns:
        Risk/reward ratio (always positive). Returns 0.0 if risk is zero.

    Example::

        calculate_rr(1.0850, 1.0800, 1.0950)  # -> 2.0  (risk=50 pips, reward=100 pips)
    """
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk == 0:
        return 0.0
    return reward / risk


# ---------------------------------------------------------------------------
# Pair normalisation
# ---------------------------------------------------------------------------

_PAIR_STRIP_RE = re.compile(r"[^A-Za-z]")  # strip non-alpha chars


def normalize_pair(pair: str) -> str:
    """
    Normalize a currency pair symbol to the ``XXX_YYY`` format used by OANDA.

    Handles the following input formats:
      - "EURUSD"   -> "EUR_USD"
      - "EUR/USD"  -> "EUR_USD"
      - "EUR-USD"  -> "EUR_USD"
      - "EUR_USD"  -> "EUR_USD"  (already normalized)
      - "eurusd"   -> "EUR_USD"

    Args:
        pair: Currency pair in any common format.

    Returns:
        Normalized pair string in ``XXX_YYY`` format.

    Example::

        normalize_pair("eurusd")  # -> "EUR_USD"
        normalize_pair("XAU/USD") # -> "XAU_USD"
    """
    upper = pair.upper()
    # Remove all non-alpha characters to get bare letters
    bare = _PAIR_STRIP_RE.sub("", upper)

    if len(bare) == 6:
        return f"{bare[:3]}_{bare[3:]}"
    if len(bare) == 7:
        # e.g. XAUUSD written as 7 chars? - shouldn't happen, but handle gracefully
        return f"{bare[:3]}_{bare[3:]}"

    # Already contains underscore or unknown format - return as-is upper-cased
    # but replace common separators with underscore
    return upper.replace("/", "_").replace("-", "_").replace(".", "_")


def get_base_quote(pair: str) -> Tuple[str, str]:
    """
    Split a currency pair into its base and quote currencies.

    Args:
        pair: Currency pair symbol (any common format).

    Returns:
        Tuple of (base, quote) strings, both uppercase.

    Example::

        get_base_quote("EUR_USD")  # -> ("EUR", "USD")
        get_base_quote("GBPJPY")   # -> ("GBP", "JPY")
    """
    normed = normalize_pair(pair)
    parts = normed.split("_")
    if len(parts) == 2:
        return parts[0], parts[1]
    # Fallback: first 3 and remaining
    return normed[:3], normed[3:]


# ---------------------------------------------------------------------------
# Candle geometry
# ---------------------------------------------------------------------------

def candle_body_size(open_price: float, close_price: float) -> float:
    """
    Return the absolute size of a candle's body (|close - open|).

    Args:
        open_price:  Candle open price.
        close_price: Candle close price.

    Returns:
        Absolute body size in price units.

    Example::

        candle_body_size(1.0850, 1.0870)  # -> 0.0020
    """
    return abs(close_price - open_price)


def candle_wick_size(
    high: float,
    low: float,
    open_price: float,
    close_price: float,
) -> Tuple[float, float]:
    """
    Return the upper and lower wick sizes of a candle.

    The body top is ``max(open, close)`` and body bottom is ``min(open, close)``.

    Args:
        high:        Candle high.
        low:         Candle low.
        open_price:  Candle open.
        close_price: Candle close.

    Returns:
        Tuple of (upper_wick, lower_wick) in price units.

    Example::

        candle_wick_size(1.0900, 1.0800, 1.0850, 1.0870)
        # upper_wick = 1.0900 - 1.0870 = 0.0030
        # lower_wick = 1.0850 - 1.0800 = 0.0050
    """
    body_top = max(open_price, close_price)
    body_bottom = min(open_price, close_price)
    upper_wick = high - body_top
    lower_wick = body_bottom - low
    return upper_wick, lower_wick


def is_bullish_candle(open_price: float, close_price: float) -> bool:
    """
    Return True if the candle closed higher than it opened (bullish).

    Args:
        open_price:  Candle open price.
        close_price: Candle close price.

    Returns:
        True for a bullish (green) candle, False for bearish or doji.

    Example::

        is_bullish_candle(1.0850, 1.0870)  # -> True
        is_bullish_candle(1.0870, 1.0850)  # -> False
    """
    return close_price > open_price


# ---------------------------------------------------------------------------
# Misc utilities
# ---------------------------------------------------------------------------

def clamp(value: float, min_val: float, max_val: float) -> float:
    """Return *value* clamped to [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def percentage_change(old_value: float, new_value: float) -> float:
    """
    Calculate the percentage change from *old_value* to *new_value*.

    Returns 0.0 if *old_value* is zero (avoids ZeroDivisionError).
    """
    if old_value == 0:
        return 0.0
    return (new_value - old_value) / abs(old_value) * 100.0


def pip_distance(price1: float, price2: float, pair: str) -> float:
    """
    Return the number of pips between *price1* and *price2* for *pair*.

    Equivalent to ``price_to_pips(abs(price1 - price2), pair)``.
    """
    return price_to_pips(abs(price1 - price2), pair)


def lot_size_from_risk(
    account_balance: float,
    risk_pct: float,
    sl_pips: float,
    pair: str,
    current_rate: Optional[float] = None,
) -> float:
    """
    Calculate the appropriate lot size to risk exactly *risk_pct* of
    *account_balance* given a stop-loss distance of *sl_pips*.

    Args:
        account_balance: Total account equity in USD.
        risk_pct:        Fraction to risk, e.g. 0.01 for 1%.
        sl_pips:         Stop-loss distance in pips.
        pair:            Currency pair.
        current_rate:    Current market rate (needed for non-USD quotes).

    Returns:
        Lot size in standard lots (rounded down to 2 decimal places).

    Example::

        lot_size_from_risk(10000, 0.01, 20, "EUR_USD")  # -> 0.5 lots
    """
    if sl_pips <= 0:
        return 0.0

    risk_amount = account_balance * risk_pct
    # Value of 1 pip per 1 standard lot
    pip_val_per_lot = get_pip_value(pair, lot_size=1.0, current_rate=current_rate)
    if pip_val_per_lot <= 0:
        return 0.0

    raw_lots = risk_amount / (sl_pips * pip_val_per_lot)
    # Round down to 2 decimal places (conservative)
    return int(raw_lots * 100) / 100.0


def spread_cost(spread_pips: float, pair: str, lot_size: float = 1.0) -> float:
    """
    Calculate the cost of the spread in USD for a given trade size.

    Args:
        spread_pips: Broker spread in pips.
        pair:        Currency pair.
        lot_size:    Position size in standard lots.

    Returns:
        Spread cost in USD (approximate).
    """
    return spread_pips * get_pip_value(pair, lot_size=lot_size)
