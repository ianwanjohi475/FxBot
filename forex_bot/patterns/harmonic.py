"""Harmonic pattern detection using exact Fibonacci ratios."""
import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from typing import List, Dict, Optional

FIBONACCI_RATIOS = {
    "gartley": {
        "XAB": [(0.618, 0.618)],
        "ABC": [(0.382, 0.886)],
        "BCD": [(1.13, 1.618)],
        "XAD": [(0.786, 0.786)],
    },
    "butterfly": {
        "XAB": [(0.786, 0.786)],
        "ABC": [(0.382, 0.886)],
        "BCD": [(1.618, 2.618)],
        "XAD": [(1.27, 1.618)],
    },
    "bat": {
        "XAB": [(0.382, 0.500)],
        "ABC": [(0.382, 0.886)],
        "BCD": [(1.618, 2.618)],
        "XAD": [(0.886, 0.886)],
    },
    "crab": {
        "XAB": [(0.382, 0.618)],
        "ABC": [(0.382, 0.886)],
        "BCD": [(2.618, 3.618)],
        "XAD": [(1.618, 1.618)],
    },
    "deep_crab": {
        "XAB": [(0.886, 0.886)],
        "ABC": [(0.382, 0.886)],
        "BCD": [(2.000, 3.618)],
        "XAD": [(1.618, 1.618)],
    },
    "shark": {
        "XAB": [(0.000, 0.500)],
        "ABC": [(1.130, 1.618)],
        "BCD": [(1.618, 2.240)],
        "XAD": [(0.886, 1.130)],
    },
    "cypher": {
        "XAB": [(0.382, 0.618)],
        "ABC": [(1.130, 1.414)],
        "BCD": [(0.382, 0.382)],
        "XAD": [(0.786, 0.786)],
    },
}


class HarmonicPatterns:

    @staticmethod
    def _find_swings(df: pd.DataFrame, order: int = 5):
        highs_idx = argrelextrema(df["high"].values, np.greater, order=order)[0]
        lows_idx = argrelextrema(df["low"].values, np.less, order=order)[0]
        return highs_idx, lows_idx

    @staticmethod
    def _check_ratio(ratio: float, lo: float, hi: float, tolerance: float = 0.05) -> bool:
        return (lo * (1 - tolerance)) <= ratio <= (hi * (1 + tolerance))

    @staticmethod
    def _fib_ratio(leg_a: float, leg_b: float) -> float:
        if leg_a == 0:
            return 0.0
        return abs(leg_b / leg_a)

    @classmethod
    def _validate_xabcd(
        cls,
        x: float, a: float, b: float, c: float, d: float,
        pattern_name: str, is_bullish: bool,
    ) -> bool:
        ratios = FIBONACCI_RATIOS.get(pattern_name)
        if ratios is None:
            return False

        xa = abs(a - x)
        ab = abs(b - a)
        bc = abs(c - b)
        cd = abs(d - c)
        xd = abs(d - x)

        xab = cls._fib_ratio(xa, ab)
        abc = cls._fib_ratio(ab, bc)
        bcd = cls._fib_ratio(bc, cd)
        xad = cls._fib_ratio(xa, xd)

        for lo, hi in ratios.get("XAB", []):
            if not cls._check_ratio(xab, lo, hi):
                return False
        for lo, hi in ratios.get("ABC", []):
            if not cls._check_ratio(abc, lo, hi):
                return False
        for lo, hi in ratios.get("BCD", []):
            if not cls._check_ratio(bcd, lo, hi):
                return False
        for lo, hi in ratios.get("XAD", []):
            if not cls._check_ratio(xad, lo, hi):
                return False
        return True

    @classmethod
    def detect_xabcd(cls, df: pd.DataFrame, pattern_name: str) -> List[Dict]:
        results = []
        highs_idx, lows_idx = cls._find_swings(df, order=5)

        all_pivots = sorted(
            [(i, "H", df["high"].iloc[i]) for i in highs_idx]
            + [(i, "L", df["low"].iloc[i]) for i in lows_idx],
            key=lambda x: x[0],
        )

        if len(all_pivots) < 5:
            return results

        for i in range(len(all_pivots) - 4):
            pts = all_pivots[i : i + 5]
            types = [p[1] for p in pts]
            prices = [p[2] for p in pts]
            indices = [p[0] for p in pts]

            is_bullish = types[0] == "H" and types[1] == "L" and types[2] == "H" and types[3] == "L" and types[4] == "H"
            is_bearish = types[0] == "L" and types[1] == "H" and types[2] == "L" and types[3] == "H" and types[4] == "L"

            if not (is_bullish or is_bearish):
                continue

            x, a, b, c, d = prices
            valid = cls._validate_xabcd(x, a, b, c, d, pattern_name, is_bullish)

            if valid:
                direction = "BUY" if is_bearish else "SELL"
                xa = abs(a - x)
                ote_low = d - xa * 0.786 if is_bearish else d + xa * 0.786
                ote_high = d - xa * 0.618 if is_bearish else d + xa * 0.618
                results.append({
                    "pattern": pattern_name,
                    "direction": direction,
                    "x": x, "a": a, "b": b, "c": c, "d": d,
                    "x_idx": indices[0], "d_idx": indices[4],
                    "ote_low": min(ote_low, ote_high),
                    "ote_high": max(ote_low, ote_high),
                    "prz": d,
                    "confidence": 0.80,
                })
        return results

    @classmethod
    def gartley(cls, df: pd.DataFrame) -> List[Dict]:
        return cls.detect_xabcd(df, "gartley")

    @classmethod
    def butterfly(cls, df: pd.DataFrame) -> List[Dict]:
        return cls.detect_xabcd(df, "butterfly")

    @classmethod
    def bat(cls, df: pd.DataFrame) -> List[Dict]:
        return cls.detect_xabcd(df, "bat")

    @classmethod
    def crab(cls, df: pd.DataFrame) -> List[Dict]:
        return cls.detect_xabcd(df, "crab")

    @classmethod
    def deep_crab(cls, df: pd.DataFrame) -> List[Dict]:
        return cls.detect_xabcd(df, "deep_crab")

    @classmethod
    def shark(cls, df: pd.DataFrame) -> List[Dict]:
        return cls.detect_xabcd(df, "shark")

    @classmethod
    def cypher(cls, df: pd.DataFrame) -> List[Dict]:
        return cls.detect_xabcd(df, "cypher")

    @classmethod
    def abcd_pattern(cls, df: pd.DataFrame) -> List[Dict]:
        """ABCD: AB leg, BC retracement 0.618, CD extension equal to AB."""
        results = []
        highs_idx, lows_idx = cls._find_swings(df, order=5)

        all_pivots = sorted(
            [(i, "H", df["high"].iloc[i]) for i in highs_idx]
            + [(i, "L", df["low"].iloc[i]) for i in lows_idx],
            key=lambda x: x[0],
        )

        for i in range(len(all_pivots) - 3):
            pts = all_pivots[i : i + 4]
            types = [p[1] for p in pts]
            prices = [p[2] for p in pts]
            indices = [p[0] for p in pts]

            is_bullish = types[0] == "H" and types[1] == "L" and types[2] == "H" and types[3] == "L"
            is_bearish = types[0] == "L" and types[1] == "H" and types[2] == "L" and types[3] == "H"

            if not (is_bullish or is_bearish):
                continue

            a, b, c, d = prices
            ab = abs(b - a)
            bc = abs(c - b)
            cd = abs(d - c)

            bc_ratio = cls._fib_ratio(ab, bc)
            cd_ratio = cls._fib_ratio(ab, cd)

            if cls._check_ratio(bc_ratio, 0.618, 0.618) and cls._check_ratio(cd_ratio, 1.0, 1.0):
                direction = "BUY" if is_bullish else "SELL"
                results.append({
                    "pattern": "abcd",
                    "direction": direction,
                    "a": a, "b": b, "c": c, "d": d,
                    "a_idx": indices[0], "d_idx": indices[3],
                    "prz": d,
                    "confidence": 0.75,
                })
        return results

    @classmethod
    def three_drives(cls, df: pd.DataFrame) -> List[Dict]:
        """Three drives: three symmetrical impulse moves."""
        results = []
        highs_idx, lows_idx = cls._find_swings(df, order=5)

        for is_bullish in [True, False]:
            pivots_idx = lows_idx if is_bullish else highs_idx
            if len(pivots_idx) < 3:
                continue
            for i in range(len(pivots_idx) - 2):
                p1_i, p2_i, p3_i = pivots_idx[i], pivots_idx[i + 1], pivots_idx[i + 2]
                if is_bullish:
                    p1 = df["low"].iloc[p1_i]
                    p2 = df["low"].iloc[p2_i]
                    p3 = df["low"].iloc[p3_i]
                else:
                    p1 = df["high"].iloc[p1_i]
                    p2 = df["high"].iloc[p2_i]
                    p3 = df["high"].iloc[p3_i]

                d1 = abs(p2 - p1)
                d2 = abs(p3 - p2)
                if d1 == 0:
                    continue
                ratio = d2 / d1
                if 0.9 <= ratio <= 1.1:
                    direction = "BUY" if is_bullish else "SELL"
                    results.append({
                        "pattern": "three_drives",
                        "direction": direction,
                        "p1": p1, "p2": p2, "p3": p3,
                        "p3_idx": p3_i,
                        "prz": p3,
                        "confidence": 0.70,
                    })
        return results

    @classmethod
    def detect_all(cls, df: pd.DataFrame) -> List[Dict]:
        results = []
        for fn in [cls.gartley, cls.butterfly, cls.bat, cls.crab,
                   cls.deep_crab, cls.shark, cls.cypher, cls.abcd_pattern, cls.three_drives]:
            try:
                results.extend(fn(df))
            except Exception:
                pass
        return results
