"""Smart Money Concepts (SMC) and ICT methodology implementation."""
import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
import pytz


class SmartMoneyConcepts:

    @staticmethod
    def detect_order_blocks(df: pd.DataFrame, lookback: int = 50) -> List[Dict]:
        """Detect bullish and bearish order blocks."""
        results = []
        data = df.tail(lookback).reset_index(drop=True)
        avg_body = abs(data["close"] - data["open"]).rolling(10).mean()

        for i in range(1, len(data) - 1):
            curr = data.iloc[i]
            next_c = data.iloc[i + 1]
            body = abs(curr["close"] - curr["open"])
            avg = avg_body.iloc[i] if not pd.isna(avg_body.iloc[i]) else body

            next_body = abs(next_c["close"] - next_c["open"])

            # Bullish OB: last bearish candle before strong bullish move
            if curr["close"] < curr["open"] and next_c["close"] > next_c["open"]:
                if next_body > 1.5 * avg and next_c["close"] > curr["high"]:
                    results.append({
                        "type": "bullish_ob",
                        "high": curr["high"],
                        "low": curr["low"],
                        "index": i,
                        "strength": next_body / avg if avg else 1.0,
                        "mitigated": False,
                    })

            # Bearish OB: last bullish candle before strong bearish move
            if curr["close"] > curr["open"] and next_c["close"] < next_c["open"]:
                if next_body > 1.5 * avg and next_c["close"] < curr["low"]:
                    results.append({
                        "type": "bearish_ob",
                        "high": curr["high"],
                        "low": curr["low"],
                        "index": i,
                        "strength": next_body / avg if avg else 1.0,
                        "mitigated": False,
                    })
        return results

    @staticmethod
    def detect_fvg(df: pd.DataFrame) -> List[Dict]:
        """Detect Fair Value Gaps (3-candle imbalances)."""
        results = []
        for i in range(1, len(df) - 1):
            c1 = df.iloc[i - 1]
            c3 = df.iloc[i + 1]

            # Bullish FVG: candle 1 high < candle 3 low
            if c1["high"] < c3["low"]:
                results.append({
                    "type": "bullish_fvg",
                    "top": c3["low"],
                    "bottom": c1["high"],
                    "mid": (c1["high"] + c3["low"]) / 2,
                    "index": i,
                    "filled": False,
                })

            # Bearish FVG: candle 1 low > candle 3 high
            if c1["low"] > c3["high"]:
                results.append({
                    "type": "bearish_fvg",
                    "top": c1["low"],
                    "bottom": c3["high"],
                    "mid": (c1["low"] + c3["high"]) / 2,
                    "index": i,
                    "filled": False,
                })
        return results

    @staticmethod
    def detect_bos(df: pd.DataFrame, swing_period: int = 10) -> List[Dict]:
        """Break of Structure detection."""
        results = []
        for i in range(swing_period, len(df)):
            window = df.iloc[i - swing_period : i]
            curr = df.iloc[i]

            recent_high = window["high"].max()
            recent_low = window["low"].min()

            # Bullish BOS: closes above recent swing high
            if curr["close"] > recent_high and df["close"].iloc[i - 1] <= recent_high:
                results.append({
                    "type": "bullish_bos",
                    "level": recent_high,
                    "index": i,
                    "strength": (curr["close"] - recent_high) / recent_high,
                })

            # Bearish BOS: closes below recent swing low
            if curr["close"] < recent_low and df["close"].iloc[i - 1] >= recent_low:
                results.append({
                    "type": "bearish_bos",
                    "level": recent_low,
                    "index": i,
                    "strength": (recent_low - curr["close"]) / recent_low,
                })
        return results

    @staticmethod
    def detect_choch(df: pd.DataFrame, swing_period: int = 10) -> List[Dict]:
        """Change of Character — first BOS in opposite direction."""
        results = []
        bos_list = SmartMoneyConcepts.detect_bos(df, swing_period)
        if len(bos_list) < 2:
            return results

        for i in range(1, len(bos_list)):
            prev = bos_list[i - 1]
            curr = bos_list[i]
            if prev["type"] != curr["type"]:
                results.append({
                    "type": "bullish_choch" if curr["type"] == "bullish_bos" else "bearish_choch",
                    "level": curr["level"],
                    "index": curr["index"],
                    "prev_bos_type": prev["type"],
                })
        return results

    @staticmethod
    def detect_liquidity_sweep(df: pd.DataFrame, lookback: int = 20) -> List[Dict]:
        """Detect stop hunts (liquidity sweeps above equal highs / below equal lows)."""
        results = []
        for i in range(lookback, len(df)):
            window = df.iloc[i - lookback : i]
            curr = df.iloc[i]

            prior_highs = window["high"]
            prior_lows = window["low"]
            max_high = prior_highs.max()
            min_low = prior_lows.min()

            # Buy-side sweep: wick above prior highs then closes below
            if curr["high"] > max_high and curr["close"] < max_high:
                results.append({
                    "type": "buy_side_sweep",
                    "level": max_high,
                    "index": i,
                    "wick_above": curr["high"] - max_high,
                })

            # Sell-side sweep: wick below prior lows then closes above
            if curr["low"] < min_low and curr["close"] > min_low:
                results.append({
                    "type": "sell_side_sweep",
                    "level": min_low,
                    "index": i,
                    "wick_below": min_low - curr["low"],
                })
        return results

    @staticmethod
    def detect_equal_highs_lows(
        df: pd.DataFrame, lookback: int = 20, tolerance: float = 0.001
    ) -> Dict:
        """Identify equal highs and lows (liquidity pools)."""
        data = df.tail(lookback)
        highs = data["high"].values
        lows = data["low"].values

        equal_highs = []
        equal_lows = []

        for i in range(len(highs)):
            for j in range(i + 1, len(highs)):
                if abs(highs[i] - highs[j]) / highs[i] <= tolerance:
                    equal_highs.append((highs[i] + highs[j]) / 2)
                if abs(lows[i] - lows[j]) / lows[i] <= tolerance:
                    equal_lows.append((lows[i] + lows[j]) / 2)

        return {
            "equal_highs": list(set(round(h, 5) for h in equal_highs)),
            "equal_lows": list(set(round(l, 5) for l in equal_lows)),
        }

    @staticmethod
    def premium_discount_zone(df: pd.DataFrame, lookback: int = 50) -> Dict:
        """Calculate premium (above 50%) and discount (below 50%) zones."""
        data = df.tail(lookback)
        range_high = data["high"].max()
        range_low = data["low"].min()
        equilibrium = (range_high + range_low) / 2

        return {
            "range_high": range_high,
            "range_low": range_low,
            "equilibrium": equilibrium,
            "premium_start": equilibrium,
            "discount_end": equilibrium,
            "premium_zone": (equilibrium, range_high),
            "discount_zone": (range_low, equilibrium),
        }

    @staticmethod
    def ote_zone(swing_low: float, swing_high: float, direction: str) -> Dict:
        """Optimal Trade Entry: 61.8%–79% Fibonacci retracement zone."""
        rng = swing_high - swing_low
        if direction == "BUY":
            ote_low = swing_high - rng * 0.786
            ote_high = swing_high - rng * 0.618
        else:
            ote_low = swing_low + rng * 0.618
            ote_high = swing_low + rng * 0.786

        return {
            "ote_low": round(min(ote_low, ote_high), 5),
            "ote_high": round(max(ote_low, ote_high), 5),
            "fib_618": swing_high - rng * 0.618 if direction == "BUY" else swing_low + rng * 0.618,
            "fib_705": swing_high - rng * 0.705 if direction == "BUY" else swing_low + rng * 0.705,
            "fib_786": swing_high - rng * 0.786 if direction == "BUY" else swing_low + rng * 0.786,
        }

    @staticmethod
    def kill_zone_active(current_time: datetime) -> Dict:
        """Check which ICT kill zone is currently active (all times in EST)."""
        est = pytz.timezone("America/New_York")
        if current_time.tzinfo is None:
            current_time = pytz.utc.localize(current_time)
        local = current_time.astimezone(est)
        hour = local.hour
        minute = local.minute
        time_frac = hour + minute / 60

        zones = {
            "london_open": (2, 5),
            "ny_open": (7, 10),
            "london_close": (10, 12),
        }

        for zone_name, (start, end) in zones.items():
            if start <= time_frac < end:
                return {"active": True, "zone_name": zone_name, "hours": (start, end)}

        return {"active": False, "zone_name": None}

    @staticmethod
    def detect_judas_swing(
        df: pd.DataFrame, session_open: float, threshold_pips: float = 10
    ) -> Dict:
        """Detect fake move from session open that reverses (Judas Swing)."""
        if len(df) < 3:
            return {"detected": False}

        recent = df.tail(5)
        high = recent["high"].max()
        low = recent["low"].min()
        last_close = df["close"].iloc[-1]

        pip_mult = 100 if "JPY" in str(df.get("pair", "")) else 10000
        threshold = threshold_pips / pip_mult

        # Fake bullish then reversal
        if high > session_open + threshold and last_close < session_open:
            return {
                "detected": True,
                "direction": "SELL",
                "fake_level": high,
                "reversal_level": session_open,
            }

        # Fake bearish then reversal
        if low < session_open - threshold and last_close > session_open:
            return {
                "detected": True,
                "direction": "BUY",
                "fake_level": low,
                "reversal_level": session_open,
            }

        return {"detected": False}

    @staticmethod
    def detect_mitigation_block(
        df: pd.DataFrame, order_blocks: List[Dict]
    ) -> List[Dict]:
        """Order blocks that price has returned to and tested."""
        mitigated = []
        if df.empty or not order_blocks:
            return mitigated

        current_low = df["low"].iloc[-1]
        current_high = df["high"].iloc[-1]

        for ob in order_blocks:
            if ob["type"] == "bullish_ob":
                if current_low <= ob["high"] and current_low >= ob["low"]:
                    ob_copy = dict(ob)
                    ob_copy["mitigated"] = True
                    ob_copy["type"] = "bullish_mitigation"
                    mitigated.append(ob_copy)
            elif ob["type"] == "bearish_ob":
                if current_high >= ob["low"] and current_high <= ob["high"]:
                    ob_copy = dict(ob)
                    ob_copy["mitigated"] = True
                    ob_copy["type"] = "bearish_mitigation"
                    mitigated.append(ob_copy)
        return mitigated

    @staticmethod
    def detect_breaker_block(
        df: pd.DataFrame, order_blocks: List[Dict]
    ) -> List[Dict]:
        """Order blocks that price has broken through — now act as opposite S/R."""
        breakers = []
        if df.empty or not order_blocks:
            return breakers

        current_close = df["close"].iloc[-1]

        for ob in order_blocks:
            if ob["type"] == "bullish_ob" and current_close < ob["low"]:
                ob_copy = dict(ob)
                ob_copy["type"] = "bearish_breaker"
                ob_copy["direction"] = "SELL"
                breakers.append(ob_copy)
            elif ob["type"] == "bearish_ob" and current_close > ob["high"]:
                ob_copy = dict(ob)
                ob_copy["type"] = "bullish_breaker"
                ob_copy["direction"] = "BUY"
                breakers.append(ob_copy)
        return breakers

    @classmethod
    def analyze_all(cls, df: pd.DataFrame) -> Dict:
        """Run complete SMC analysis."""
        return {
            "order_blocks": cls.detect_order_blocks(df),
            "fvg": cls.detect_fvg(df),
            "bos": cls.detect_bos(df),
            "choch": cls.detect_choch(df),
            "liquidity_sweeps": cls.detect_liquidity_sweep(df),
            "equal_hl": cls.detect_equal_highs_lows(df),
            "premium_discount": cls.premium_discount_zone(df),
        }
