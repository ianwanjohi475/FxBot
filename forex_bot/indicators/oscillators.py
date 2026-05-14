"""
Oscillator indicators implemented in pure pandas/numpy (no ta-lib dependency).
All methods are static and operate on standard OHLCV DataFrames or Series.
"""

import numpy as np
import pandas as pd


class Oscillators:
    """Collection of oscillator-type technical indicators."""

    @staticmethod
    def demarker(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        DeMarker indicator.

        DeMax[i] = max(high[i] - high[i-1], 0)
        DeMin[i] = max(low[i-1] - low[i], 0)
        DM[i]    = SMA(DeMax, period) / (SMA(DeMax, period) + SMA(DeMin, period))

        Returns
        -------
        pd.Series in [0, 1]
        """
        high = df["high"]
        low = df["low"]

        de_max = (high - high.shift(1)).clip(lower=0)
        de_min = (low.shift(1) - low).clip(lower=0)

        sma_de_max = de_max.rolling(window=period).mean()
        sma_de_min = de_min.rolling(window=period).mean()

        denom = sma_de_max + sma_de_min
        dm = sma_de_max / denom.replace(0, np.nan)
        return dm.rename("demarker")

    @staticmethod
    def ultimate_oscillator(
        df: pd.DataFrame, p1: int = 7, p2: int = 14, p3: int = 28
    ) -> pd.Series:
        """
        Ultimate Oscillator (Larry Williams).

        Buying Pressure (BP) = close - min(low, prev_close)
        True Range (TR)      = max(high, prev_close) - min(low, prev_close)
        Average(n)           = sum(BP, n) / sum(TR, n)
        UO                   = 100 * (4*Avg1 + 2*Avg2 + 1*Avg3) / (4+2+1)

        Returns
        -------
        pd.Series in [0, 100]
        """
        close = df["close"]
        high = df["high"]
        low = df["low"]
        prev_close = close.shift(1)

        true_low = pd.concat([low, prev_close], axis=1).min(axis=1)
        true_high = pd.concat([high, prev_close], axis=1).max(axis=1)

        bp = close - true_low
        tr = true_high - true_low

        avg1 = bp.rolling(p1).sum() / tr.rolling(p1).sum().replace(0, np.nan)
        avg2 = bp.rolling(p2).sum() / tr.rolling(p2).sum().replace(0, np.nan)
        avg3 = bp.rolling(p3).sum() / tr.rolling(p3).sum().replace(0, np.nan)

        uo = 100 * (4 * avg1 + 2 * avg2 + avg3) / 7
        return uo.rename("ultimate_oscillator")

    @staticmethod
    def awesome_oscillator(
        df: pd.DataFrame, fast: int = 5, slow: int = 34
    ) -> pd.Series:
        """
        Awesome Oscillator (Bill Williams).

        Midpoint = (high + low) / 2
        AO       = SMA(midpoint, fast) - SMA(midpoint, slow)

        Returns
        -------
        pd.Series
        """
        midpoint = (df["high"] + df["low"]) / 2
        ao = (
            midpoint.rolling(window=fast).mean()
            - midpoint.rolling(window=slow).mean()
        )
        return ao.rename("awesome_oscillator")

    @staticmethod
    def ac_oscillator(df: pd.DataFrame) -> pd.Series:
        """
        Accelerator/Decelerator Oscillator (Bill Williams).

        AC = AO - SMA(AO, 5)

        Returns
        -------
        pd.Series
        """
        ao = Oscillators.awesome_oscillator(df)
        ac = ao - ao.rolling(window=5).mean()
        return ac.rename("ac_oscillator")

    @staticmethod
    def detect_ao_zero_cross(ao: pd.Series) -> pd.Series:
        """
        Detect when the Awesome Oscillator crosses the zero line.

        Returns
        -------
        pd.Series: 1=crossed above zero, -1=crossed below zero, 0=no cross
        """
        above_zero = ao > 0
        cross = above_zero.astype(int).diff()

        result = pd.Series(0, index=ao.index, dtype=int)
        result[cross == 1] = 1    # crossed from below to above zero
        result[cross == -1] = -1  # crossed from above to below zero
        return result.rename("ao_zero_cross")

    @staticmethod
    def detect_ao_twin_peaks(ao: pd.Series) -> pd.Series:
        """
        Detect AO Twin Peaks pattern.

        Bullish Twin Peaks  ( 1): two consecutive troughs both below zero,
                                   second trough is HIGHER than the first (divergence up).
        Bearish Twin Peaks (-1): two consecutive peaks both above zero,
                                   second peak is LOWER than the first (divergence down).

        The signal is placed at the bar following the second peak/trough.

        Returns
        -------
        pd.Series: 1=bullish, -1=bearish, 0=none
        """
        result = pd.Series(0, index=ao.index, dtype=int)
        ao_arr = ao.values
        n = len(ao_arr)

        for i in range(2, n):
            if np.isnan(ao_arr[i]) or np.isnan(ao_arr[i - 1]) or np.isnan(ao_arr[i - 2]):
                continue

            # Look for local extremes: i-1 is a trough or peak
            is_trough = ao_arr[i - 1] < ao_arr[i - 2] and ao_arr[i - 1] < ao_arr[i]
            is_peak = ao_arr[i - 1] > ao_arr[i - 2] and ao_arr[i - 1] > ao_arr[i]

            if is_trough and ao_arr[i - 1] < 0:
                # Find the most recent prior trough below zero
                for j in range(i - 3, 0, -1):
                    if np.isnan(ao_arr[j]):
                        break
                    prior_is_trough = ao_arr[j] < ao_arr[j - 1] and ao_arr[j] < ao_arr[j + 1]
                    if prior_is_trough and ao_arr[j] < 0:
                        # Second trough higher than first -> bullish twin peaks
                        if ao_arr[i - 1] > ao_arr[j]:
                            result.iloc[i] = 1
                        break

            elif is_peak and ao_arr[i - 1] > 0:
                # Find the most recent prior peak above zero
                for j in range(i - 3, 0, -1):
                    if np.isnan(ao_arr[j]):
                        break
                    prior_is_peak = ao_arr[j] > ao_arr[j - 1] and ao_arr[j] > ao_arr[j + 1]
                    if prior_is_peak and ao_arr[j] > 0:
                        # Second peak lower than first -> bearish twin peaks
                        if ao_arr[i - 1] < ao_arr[j]:
                            result.iloc[i] = -1
                        break

        return result.rename("ao_twin_peaks")
