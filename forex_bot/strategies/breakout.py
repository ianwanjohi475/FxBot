"""
Breakout Strategy — range breakout confirmed by volume spike.
Also includes Donchian Channel breakouts.
"""
import pandas as pd
import numpy as np
from typing import Optional
from . import TradeSignal
from indicators.volatility import VolatilityIndicators
from indicators.volume import VolumeIndicators
from indicators.trend import TrendIndicators
from utils.logger import get_logger

logger = get_logger(__name__)


class BreakoutStrategy:
    name = "breakout"
    preferred_timeframes = ["H1", "H4", "M15"]

    def analyze(
        self,
        data: dict,
        pair: str,
        current_price: float,
        atr: float,
        spread_pips: float = 1.5,
    ) -> Optional[TradeSignal]:
        for tf in self.preferred_timeframes:
            if tf not in data or data[tf] is None or len(data[tf]) < 30:
                continue
            df = data[tf]
            signal = self._analyze_tf(df, pair, tf, current_price, atr)
            if signal:
                return signal
        return None

    def _analyze_tf(
        self,
        df: pd.DataFrame,
        pair: str,
        tf: str,
        current_price: float,
        atr: float,
    ) -> Optional[TradeSignal]:
        atr_s = VolatilityIndicators.atr(df, 14)
        current_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr

        dc = VolatilityIndicators.donchian_channel(df, 20)
        upper = dc["upper"].iloc[-2]
        lower = dc["lower"].iloc[-2]
        current_close = df["close"].iloc[-1]

        vol_spike = VolumeIndicators.detect_volume_spike(df["volume"], 20, 1.8)
        is_spike = vol_spike.iloc[-1] if not vol_spike.empty else False

        range_size = upper - lower
        if range_size <= 0:
            return None

        # Bullish breakout
        if current_close > upper and is_spike:
            sl = lower
            tp1 = current_price + range_size * 0.5
            tp2 = current_price + range_size * 1.0
            tp3 = current_price + range_size * 1.5
            return TradeSignal(
                pair=pair,
                direction="BUY",
                strategy_name=self.name,
                timeframe=tf,
                entry_price=current_price,
                sl_price=round(sl, 5),
                tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5),
                tp3_price=round(tp3, 5),
                indicators={
                    "dc_upper": round(upper, 5),
                    "dc_lower": round(lower, 5),
                    "atr": round(current_atr, 5),
                },
                metadata={"breakout_type": "donchian_upper", "range_size": range_size},
            )

        # Bearish breakout
        if current_close < lower and is_spike:
            sl = upper
            tp1 = current_price - range_size * 0.5
            tp2 = current_price - range_size * 1.0
            tp3 = current_price - range_size * 1.5
            return TradeSignal(
                pair=pair,
                direction="SELL",
                strategy_name=self.name,
                timeframe=tf,
                entry_price=current_price,
                sl_price=round(sl, 5),
                tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5),
                tp3_price=round(tp3, 5),
                indicators={
                    "dc_upper": round(upper, 5),
                    "dc_lower": round(lower, 5),
                    "atr": round(current_atr, 5),
                },
                metadata={"breakout_type": "donchian_lower", "range_size": range_size},
            )
        return None
