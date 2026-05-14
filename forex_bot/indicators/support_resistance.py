"""
Support and Resistance indicators implemented in pure pandas/numpy.
All methods are static and operate on standard OHLCV DataFrames.
"""

import numpy as np
import pandas as pd
from typing import List


# Pip sizes per pair: number of decimal places for 1 pip
_PIP_DECIMALS: dict = {
    "JPY": 2,   # pairs with JPY quote
}
_DEFAULT_PIP_DECIMALS = 4  # standard forex pairs


def _pip_value(pair: str) -> float:
    """Return the value of 1 pip for the given pair string (e.g. 'EUR_USD')."""
    if "JPY" in pair.upper():
        return 0.01
    return 0.0001


class SupportResistance:
    """Collection of support and resistance calculation methods."""

    @staticmethod
    def pivot_classic(df: pd.DataFrame) -> dict:
        """
        Classic (floor) pivot points based on the LAST completed candle (prior period H/L/C).

        PP = (H + L + C) / 3
        R1 = 2*PP - L  |  S1 = 2*PP - H
        R2 = PP + (H-L) |  S2 = PP - (H-L)
        R3 = H + 2*(PP-L) | S3 = L - 2*(H-PP)

        Returns
        -------
        dict with float values: 'PP', 'R1', 'R2', 'R3', 'S1', 'S2', 'S3'
        """
        row = df.iloc[-1]
        H, L, C = row["high"], row["low"], row["close"]
        PP = (H + L + C) / 3
        return {
            "PP": PP,
            "R1": 2 * PP - L,
            "R2": PP + (H - L),
            "R3": H + 2 * (PP - L),
            "S1": 2 * PP - H,
            "S2": PP - (H - L),
            "S3": L - 2 * (H - PP),
        }

    @staticmethod
    def pivot_camarilla(df: pd.DataFrame) -> dict:
        """
        Camarilla pivot points.

        PP = (H + L + C) / 3
        R1-R4 = C + (H-L) * n/12  where n = 1.1, 1.2, 1.3, 1.4 (×1.1 multipliers)
        S1-S4 = C - (H-L) * n/12

        Returns
        -------
        dict with float values: 'PP', 'R1'-'R4', 'S1'-'S4'
        """
        row = df.iloc[-1]
        H, L, C = row["high"], row["low"], row["close"]
        PP = (H + L + C) / 3
        diff = H - L
        result = {"PP": PP}
        camarilla_multipliers = {1: 1.1, 2: 1.2, 3: 1.3, 4: 1.4}
        for n, mult in camarilla_multipliers.items():
            result[f"R{n}"] = C + diff * mult / 12
            result[f"S{n}"] = C - diff * mult / 12
        return result

    @staticmethod
    def pivot_fibonacci(df: pd.DataFrame) -> dict:
        """
        Fibonacci pivot points.

        PP = (H + L + C) / 3
        R1 = PP + 0.382*(H-L) | S1 = PP - 0.382*(H-L)
        R2 = PP + 0.618*(H-L) | S2 = PP - 0.618*(H-L)
        R3 = PP + 1.000*(H-L) | S3 = PP - 1.000*(H-L)

        Returns
        -------
        dict with float values: 'PP', 'R1', 'R2', 'R3', 'S1', 'S2', 'S3'
        """
        row = df.iloc[-1]
        H, L, C = row["high"], row["low"], row["close"]
        PP = (H + L + C) / 3
        diff = H - L
        return {
            "PP": PP,
            "R1": PP + 0.382 * diff,
            "R2": PP + 0.618 * diff,
            "R3": PP + 1.000 * diff,
            "S1": PP - 0.382 * diff,
            "S2": PP - 0.618 * diff,
            "S3": PP - 1.000 * diff,
        }

    @staticmethod
    def pivot_woodie(df: pd.DataFrame) -> dict:
        """
        Woodie pivot points (PP weighs close twice).

        PP = (H + L + 2*C) / 4
        R1 = 2*PP - L  |  S1 = 2*PP - H
        R2 = PP + (H-L) | S2 = PP - (H-L)

        Returns
        -------
        dict with float values: 'PP', 'R1', 'R2', 'S1', 'S2'
        """
        row = df.iloc[-1]
        H, L, C = row["high"], row["low"], row["close"]
        PP = (H + L + 2 * C) / 4
        return {
            "PP": PP,
            "R1": 2 * PP - L,
            "R2": PP + (H - L),
            "S1": 2 * PP - H,
            "S2": PP - (H - L),
        }

    @staticmethod
    def dynamic_sr(
        df: pd.DataFrame, lookback: int = 50, sensitivity: float = 0.001
    ) -> dict:
        """
        Identify dynamic support and resistance levels from recent swing highs/lows.

        Algorithm:
          1. Find local swing highs (high > both neighbours) and swing lows
             within the last `lookback` candles.
          2. Cluster nearby levels: merge levels within `sensitivity` * price of each other.

        Parameters
        ----------
        df          : OHLCV DataFrame
        lookback    : number of recent candles to search
        sensitivity : fractional tolerance for clustering (default 0.001 = 0.1%)

        Returns
        -------
        dict with 'support' (list of float) and 'resistance' (list of float)
        """
        recent = df.tail(lookback)
        highs = recent["high"].values
        lows = recent["low"].values

        swing_highs: List[float] = []
        swing_lows: List[float] = []

        for i in range(1, len(recent) - 1):
            if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                swing_highs.append(float(highs[i]))
            if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
                swing_lows.append(float(lows[i]))

        def cluster(levels: List[float], tol: float) -> List[float]:
            if not levels:
                return []
            levels_sorted = sorted(levels)
            clusters: List[List[float]] = [[levels_sorted[0]]]
            for level in levels_sorted[1:]:
                reference = clusters[-1][0]
                if abs(level - reference) / reference <= tol:
                    clusters[-1].append(level)
                else:
                    clusters.append([level])
            return [float(np.mean(c)) for c in clusters]

        resistance = cluster(swing_highs, sensitivity)
        support = cluster(swing_lows, sensitivity)

        return {"support": support, "resistance": resistance}

    @staticmethod
    def round_number_levels(
        price: float,
        pair: str,
        pip_intervals: List[int] = None,
    ) -> List[float]:
        """
        Return round-number price levels at specified pip intervals above and below price.

        Parameters
        ----------
        price         : current price
        pair          : forex pair string (e.g. 'EUR_USD')
        pip_intervals : list of pip distances to compute round numbers for
                        (default [50, 100])

        Returns
        -------
        Sorted list of unique price levels (floats)
        """
        if pip_intervals is None:
            pip_intervals = [50, 100]

        pip = _pip_value(pair)
        levels: List[float] = []

        for interval in pip_intervals:
            step = pip * interval
            if step <= 0:
                continue
            # Find the nearest multiple of step below price
            base = np.floor(price / step) * step
            # Include a range of ±3 multiples around current price
            for k in range(-3, 4):
                level = round(base + k * step, 10)
                levels.append(level)

        # Deduplicate and sort
        levels = sorted(set(round(lv, 8) for lv in levels))
        return levels

    @staticmethod
    def weekly_monthly_open(df: pd.DataFrame) -> dict:
        """
        Extract weekly and monthly open prices from the DataFrame.

        Requires a DatetimeIndex. Uses the first candle open of the most recent
        week and month present in the data.

        Returns
        -------
        dict with 'weekly_open' (float) and 'monthly_open' (float)
        """
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame must have a DatetimeIndex for weekly_monthly_open.")

        last_date = df.index[-1]

        # Current ISO week and month
        current_week = last_date.isocalendar()[1]
        current_year = last_date.year
        current_month = last_date.month

        week_mask = (
            (df.index.year == current_year)
            & (df.index.isocalendar().week.values == current_week)
        )
        month_mask = (
            (df.index.year == current_year) & (df.index.month == current_month)
        )

        week_df = df[week_mask]
        month_df = df[month_mask]

        weekly_open = float(week_df["open"].iloc[0]) if len(week_df) > 0 else float("nan")
        monthly_open = float(month_df["open"].iloc[0]) if len(month_df) > 0 else float("nan")

        return {"weekly_open": weekly_open, "monthly_open": monthly_open}

    @staticmethod
    def is_near_sr_level(
        price: float,
        levels: List[float],
        tolerance_pips: float = 5,
        pair: str = "EUR_USD",
    ) -> bool:
        """
        Check whether `price` is within `tolerance_pips` of any level in `levels`.

        Parameters
        ----------
        price           : current market price
        levels          : list of S/R price levels
        tolerance_pips  : number of pips defining proximity (default 5)
        pair            : forex pair for pip size calculation

        Returns
        -------
        bool
        """
        pip = _pip_value(pair)
        tolerance = tolerance_pips * pip
        return any(abs(price - level) <= tolerance for level in levels)
