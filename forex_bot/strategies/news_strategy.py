"""
News Trading Strategy — trade the retest after a news spike.
"""
import pandas as pd
from typing import Optional
from . import TradeSignal
from indicators.volatility import VolatilityIndicators
from utils.logger import get_logger

logger = get_logger(__name__)

SPIKE_MIN_PIPS = 15.0


class NewsStrategy:
    name = "news_strategy"
    preferred_timeframes = ["M5", "M15"]

    def __init__(self):
        self.recent_spikes = {}  # pair -> spike info

    def record_spike(self, pair: str, direction: str, spike_price: float,
                     pre_news_price: float):
        """Call this after a news event spike is detected."""
        self.recent_spikes[pair] = {
            "direction": direction,
            "spike_price": spike_price,
            "pre_news_price": pre_news_price,
            "retest_pending": True,
        }

    def analyze(self, data, pair, current_price, atr, spread_pips=1.5):
        spike = self.recent_spikes.get(pair)
        if not spike or not spike.get("retest_pending"):
            # Auto-detect spike from recent data
            spike = self._detect_spike(data, pair)
            if spike:
                self.recent_spikes[pair] = spike
            else:
                return None

        for tf in self.preferred_timeframes:
            if tf not in data or data[tf] is None or len(data[tf]) < 5:
                continue
            signal = self._check_retest(data[tf], pair, tf, current_price, atr, spike)
            if signal:
                self.recent_spikes[pair]["retest_pending"] = False
                return signal
        return None

    def _detect_spike(self, data, pair):
        tf = "M5"
        if tf not in data or data[tf] is None or len(data[tf]) < 5:
            return None
        df = data[tf]
        last = df.iloc[-1]
        prev = df.iloc[-2]

        pip_mult = 100 if "JPY" in pair else 10000
        candle_size = abs(last["close"] - last["open"]) * pip_mult

        if candle_size >= SPIKE_MIN_PIPS:
            direction = "BUY" if last["close"] > last["open"] else "SELL"
            return {
                "direction": direction,
                "spike_price": last["close"],
                "pre_news_price": prev["close"],
                "retest_pending": True,
                "spike_candle_idx": len(df) - 1,
            }
        return None

    def _check_retest(self, df, pair, tf, current_price, atr, spike):
        atr_s = VolatilityIndicators.atr(df, 14)
        cur_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr

        spike_price = spike["spike_price"]
        direction = spike["direction"]
        tolerance = cur_atr * 0.5

        if direction == "BUY" and abs(current_price - spike_price) <= tolerance:
            sl = spike_price - cur_atr * 1.5
            recent_high = df["high"].tail(20).max()
            tp1 = current_price + cur_atr * 1.5
            tp2 = current_price + cur_atr * 3.0
            tp3 = recent_high
            return TradeSignal(
                pair=pair, direction="BUY", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                metadata={"news_trade": True, "spike_direction": "bullish",
                          "spike_level": round(spike_price, 5)},
            )

        if direction == "SELL" and abs(current_price - spike_price) <= tolerance:
            sl = spike_price + cur_atr * 1.5
            recent_low = df["low"].tail(20).min()
            tp1 = current_price - cur_atr * 1.5
            tp2 = current_price - cur_atr * 3.0
            tp3 = recent_low
            return TradeSignal(
                pair=pair, direction="SELL", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                metadata={"news_trade": True, "spike_direction": "bearish",
                          "spike_level": round(spike_price, 5)},
            )
        return None
