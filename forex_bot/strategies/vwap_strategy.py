"""
VWAP Strategy — fade extreme deviations from VWAP, trade VWAP reclaims.
"""
import pandas as pd
from typing import Optional
from . import TradeSignal
from indicators.volume import VolumeIndicators
from indicators.volatility import VolatilityIndicators
from indicators.momentum import MomentumIndicators
from utils.logger import get_logger

logger = get_logger(__name__)


class VWAPStrategy:
    name = "vwap_strategy"
    preferred_timeframes = ["M15", "H1"]

    def analyze(self, data, pair, current_price, atr, spread_pips=1.5):
        for tf in self.preferred_timeframes:
            if tf not in data or data[tf] is None or len(data[tf]) < 30:
                continue
            signal = self._analyze_tf(data[tf], pair, tf, current_price, atr)
            if signal:
                return signal
        return None

    def _analyze_tf(self, df, pair, tf, current_price, atr):
        vwap = VolumeIndicators.vwap(df)
        rsi = MomentumIndicators.rsi(df["close"], 14)
        atr_s = VolatilityIndicators.atr(df, 14)
        cur_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr

        vwap_val = vwap.iloc[-1]
        if pd.isna(vwap_val) or vwap_val == 0:
            return None

        deviation_pct = (current_price - vwap_val) / vwap_val
        rsi_val = rsi.iloc[-1]

        # Fade extreme: price > 0.5% above VWAP, RSI > 65
        if deviation_pct > 0.005 and rsi_val > 65:
            sl = current_price + cur_atr * 1.5
            tp1 = vwap_val
            tp2 = vwap_val - cur_atr
            tp3 = vwap_val - cur_atr * 2
            return TradeSignal(
                pair=pair, direction="SELL", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                indicators={"vwap": round(vwap_val, 5), "rsi": round(rsi_val, 2),
                            "deviation_pct": round(deviation_pct * 100, 3)},
                metadata={"trade_type": "fade_above_vwap"},
            )

        # Fade extreme: price < 0.5% below VWAP, RSI < 35
        if deviation_pct < -0.005 and rsi_val < 35:
            sl = current_price - cur_atr * 1.5
            tp1 = vwap_val
            tp2 = vwap_val + cur_atr
            tp3 = vwap_val + cur_atr * 2
            return TradeSignal(
                pair=pair, direction="BUY", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                indicators={"vwap": round(vwap_val, 5), "rsi": round(rsi_val, 2),
                            "deviation_pct": round(deviation_pct * 100, 3)},
                metadata={"trade_type": "fade_below_vwap"},
            )

        # VWAP reclaim: price was below, now closes above
        prev_close = df["close"].iloc[-2]
        curr_close = df["close"].iloc[-1]
        if prev_close < vwap_val and curr_close > vwap_val:
            sl = vwap_val - cur_atr
            recent_high = df["high"].tail(20).max()
            tp1 = current_price + cur_atr * 1.5
            tp2 = current_price + cur_atr * 3.0
            tp3 = recent_high
            return TradeSignal(
                pair=pair, direction="BUY", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                indicators={"vwap": round(vwap_val, 5)},
                metadata={"trade_type": "vwap_reclaim_bullish"},
            )

        # VWAP reclaim bearish
        if prev_close > vwap_val and curr_close < vwap_val:
            sl = vwap_val + cur_atr
            recent_low = df["low"].tail(20).min()
            tp1 = current_price - cur_atr * 1.5
            tp2 = current_price - cur_atr * 3.0
            tp3 = recent_low
            return TradeSignal(
                pair=pair, direction="SELL", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                indicators={"vwap": round(vwap_val, 5)},
                metadata={"trade_type": "vwap_reclaim_bearish"},
            )
        return None
