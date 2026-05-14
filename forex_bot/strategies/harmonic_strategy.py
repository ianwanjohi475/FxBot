"""
Harmonic Pattern Trading Strategy.
Entry: completed D-leg in PRZ + RSI divergence or candlestick confirmation.
"""
import pandas as pd
from typing import Optional
from . import TradeSignal
from patterns.harmonic import HarmonicPatterns
from indicators.momentum import MomentumIndicators
from indicators.volatility import VolatilityIndicators
from patterns.candlestick import CandlestickPatterns
from utils.logger import get_logger

logger = get_logger(__name__)


class HarmonicStrategy:
    name = "harmonic_strategy"
    preferred_timeframes = ["H4", "H1", "D1"]

    def analyze(self, data, pair, current_price, atr, spread_pips=1.5):
        for tf in self.preferred_timeframes:
            if tf not in data or data[tf] is None or len(data[tf]) < 50:
                continue
            signal = self._analyze_tf(data[tf], pair, tf, current_price, atr)
            if signal:
                return signal
        return None

    def _analyze_tf(self, df, pair, tf, current_price, atr):
        patterns = HarmonicPatterns.detect_all(df)
        if not patterns:
            return None

        atr_s = VolatilityIndicators.atr(df, 14)
        cur_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr
        rsi = MomentumIndicators.rsi(df["close"], 14)
        rsi_val = rsi.iloc[-1]

        candle_patterns = CandlestickPatterns.detect_all(df.tail(5))
        confirm_bull = any(
            isinstance(v, pd.Series) and not v.empty and v.iloc[-1] == 1
            for v in candle_patterns.values()
        )
        confirm_bear = any(
            isinstance(v, pd.Series) and not v.empty and v.iloc[-1] == -1
            for v in candle_patterns.values()
        )

        for pat in reversed(patterns):
            direction = pat["direction"]
            prz = pat.get("prz", current_price)

            # Price must be in PRZ
            if abs(current_price - prz) > cur_atr * 2:
                continue

            if direction == "BUY" and (confirm_bull or rsi_val < 40):
                xa = abs(pat.get("a", prz) - pat.get("x", prz))
                sl = prz - cur_atr * 1.5
                tp1 = prz + xa * 0.382
                tp2 = prz + xa * 0.618
                tp3 = prz + xa * 1.0
                return TradeSignal(
                    pair=pair, direction="BUY", strategy_name=self.name,
                    timeframe=tf, entry_price=current_price,
                    sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                    tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                    pattern_detected=pat["pattern"],
                    indicators={"rsi": round(rsi_val, 2), "prz": round(prz, 5)},
                    metadata={"harmonic_pattern": pat["pattern"], "confidence": pat.get("confidence", 0.7)},
                )

            if direction == "SELL" and (confirm_bear or rsi_val > 60):
                xa = abs(pat.get("a", prz) - pat.get("x", prz))
                sl = prz + cur_atr * 1.5
                tp1 = prz - xa * 0.382
                tp2 = prz - xa * 0.618
                tp3 = prz - xa * 1.0
                return TradeSignal(
                    pair=pair, direction="SELL", strategy_name=self.name,
                    timeframe=tf, entry_price=current_price,
                    sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                    tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                    pattern_detected=pat["pattern"],
                    indicators={"rsi": round(rsi_val, 2), "prz": round(prz, 5)},
                    metadata={"harmonic_pattern": pat["pattern"], "confidence": pat.get("confidence", 0.7)},
                )
        return None
