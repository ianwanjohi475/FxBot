"""
Momentum Strategy — MACD + RSI alignment + volume.
"""
import pandas as pd
from typing import Optional
from . import TradeSignal
from indicators.trend import TrendIndicators
from indicators.momentum import MomentumIndicators
from indicators.volatility import VolatilityIndicators
from indicators.volume import VolumeIndicators
from utils.logger import get_logger

logger = get_logger(__name__)


class MomentumStrategy:
    name = "momentum"
    preferred_timeframes = ["H1", "M15"]

    def analyze(self, data, pair, current_price, atr, spread_pips=1.5):
        for tf in self.preferred_timeframes:
            if tf not in data or data[tf] is None or len(data[tf]) < 30:
                continue
            signal = self._analyze_tf(data[tf], pair, tf, current_price, atr)
            if signal:
                return signal
        return None

    def _analyze_tf(self, df, pair, tf, current_price, atr):
        close = df["close"]
        macd_data = TrendIndicators.macd(close)
        rsi = MomentumIndicators.rsi(close, 14)
        roc = MomentumIndicators.roc(close, 12)
        ema200 = TrendIndicators.ema(close, 200)
        vol_spike = VolumeIndicators.detect_volume_spike(df["volume"], 20, 1.5)

        atr_s = VolatilityIndicators.atr(df, 14)
        cur_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr

        macd_cross = TrendIndicators.detect_macd_crossover(
            macd_data["macd"], macd_data["signal"]
        )
        last_cross = macd_cross.iloc[-1]
        rsi_val = rsi.iloc[-1]
        roc_val = roc.iloc[-1]
        vol_ok = vol_spike.iloc[-1] if not vol_spike.empty else False
        above_200 = current_price > ema200.iloc[-1]
        below_200 = current_price < ema200.iloc[-1]

        # RSI in neutral zone (not overbought/oversold) for momentum
        rsi_neutral = 40 <= rsi_val <= 60

        if last_cross == 1 and rsi_neutral and above_200 and roc_val > 0:
            sl = current_price - cur_atr * 2.0
            tp1 = current_price + cur_atr * 2.0
            tp2 = current_price + cur_atr * 4.0
            tp3 = current_price + cur_atr * 6.0
            return TradeSignal(
                pair=pair, direction="BUY", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                indicators={"rsi": round(rsi_val, 2), "roc": round(roc_val, 4),
                            "macd": round(macd_data["macd"].iloc[-1], 6)},
                metadata={"volume_spike": bool(vol_ok)},
            )

        if last_cross == -1 and rsi_neutral and below_200 and roc_val < 0:
            sl = current_price + cur_atr * 2.0
            tp1 = current_price - cur_atr * 2.0
            tp2 = current_price - cur_atr * 4.0
            tp3 = current_price - cur_atr * 6.0
            return TradeSignal(
                pair=pair, direction="SELL", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                indicators={"rsi": round(rsi_val, 2), "roc": round(roc_val, 4),
                            "macd": round(macd_data["macd"].iloc[-1], 6)},
                metadata={"volume_spike": bool(vol_ok)},
            )
        return None
