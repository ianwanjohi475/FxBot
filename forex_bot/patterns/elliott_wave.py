"""Elliott Wave detection for impulse (1-2-3-4-5) and corrective (A-B-C) waves."""
import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from typing import List, Dict, Optional


class ElliottWave:

    @staticmethod
    def _find_pivots(df: pd.DataFrame, order: int = 5) -> pd.DataFrame:
        highs = argrelextrema(df["high"].values, np.greater, order=order)[0]
        lows = argrelextrema(df["low"].values, np.less, order=order)[0]
        pivots = []
        for i in highs:
            pivots.append({"idx": i, "type": "H", "price": df["high"].iloc[i]})
        for i in lows:
            pivots.append({"idx": i, "type": "L", "price": df["low"].iloc[i]})
        return pd.DataFrame(pivots).sort_values("idx").reset_index(drop=True)

    @staticmethod
    def _wave_valid_impulse(w1, w2, w3, w4, w5, is_bullish: bool) -> bool:
        """Validate Elliott Wave impulse rules."""
        # Rule 1: Wave 2 does not retrace more than 100% of wave 1
        w1_len = abs(w2[0] - w1[0])
        w2_retrace = abs(w2[1] - w2[0]) / w1_len if w1_len else 0
        if w2_retrace > 1.0:
            return False

        # Rule 2: Wave 3 is never the shortest impulse wave
        w1_move = abs(w1[1] - w1[0])
        w3_move = abs(w3[1] - w3[0])
        w5_move = abs(w5[1] - w5[0])
        if w3_move < w1_move and w3_move < w5_move:
            return False

        # Rule 3: Wave 4 does not overlap wave 1 territory
        if is_bullish:
            if w4[1] < w1[1]:  # Wave 4 dips below top of wave 1
                return False
        else:
            if w4[1] > w1[1]:
                return False

        return True

    @classmethod
    def detect_impulse_wave(cls, df: pd.DataFrame, lookback: int = 100) -> List[Dict]:
        """Detect 5-wave impulse patterns."""
        results = []
        sub_df = df.tail(lookback).reset_index(drop=True)
        pivots = cls._find_pivots(sub_df, order=5)

        if len(pivots) < 6:
            return results

        # Try bullish impulse: L-H-L-H-L-H
        # Try bearish impulse: H-L-H-L-H-L
        for is_bullish in [True, False]:
            seq = ["L", "H", "L", "H", "L", "H"] if is_bullish else ["H", "L", "H", "L", "H", "L"]
            for i in range(len(pivots) - 5):
                pts = pivots.iloc[i : i + 6]
                if list(pts["type"]) != seq:
                    continue
                prices = list(pts["price"])
                # Waves as (start, end) tuples
                w1 = (prices[0], prices[1])
                w2 = (prices[1], prices[2])
                w3 = (prices[2], prices[3])
                w4 = (prices[3], prices[4])
                w5 = (prices[4], prices[5])

                if cls._wave_valid_impulse(w1, w2, w3, w4, w5, is_bullish):
                    results.append({
                        "type": "impulse",
                        "direction": "BUY" if is_bullish else "SELL",
                        "waves": {
                            "1": w1, "2": w2, "3": w3, "4": w4, "5": w5
                        },
                        "wave_indices": list(pts["idx"]),
                        "current_wave": "5",
                        "confidence": 0.75,
                    })
        return results

    @classmethod
    def detect_corrective_wave(cls, df: pd.DataFrame, lookback: int = 50) -> List[Dict]:
        """Detect ABC corrective waves."""
        results = []
        sub_df = df.tail(lookback).reset_index(drop=True)
        pivots = cls._find_pivots(sub_df, order=3)

        if len(pivots) < 3:
            return results

        for i in range(len(pivots) - 2):
            pts = pivots.iloc[i : i + 3]
            types = list(pts["type"])
            prices = list(pts["price"])

            # Bullish correction: H-L-H (A down, B up, C down) -> buy at C
            # Bearish correction: L-H-L (A up, B down, C up) -> sell at C
            is_correction_down = types == ["H", "L", "H"]
            is_correction_up = types == ["L", "H", "L"]

            if is_correction_down or is_correction_up:
                a_start, b, c = prices
                wave_a = abs(b - a_start)
                wave_c = abs(c - b)
                if wave_a == 0:
                    continue
                c_ratio = wave_c / wave_a

                if 0.618 <= c_ratio <= 1.618:
                    direction = "BUY" if is_correction_down else "SELL"
                    results.append({
                        "type": "corrective",
                        "direction": direction,
                        "waves": {
                            "A": (a_start, b),
                            "B": (b, c),
                            "C_complete": c,
                        },
                        "wave_indices": list(pts["idx"]),
                        "c_ratio": round(c_ratio, 3),
                        "confidence": 0.65,
                    })
        return results

    @staticmethod
    def label_waves(df: pd.DataFrame, waves: List[Dict]) -> pd.DataFrame:
        """Add wave labels to DataFrame."""
        df = df.copy()
        df["wave_label"] = ""
        for wave in waves:
            if wave["type"] == "impulse":
                for label, indices in zip(
                    ["1", "2", "3", "4", "5"], wave.get("wave_indices", [])
                ):
                    if indices < len(df):
                        df.loc[indices, "wave_label"] = label
            elif wave["type"] == "corrective":
                for label, idx in zip(["A", "B", "C"], wave.get("wave_indices", [])):
                    if idx < len(df):
                        df.loc[idx, "wave_label"] = label
        return df

    @classmethod
    def get_trading_signal(cls, waves: List[Dict]) -> Dict:
        """Determine best trading opportunity from detected waves."""
        if not waves:
            return {"signal": None}

        # Prefer impulse waves
        impulse_waves = [w for w in waves if w["type"] == "impulse"]
        corrective_waves = [w for w in waves if w["type"] == "corrective"]

        if impulse_waves:
            wave = impulse_waves[-1]
            current = wave.get("current_wave", "5")
            direction = wave["direction"]
            if current in ["2", "4"]:
                return {
                    "signal": direction,
                    "wave_count": current,
                    "entry_reason": f"End of wave {current} correction — wave {int(current)+1} expected",
                    "confidence": wave["confidence"],
                }

        if corrective_waves:
            wave = corrective_waves[-1]
            return {
                "signal": wave["direction"],
                "wave_count": "C",
                "entry_reason": "End of ABC correction",
                "confidence": wave["confidence"],
            }

        return {"signal": None}
