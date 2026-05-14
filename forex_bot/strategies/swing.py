"""
Swing Trading Strategy — H4/D1 multi-day holds.
Entry: D1 trend + H4 pullback to 50% Fib + bullish/bearish pattern + RSI.
"""
import pandas as pd
from typing import Optional
from . import TradeSignal
from indicators.trend import TrendIndicators
from indicators.momentum import MomentumIndicators
from indicators.volatility import VolatilityIndicators
from indicators.support_resistance import SupportResistance
from patterns.candlestick import CandlestickPatterns
from utils.logger import get_logger

logger = get_logger(__name__)


class SwingStrategy:
    name = "swing"
    preferred_timeframes = ["H4", "D1"]

    def analyze(self, data, pair, current_price, atr, spread_pips=1.5):
        # Need both H4 and D1
        if "H4" not in data or "D1" not in data:
            return None
        if data["H4"] is None or len(data["H4"]) < 50:
            return None
        if data["D1"] is None or len(data["D1"]) < 60:
            return None
        return self._analyze(data, pair, current_price, atr)

    def _analyze(self, data, pair, current_price, atr):
        d1 = data["D1"]
        h4 = data["H4"]

        # D1 trend
        d1_ema50 = TrendIndicators.ema(d1["close"], 50)
        d1_ema200 = TrendIndicators.ema(d1["close"], 200)
        d1_bullish = d1["close"].iloc[-1] > d1_ema50.iloc[-1] > d1_ema200.iloc[-1]
        d1_bearish = d1["close"].iloc[-1] < d1_ema50.iloc[-1] < d1_ema200.iloc[-1]

        if not d1_bullish and not d1_bearish:
            return None

        # H4 RSI
        rsi_h4 = MomentumIndicators.rsi(h4["close"], 14)
        rsi_val = rsi_h4.iloc[-1]

        atr_s = VolatilityIndicators.atr(h4, 14)
        cur_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr

        # Fibonacci 50% of last H4 swing
        h4_high = h4["high"].tail(50).max()
        h4_low = h4["low"].tail(50).min()
        fib50 = (h4_high + h4_low) / 2
        fib382 = h4_high - (h4_high - h4_low) * 0.382
        fib618 = h4_high - (h4_high - h4_low) * 0.618

        # Candlestick patterns on H4
        patterns = CandlestickPatterns.detect_all(h4.tail(5))
        bullish_p = [k for k, v in patterns.items()
                     if isinstance(v, pd.Series) and not v.empty and v.iloc[-1] == 1]
        bearish_p = [k for k, v in patterns.items()
                     if isinstance(v, pd.Series) and not v.empty and v.iloc[-1] == -1]

        # Bullish swing: D1 bullish trend, H4 pulled back to 50-61.8% Fib, RSI < 45
        if d1_bullish and fib618 <= current_price <= fib50 and rsi_val < 45 and bullish_p:
            sl = h4_low - cur_atr * 0.5
            tp1 = h4_high * 0.95
            tp2 = h4_high
            tp3 = h4_high + (h4_high - h4_low) * 0.382
            return TradeSignal(
                pair=pair, direction="BUY", strategy_name=self.name,
                timeframe="H4", entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                pattern_detected=bullish_p[0] if bullish_p else None,
                indicators={"rsi_h4": round(rsi_val, 2), "fib50": round(fib50, 5),
                            "h4_high": round(h4_high, 5), "h4_low": round(h4_low, 5)},
                metadata={"d1_trend": "bullish"},
            )

        # Bearish swing
        fib50_bear = (h4_high + h4_low) / 2
        fib382_bear = h4_low + (h4_high - h4_low) * 0.382
        fib618_bear = h4_low + (h4_high - h4_low) * 0.618

        if d1_bearish and fib50_bear <= current_price <= fib618_bear and rsi_val > 55 and bearish_p:
            sl = h4_high + cur_atr * 0.5
            tp1 = h4_low * 1.05
            tp2 = h4_low
            tp3 = h4_low - (h4_high - h4_low) * 0.382
            return TradeSignal(
                pair=pair, direction="SELL", strategy_name=self.name,
                timeframe="H4", entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                pattern_detected=bearish_p[0] if bearish_p else None,
                indicators={"rsi_h4": round(rsi_val, 2)},
                metadata={"d1_trend": "bearish"},
            )
        return None
