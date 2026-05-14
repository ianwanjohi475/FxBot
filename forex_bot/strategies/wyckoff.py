"""
Wyckoff Method — Accumulation (buy LPS) and Distribution (sell LPSY) detection.
"""
import pandas as pd
import numpy as np
from typing import Optional
from . import TradeSignal
from indicators.volume import VolumeIndicators
from indicators.volatility import VolatilityIndicators
from indicators.momentum import MomentumIndicators
from utils.logger import get_logger

logger = get_logger(__name__)


class WyckoffStrategy:
    name = "wyckoff"
    preferred_timeframes = ["H4", "D1"]

    def analyze(self, data, pair, current_price, atr, spread_pips=1.5):
        for tf in self.preferred_timeframes:
            if tf not in data or data[tf] is None or len(data[tf]) < 80:
                continue
            signal = self._analyze_tf(data[tf], pair, tf, current_price, atr)
            if signal:
                return signal
        return None

    def _analyze_tf(self, df, pair, tf, current_price, atr):
        phase = self._detect_phase(df)
        atr_s = VolatilityIndicators.atr(df, 14)
        cur_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr

        if phase == "accumulation_lps":
            sl = df["low"].tail(20).min() - cur_atr
            tp1 = current_price + cur_atr * 2
            tp2 = current_price + cur_atr * 4
            tp3 = current_price + cur_atr * 7
            return TradeSignal(
                pair=pair, direction="BUY", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                indicators={"phase": "accumulation_lps"},
                metadata={"wyckoff_phase": "accumulation"},
            )

        if phase == "distribution_lpsy":
            sl = df["high"].tail(20).max() + cur_atr
            tp1 = current_price - cur_atr * 2
            tp2 = current_price - cur_atr * 4
            tp3 = current_price - cur_atr * 7
            return TradeSignal(
                pair=pair, direction="SELL", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                indicators={"phase": "distribution_lpsy"},
                metadata={"wyckoff_phase": "distribution"},
            )
        return None

    def _detect_phase(self, df: pd.DataFrame) -> Optional[str]:
        """Simplified Wyckoff phase detection using price/volume characteristics."""
        window = df.tail(80)
        vol = window["volume"]
        close = window["close"]

        # Accumulation: declining volume on down bars, increasing volume on up bars
        # Distribution: increasing volume on up bars failing to make new highs
        vol_sma = vol.rolling(20).mean()
        price_trend = close.rolling(20).mean()

        # Last 20 candles
        recent = window.tail(20)
        recent_range_high = recent["high"].max()
        recent_range_low = recent["low"].min()
        range_mid = (recent_range_high + recent_range_low) / 2

        current_close = close.iloc[-1]
        current_vol = vol.iloc[-1]
        avg_vol = vol_sma.iloc[-1] if not pd.isna(vol_sma.iloc[-1]) else vol.mean()

        # Spring (LPS): price dips below range low on low volume, closes back in range
        recent_low_prior = window["low"].iloc[-40:-20].min()
        if (close.iloc[-2] < recent_low_prior and
                current_close > recent_low_prior and
                current_vol < avg_vol * 0.8):
            return "accumulation_lps"

        # Upthrust (LPSY): price spikes above range high on high volume, closes back in range
        recent_high_prior = window["high"].iloc[-40:-20].max()
        if (close.iloc[-2] > recent_high_prior and
                current_close < recent_high_prior and
                current_vol > avg_vol * 1.5):
            return "distribution_lpsy"

        return None
