"""
Chart pattern detection on OHLC price data.

All methods accept a pd.DataFrame with columns: open, high, low, close
and return a list of dicts describing each detected pattern.
"""

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from typing import List, Dict, Any


# --------------------------------------------------------------------------- #
# Internal utilities                                                            #
# --------------------------------------------------------------------------- #

def _local_highs(series: pd.Series, order: int = 5) -> np.ndarray:
    """Return indices of local highs in *series* using a window of *order*."""
    idx = argrelextrema(series.values, np.greater_equal, order=order)[0]
    # Remove consecutive duplicates
    if len(idx) > 1:
        diff = np.diff(idx)
        idx = idx[np.concatenate(([True], diff > 0))]
    return idx


def _local_lows(series: pd.Series, order: int = 5) -> np.ndarray:
    """Return indices of local lows in *series* using a window of *order*."""
    idx = argrelextrema(series.values, np.less_equal, order=order)[0]
    if len(idx) > 1:
        diff = np.diff(idx)
        idx = idx[np.concatenate(([True], diff > 0))]
    return idx


def _linreg_slope(y: np.ndarray) -> float:
    """Return the slope of a least-squares linear fit to *y*."""
    x = np.arange(len(y), dtype=float)
    if len(y) < 2:
        return 0.0
    m, _ = np.polyfit(x, y, 1)
    return float(m)


def _trendline(y: np.ndarray) -> tuple:
    """Return (slope, intercept) of OLS fit."""
    x = np.arange(len(y), dtype=float)
    return tuple(np.polyfit(x, y, 1))


class ChartPatterns:
    """Detect classic chart patterns on OHLC data."""

    # ------------------------------------------------------------------ #
    # Head and Shoulders                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def head_and_shoulders(df: pd.DataFrame, lookback: int = 50) -> List[Dict[str, Any]]:
        """
        Classic Head and Shoulders: left shoulder, higher head, right shoulder
        at approximately the same height as the left shoulder.
        Bearish reversal.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        highs_idx = _local_highs(window["high"], order=max(3, lookback // 10))

        if len(highs_idx) < 3:
            return results

        for i in range(len(highs_idx) - 2):
            ls_i, h_i, rs_i = highs_idx[i], highs_idx[i + 1], highs_idx[i + 2]
            ls = window["high"].iloc[ls_i]
            h = window["high"].iloc[h_i]
            rs = window["high"].iloc[rs_i]

            # Head must be highest
            if h <= ls or h <= rs:
                continue
            # Shoulders approximately equal (within 3%)
            if abs(ls - rs) / h > 0.03:
                continue

            # Neckline: average of the two troughs between shoulders
            trough1 = window["low"].iloc[ls_i:h_i].min()
            trough2 = window["low"].iloc[h_i:rs_i].min()
            neckline = (trough1 + trough2) / 2

            offset = len(df) - lookback
            results.append({
                "type": "head_and_shoulders",
                "direction": -1,
                "neckline": float(neckline),
                "left_shoulder": float(ls),
                "head": float(h),
                "right_shoulder": float(rs),
                "start_idx": int(ls_i + offset),
                "end_idx": int(rs_i + offset),
            })

        return results

    @staticmethod
    def inverse_head_and_shoulders(df: pd.DataFrame, lookback: int = 50) -> List[Dict[str, Any]]:
        """
        Inverse H&S: three troughs where the middle is lowest.
        Bullish reversal.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        lows_idx = _local_lows(window["low"], order=max(3, lookback // 10))

        if len(lows_idx) < 3:
            return results

        for i in range(len(lows_idx) - 2):
            ls_i, h_i, rs_i = lows_idx[i], lows_idx[i + 1], lows_idx[i + 2]
            ls = window["low"].iloc[ls_i]
            h = window["low"].iloc[h_i]
            rs = window["low"].iloc[rs_i]

            if h >= ls or h >= rs:
                continue
            if abs(ls - rs) / abs(h) > 0.03:
                continue

            peak1 = window["high"].iloc[ls_i:h_i].max()
            peak2 = window["high"].iloc[h_i:rs_i].max()
            neckline = (peak1 + peak2) / 2

            offset = len(df) - lookback
            results.append({
                "type": "inverse_head_and_shoulders",
                "direction": 1,
                "neckline": float(neckline),
                "left_shoulder": float(ls),
                "head": float(h),
                "right_shoulder": float(rs),
                "start_idx": int(ls_i + offset),
                "end_idx": int(rs_i + offset),
            })

        return results

    # ------------------------------------------------------------------ #
    # Double / Triple Tops and Bottoms                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def double_top(df: pd.DataFrame, lookback: int = 50, tolerance: float = 0.002) -> List[Dict[str, Any]]:
        """
        Two peaks at approximately the same level with a trough between.
        Bearish reversal.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        highs_idx = _local_highs(window["high"], order=max(3, lookback // 12))

        if len(highs_idx) < 2:
            return results

        offset = len(df) - lookback
        for i in range(len(highs_idx) - 1):
            p1_i, p2_i = highs_idx[i], highs_idx[i + 1]
            p1 = window["high"].iloc[p1_i]
            p2 = window["high"].iloc[p2_i]

            if abs(p1 - p2) / p1 > tolerance:
                continue

            # Trough between the two peaks
            trough = window["low"].iloc[p1_i:p2_i + 1].min()
            # Trough must be meaningfully below peaks
            if (min(p1, p2) - trough) / min(p1, p2) < 0.005:
                continue

            results.append({
                "type": "double_top",
                "direction": -1,
                "resistance": float((p1 + p2) / 2),
                "support": float(trough),
                "peak1": float(p1),
                "peak2": float(p2),
                "start_idx": int(p1_i + offset),
                "end_idx": int(p2_i + offset),
            })

        return results

    @staticmethod
    def double_bottom(df: pd.DataFrame, lookback: int = 50, tolerance: float = 0.002) -> List[Dict[str, Any]]:
        """
        Two troughs at approximately the same level with a peak between.
        Bullish reversal.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        lows_idx = _local_lows(window["low"], order=max(3, lookback // 12))

        if len(lows_idx) < 2:
            return results

        offset = len(df) - lookback
        for i in range(len(lows_idx) - 1):
            t1_i, t2_i = lows_idx[i], lows_idx[i + 1]
            t1 = window["low"].iloc[t1_i]
            t2 = window["low"].iloc[t2_i]

            if abs(t1 - t2) / t1 > tolerance:
                continue

            peak = window["high"].iloc[t1_i:t2_i + 1].max()
            if (peak - max(t1, t2)) / peak < 0.005:
                continue

            results.append({
                "type": "double_bottom",
                "direction": 1,
                "support": float((t1 + t2) / 2),
                "resistance": float(peak),
                "trough1": float(t1),
                "trough2": float(t2),
                "start_idx": int(t1_i + offset),
                "end_idx": int(t2_i + offset),
            })

        return results

    @staticmethod
    def triple_top(df: pd.DataFrame, lookback: int = 80) -> List[Dict[str, Any]]:
        """Three peaks at similar levels. Bearish reversal."""
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        highs_idx = _local_highs(window["high"], order=max(3, lookback // 15))

        if len(highs_idx) < 3:
            return results

        offset = len(df) - lookback
        for i in range(len(highs_idx) - 2):
            p1_i, p2_i, p3_i = highs_idx[i], highs_idx[i + 1], highs_idx[i + 2]
            p1 = window["high"].iloc[p1_i]
            p2 = window["high"].iloc[p2_i]
            p3 = window["high"].iloc[p3_i]
            avg_peak = (p1 + p2 + p3) / 3

            if max(abs(p1 - avg_peak), abs(p2 - avg_peak), abs(p3 - avg_peak)) / avg_peak > 0.01:
                continue

            support = window["low"].iloc[p1_i:p3_i + 1].min()
            results.append({
                "type": "triple_top",
                "direction": -1,
                "resistance": float(avg_peak),
                "support": float(support),
                "start_idx": int(p1_i + offset),
                "end_idx": int(p3_i + offset),
            })

        return results

    @staticmethod
    def triple_bottom(df: pd.DataFrame, lookback: int = 80) -> List[Dict[str, Any]]:
        """Three troughs at similar levels. Bullish reversal."""
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        lows_idx = _local_lows(window["low"], order=max(3, lookback // 15))

        if len(lows_idx) < 3:
            return results

        offset = len(df) - lookback
        for i in range(len(lows_idx) - 2):
            t1_i, t2_i, t3_i = lows_idx[i], lows_idx[i + 1], lows_idx[i + 2]
            t1 = window["low"].iloc[t1_i]
            t2 = window["low"].iloc[t2_i]
            t3 = window["low"].iloc[t3_i]
            avg_trough = (t1 + t2 + t3) / 3

            if max(abs(t1 - avg_trough), abs(t2 - avg_trough), abs(t3 - avg_trough)) / avg_trough > 0.01:
                continue

            resistance = window["high"].iloc[t1_i:t3_i + 1].max()
            results.append({
                "type": "triple_bottom",
                "direction": 1,
                "support": float(avg_trough),
                "resistance": float(resistance),
                "start_idx": int(t1_i + offset),
                "end_idx": int(t3_i + offset),
            })

        return results

    # ------------------------------------------------------------------ #
    # Cup and Handle                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def cup_and_handle(df: pd.DataFrame, lookback: int = 100) -> List[Dict[str, Any]]:
        """
        Cup and Handle: rounded bottom (U-shape) followed by brief consolidation
        that forms a small downward channel before breakout. Bullish.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        cup_len = int(lookback * 0.7)
        handle_len = lookback - cup_len

        cup = window.iloc[:cup_len]
        handle = window.iloc[cup_len:]

        cup_left_high = cup["high"].iloc[:5].max()
        cup_right_high = cup["high"].iloc[-5:].max()
        cup_bottom = cup["low"].min()

        # Cup rims should be approximately equal (within 3%)
        if abs(cup_left_high - cup_right_high) / cup_left_high > 0.03:
            return results

        # Bottom must be meaningfully below rims (>= 5%)
        rim_avg = (cup_left_high + cup_right_high) / 2
        if (rim_avg - cup_bottom) / rim_avg < 0.05:
            return results

        # Handle should trend slightly downward and be shallower than cup
        handle_low = handle["low"].min()
        handle_high = handle["high"].max()
        handle_depth = handle_high - handle_low
        cup_depth = rim_avg - cup_bottom

        if handle_depth > cup_depth * 0.5:
            return results

        # Handle slope negative (downward drift)
        handle_slope = _linreg_slope(handle["close"].values)

        offset = len(df) - lookback
        results.append({
            "type": "cup_and_handle",
            "direction": 1,
            "resistance": float(rim_avg),
            "cup_bottom": float(cup_bottom),
            "handle_low": float(handle_low),
            "target": float(rim_avg + (rim_avg - cup_bottom)),  # measured move
            "start_idx": int(offset),
            "end_idx": int(len(df) - 1),
        })

        return results

    # ------------------------------------------------------------------ #
    # Wedges                                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def rising_wedge(df: pd.DataFrame, lookback: int = 30) -> List[Dict[str, Any]]:
        """
        Rising wedge: higher highs and higher lows but the trendlines converge.
        Bearish signal.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        highs_idx = _local_highs(window["high"], order=max(2, lookback // 8))
        lows_idx = _local_lows(window["low"], order=max(2, lookback // 8))

        if len(highs_idx) < 2 or len(lows_idx) < 2:
            return results

        high_slope, _ = _trendline(window["high"].iloc[highs_idx].values)
        low_slope, _ = _trendline(window["low"].iloc[lows_idx].values)

        if high_slope <= 0 or low_slope <= 0:
            return results
        if low_slope <= high_slope:
            return results  # Lows rising faster → converging: low_slope > high_slope

        offset = len(df) - lookback
        results.append({
            "type": "rising_wedge",
            "direction": -1,
            "high_slope": float(high_slope),
            "low_slope": float(low_slope),
            "start_idx": int(offset),
            "end_idx": int(len(df) - 1),
        })
        return results

    @staticmethod
    def falling_wedge(df: pd.DataFrame, lookback: int = 30) -> List[Dict[str, Any]]:
        """
        Falling wedge: lower highs and lower lows, trendlines converge.
        Bullish signal.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        highs_idx = _local_highs(window["high"], order=max(2, lookback // 8))
        lows_idx = _local_lows(window["low"], order=max(2, lookback // 8))

        if len(highs_idx) < 2 or len(lows_idx) < 2:
            return results

        high_slope, _ = _trendline(window["high"].iloc[highs_idx].values)
        low_slope, _ = _trendline(window["low"].iloc[lows_idx].values)

        if high_slope >= 0 or low_slope >= 0:
            return results
        if high_slope <= low_slope:
            return results  # Highs falling faster → converging: high_slope < low_slope

        offset = len(df) - lookback
        results.append({
            "type": "falling_wedge",
            "direction": 1,
            "high_slope": float(high_slope),
            "low_slope": float(low_slope),
            "start_idx": int(offset),
            "end_idx": int(len(df) - 1),
        })
        return results

    # ------------------------------------------------------------------ #
    # Triangles                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def ascending_triangle(df: pd.DataFrame, lookback: int = 30) -> List[Dict[str, Any]]:
        """
        Ascending triangle: flat resistance, rising support. Bullish.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        highs_idx = _local_highs(window["high"], order=max(2, lookback // 8))
        lows_idx = _local_lows(window["low"], order=max(2, lookback // 8))

        if len(highs_idx) < 2 or len(lows_idx) < 2:
            return results

        high_vals = window["high"].iloc[highs_idx].values
        high_slope, _ = _trendline(high_vals)
        low_slope, _ = _trendline(window["low"].iloc[lows_idx].values)

        # Highs roughly flat (within 0.5% per bar slope), lows rising
        if abs(high_slope) > 0.002 * window["close"].mean():
            return results
        if low_slope <= 0:
            return results

        resistance = float(np.mean(high_vals))
        offset = len(df) - lookback
        results.append({
            "type": "ascending_triangle",
            "direction": 1,
            "resistance": resistance,
            "low_slope": float(low_slope),
            "target": float(resistance + (resistance - window["low"].iloc[lows_idx].mean())),
            "start_idx": int(offset),
            "end_idx": int(len(df) - 1),
        })
        return results

    @staticmethod
    def descending_triangle(df: pd.DataFrame, lookback: int = 30) -> List[Dict[str, Any]]:
        """
        Descending triangle: flat support, falling resistance. Bearish.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        highs_idx = _local_highs(window["high"], order=max(2, lookback // 8))
        lows_idx = _local_lows(window["low"], order=max(2, lookback // 8))

        if len(highs_idx) < 2 or len(lows_idx) < 2:
            return results

        low_vals = window["low"].iloc[lows_idx].values
        high_slope, _ = _trendline(window["high"].iloc[highs_idx].values)
        low_slope, _ = _trendline(low_vals)

        if abs(low_slope) > 0.002 * window["close"].mean():
            return results
        if high_slope >= 0:
            return results

        support = float(np.mean(low_vals))
        offset = len(df) - lookback
        results.append({
            "type": "descending_triangle",
            "direction": -1,
            "support": support,
            "high_slope": float(high_slope),
            "target": float(support - (window["high"].iloc[highs_idx].mean() - support)),
            "start_idx": int(offset),
            "end_idx": int(len(df) - 1),
        })
        return results

    @staticmethod
    def symmetrical_triangle(df: pd.DataFrame, lookback: int = 30) -> List[Dict[str, Any]]:
        """
        Symmetrical triangle: converging highs and lows. Neutral until breakout.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        highs_idx = _local_highs(window["high"], order=max(2, lookback // 8))
        lows_idx = _local_lows(window["low"], order=max(2, lookback // 8))

        if len(highs_idx) < 2 or len(lows_idx) < 2:
            return results

        high_slope, _ = _trendline(window["high"].iloc[highs_idx].values)
        low_slope, _ = _trendline(window["low"].iloc[lows_idx].values)

        # Highs falling, lows rising, roughly symmetric
        if high_slope >= 0 or low_slope <= 0:
            return results
        if abs(high_slope + low_slope) > abs(high_slope) * 0.5:
            return results  # Not symmetric enough

        apex_x = -high_slope / (low_slope - high_slope) * lookback
        offset = len(df) - lookback
        results.append({
            "type": "symmetrical_triangle",
            "direction": 0,
            "high_slope": float(high_slope),
            "low_slope": float(low_slope),
            "apex_bars_ahead": float(max(0.0, float(lookback) - apex_x)),
            "start_idx": int(offset),
            "end_idx": int(len(df) - 1),
        })
        return results

    # ------------------------------------------------------------------ #
    # Flags and Pennants                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def bull_flag(df: pd.DataFrame, lookback: int = 20) -> List[Dict[str, Any]]:
        """
        Bull flag: strong upward pole followed by brief downward-sloping channel.
        Bullish continuation.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        pole_len = max(5, lookback // 3)
        flag_len = lookback - pole_len

        pole = window.iloc[:pole_len]
        flag = window.iloc[pole_len:]

        pole_move = (pole["close"].iloc[-1] - pole["close"].iloc[0]) / pole["close"].iloc[0]
        if pole_move < 0.01:  # at least 1% move
            return results

        flag_slope = _linreg_slope(flag["close"].values)
        # Flag should slope downward (consolidation)
        if flag_slope >= 0:
            return results

        flag_range = flag["high"].max() - flag["low"].min()
        pole_range = pole["high"].max() - pole["low"].min()
        if flag_range > pole_range * 0.5:
            return results  # Flag too deep

        offset = len(df) - lookback
        results.append({
            "type": "bull_flag",
            "direction": 1,
            "pole_gain": float(pole_move),
            "pole_high": float(pole["high"].max()),
            "flag_slope": float(flag_slope),
            "target": float(pole["high"].max() + pole_range),
            "start_idx": int(offset),
            "end_idx": int(len(df) - 1),
        })
        return results

    @staticmethod
    def bear_flag(df: pd.DataFrame, lookback: int = 20) -> List[Dict[str, Any]]:
        """
        Bear flag: strong downward pole followed by brief upward-sloping channel.
        Bearish continuation.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        pole_len = max(5, lookback // 3)
        flag_len = lookback - pole_len

        pole = window.iloc[:pole_len]
        flag = window.iloc[pole_len:]

        pole_move = (pole["close"].iloc[0] - pole["close"].iloc[-1]) / pole["close"].iloc[0]
        if pole_move < 0.01:
            return results

        flag_slope = _linreg_slope(flag["close"].values)
        if flag_slope <= 0:
            return results

        flag_range = flag["high"].max() - flag["low"].min()
        pole_range = pole["high"].max() - pole["low"].min()
        if flag_range > pole_range * 0.5:
            return results

        offset = len(df) - lookback
        results.append({
            "type": "bear_flag",
            "direction": -1,
            "pole_drop": float(pole_move),
            "pole_low": float(pole["low"].min()),
            "flag_slope": float(flag_slope),
            "target": float(pole["low"].min() - pole_range),
            "start_idx": int(offset),
            "end_idx": int(len(df) - 1),
        })
        return results

    @staticmethod
    def pennant(df: pd.DataFrame, lookback: int = 20) -> List[Dict[str, Any]]:
        """
        Pennant: strong directional move followed by symmetrical triangle.
        Continuation signal.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        pole_len = max(5, lookback // 3)

        pole = window.iloc[:pole_len]
        consol = window.iloc[pole_len:]

        pole_move = pole["close"].iloc[-1] - pole["close"].iloc[0]
        direction = 1 if pole_move > 0 else -1

        if abs(pole_move) / pole["close"].iloc[0] < 0.01:
            return results

        # Consolidation: converging highs and lows
        if len(consol) < 4:
            return results
        highs_idx = _local_highs(consol["high"], order=2)
        lows_idx = _local_lows(consol["low"], order=2)

        if len(highs_idx) < 2 or len(lows_idx) < 2:
            return results

        h_slope, _ = _trendline(consol["high"].iloc[highs_idx].values)
        l_slope, _ = _trendline(consol["low"].iloc[lows_idx].values)

        if h_slope >= 0 or l_slope <= 0:
            return results

        offset = len(df) - lookback
        results.append({
            "type": "pennant",
            "direction": direction,
            "pole_move": float(pole_move),
            "start_idx": int(offset),
            "end_idx": int(len(df) - 1),
        })
        return results

    # ------------------------------------------------------------------ #
    # Rectangle                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def rectangle(df: pd.DataFrame, lookback: int = 30, tolerance: float = 0.002) -> List[Dict[str, Any]]:
        """
        Rectangle: price oscillating between horizontal support and resistance.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        highs_idx = _local_highs(window["high"], order=max(2, lookback // 8))
        lows_idx = _local_lows(window["low"], order=max(2, lookback // 8))

        if len(highs_idx) < 2 or len(lows_idx) < 2:
            return results

        high_vals = window["high"].iloc[highs_idx].values
        low_vals = window["low"].iloc[lows_idx].values

        high_std = np.std(high_vals) / np.mean(high_vals)
        low_std = np.std(low_vals) / np.mean(low_vals)

        if high_std > tolerance or low_std > tolerance:
            return results

        resistance = float(np.mean(high_vals))
        support = float(np.mean(low_vals))

        if (resistance - support) / support < 0.002:
            return results

        offset = len(df) - lookback
        results.append({
            "type": "rectangle",
            "direction": 0,
            "resistance": resistance,
            "support": support,
            "channel_height": float(resistance - support),
            "start_idx": int(offset),
            "end_idx": int(len(df) - 1),
        })
        return results

    # ------------------------------------------------------------------ #
    # Rounding Bottom                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def rounding_bottom(df: pd.DataFrame, lookback: int = 60) -> List[Dict[str, Any]]:
        """
        Rounding bottom (saucer): gradual U-shaped price reversal. Bullish.
        Detect by fitting a parabola to the lows and checking upward concavity.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        x = np.arange(len(window), dtype=float)
        y = window["low"].values

        coeffs = np.polyfit(x, y, 2)
        a, b, c = coeffs

        # Upward parabola: a > 0
        if a <= 0:
            return results

        # Vertex (bottom of cup) should be roughly in the middle
        vertex_x = -b / (2 * a)
        if not (lookback * 0.2 < vertex_x < lookback * 0.8):
            return results

        # R-squared of fit
        y_pred = np.polyval(coeffs, x)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        if r2 < 0.6:
            return results

        offset = len(df) - lookback
        results.append({
            "type": "rounding_bottom",
            "direction": 1,
            "bottom_price": float(np.polyval(coeffs, vertex_x)),
            "r_squared": float(r2),
            "start_idx": int(offset),
            "end_idx": int(len(df) - 1),
        })
        return results

    # ------------------------------------------------------------------ #
    # Diamond Pattern                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def diamond_pattern(df: pd.DataFrame, lookback: int = 40) -> List[Dict[str, Any]]:
        """
        Diamond: price widens then narrows forming a diamond shape. Reversal signal.
        Approximated by fitting widening and narrowing wedge halves.
        """
        results: List[Dict] = []
        if len(df) < lookback:
            return results

        window = df.tail(lookback).reset_index(drop=True)
        half = lookback // 2

        first_half = window.iloc[:half]
        second_half = window.iloc[half:]

        # First half: highs rising, lows falling (expanding)
        fh_high_slope = _linreg_slope(first_half["high"].values)
        fh_low_slope = _linreg_slope(first_half["low"].values)

        # Second half: highs falling, lows rising (contracting)
        sh_high_slope = _linreg_slope(second_half["high"].values)
        sh_low_slope = _linreg_slope(second_half["low"].values)

        if fh_high_slope <= 0 or fh_low_slope >= 0:
            return results
        if sh_high_slope >= 0 or sh_low_slope <= 0:
            return results

        # Current close relative to first half midpoint determines direction
        mid_price = (window["high"].max() + window["low"].min()) / 2
        cur_close = window["close"].iloc[-1]
        direction = -1 if cur_close > mid_price else 1

        offset = len(df) - lookback
        results.append({
            "type": "diamond_pattern",
            "direction": direction,
            "high_peak": float(window["high"].max()),
            "low_trough": float(window["low"].min()),
            "start_idx": int(offset),
            "end_idx": int(len(df) - 1),
        })
        return results

    # ------------------------------------------------------------------ #
    # Aggregate                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def detect_all(df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Run all chart pattern detectors and return a combined list."""
        cp = ChartPatterns
        all_results: List[Dict] = []
        detectors = [
            cp.head_and_shoulders,
            cp.inverse_head_and_shoulders,
            cp.double_top,
            cp.double_bottom,
            cp.triple_top,
            cp.triple_bottom,
            cp.cup_and_handle,
            cp.rising_wedge,
            cp.falling_wedge,
            cp.ascending_triangle,
            cp.descending_triangle,
            cp.symmetrical_triangle,
            cp.bull_flag,
            cp.bear_flag,
            cp.pennant,
            cp.rectangle,
            cp.rounding_bottom,
            cp.diamond_pattern,
        ]
        for fn in detectors:
            try:
                all_results.extend(fn(df))
            except Exception:
                pass
        return all_results
