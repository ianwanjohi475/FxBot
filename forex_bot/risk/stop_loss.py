"""Stop Loss calculation utilities."""
import pandas as pd
from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class StopLossCalculator:

    @staticmethod
    def _pip_size(pair: str) -> float:
        if "JPY" in pair:
            return 0.01
        if "XAU" in pair or "XAG" in pair:
            return 0.01
        if "US30" in pair or "NAS" in pair or "SPX" in pair or "DAX" in pair:
            return 1.0   # index points
        return 0.0001

    def atr_based_sl(self, entry: float, direction: str, atr: float,
                     multiplier: float = 1.5, pair: str = "EUR_USD") -> float:
        offset = atr * multiplier
        sl = entry - offset if direction == "BUY" else entry + offset
        return round(sl, 5)

    def structure_based_sl(self, entry: float, direction: str,
                            df: pd.DataFrame, lookback: int = 10,
                            buffer_pips: float = 0.5, pair: str = "EUR_USD") -> float:
        pip = self._pip_size(pair)
        buf = buffer_pips * pip
        window = df.tail(lookback)
        if direction == "BUY":
            swing_low = window["low"].min()
            sl = swing_low - buf
        else:
            swing_high = window["high"].max()
            sl = swing_high + buf
        return round(sl, 5)

    def fixed_pip_sl(self, entry: float, direction: str,
                     pips: float, pair: str = "EUR_USD") -> float:
        pip = self._pip_size(pair)
        offset = pips * pip
        sl = entry - offset if direction == "BUY" else entry + offset
        return round(sl, 5)

    # Pair-specific SL bounds (pips). Volatile pairs need wider minimums to
    # avoid getting stopped out by normal noise before the move develops.
    PAIR_SL_BOUNDS: dict = {
        "XAU_USD":  {"min": 15,  "max": 150},   # gold: ~$0.15–$1.50 per pip on 0.03 lots
        "US30_USD": {"min": 20,  "max": 300},   # Dow: 20–300 index points
        "GBP_JPY":  {"min": 10,  "max": 150},   # volatile cross
        "USD_JPY":  {"min":  5,  "max": 100},
        "EUR_USD":  {"min":  5,  "max": 100},
    }

    def validate_sl(self, entry: float, sl: float, direction: str,
                    min_pips: float = 5, max_pips: float = 150,
                    pair: str = "EUR_USD") -> float:
        # Use pair-specific bounds when available
        bounds = self.PAIR_SL_BOUNDS.get(pair, {})
        min_pips = bounds.get("min", min_pips)
        max_pips = bounds.get("max", max_pips)

        pip = self._pip_size(pair)
        distance_pips = abs(entry - sl) / pip
        if distance_pips < min_pips:
            logger.debug(
                f"[SL] {pair} SL too tight ({distance_pips:.1f}p < {min_pips}p), "
                f"adjusting to minimum"
            )
            return self.fixed_pip_sl(entry, direction, min_pips, pair)
        if distance_pips > max_pips:
            logger.debug(
                f"[SL] {pair} SL too wide ({distance_pips:.1f}p > {max_pips}p), "
                f"capping at maximum"
            )
            return self.fixed_pip_sl(entry, direction, max_pips, pair)
        return round(sl, 5)

    def round_number_adjusted_sl(self, sl: float, direction: str,
                                  pair: str = "EUR_USD") -> float:
        """Push SL just beyond the nearest round number if within 2 pips."""
        pip = self._pip_size(pair)
        round_step = 0.01 if "JPY" in pair else 0.0010  # 100-pip round numbers
        nearest = round(sl / round_step) * round_step
        dist_pips = abs(sl - nearest) / pip
        if dist_pips < 2:
            extra = 3 * pip
            if direction == "BUY":
                return round(nearest - extra, 5)
            return round(nearest + extra, 5)
        return round(sl, 5)
