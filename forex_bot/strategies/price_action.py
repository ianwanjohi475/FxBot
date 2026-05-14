"""
Price Action Strategy — pure candlestick + S/R decisions.
Entry: key S/R level + confirming candlestick pattern.
Primary timeframes: H1, H4.
"""
import pandas as pd
import numpy as np
from typing import Optional
from . import TradeSignal
from indicators.support_resistance import SupportResistance
from indicators.trend import TrendIndicators
from indicators.volatility import VolatilityIndicators
from patterns.candlestick import CandlestickPatterns
from utils.logger import get_logger

logger = get_logger(__name__)


class PriceActionStrategy:
    name = "price_action"
    preferred_timeframes = ["H1", "H4"]

    def analyze(
        self,
        data: dict,
        pair: str,
        current_price: float,
        atr: float,
        spread_pips: float = 1.5,
    ) -> Optional[TradeSignal]:
        for tf in self.preferred_timeframes:
            if tf not in data or data[tf] is None or len(data[tf]) < 50:
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
        # Calculate S/R levels
        sr = SupportResistance.dynamic_sr(df, lookback=50)
        supports = sr.get("support", [])
        resistances = sr.get("resistance", [])

        # ATR
        atr_series = VolatilityIndicators.atr(df, 14)
        current_atr = atr_series.iloc[-1] if not pd.isna(atr_series.iloc[-1]) else atr

        # Candlestick pattern on last 3 candles
        patterns = CandlestickPatterns.detect_all(df.tail(10))

        bullish_patterns = [
            k for k, v in patterns.items()
            if isinstance(v, pd.Series) and not v.empty and v.iloc[-1] == 1
        ]
        bearish_patterns = [
            k for k, v in patterns.items()
            if isinstance(v, pd.Series) and not v.empty and v.iloc[-1] == -1
        ]

        close = current_price
        tolerance = current_atr * 0.5

        # --- Bullish setup ---
        for sup in supports:
            if abs(close - sup) <= tolerance and bullish_patterns:
                sl = sup - current_atr * 1.5
                tp1 = close + current_atr * 1.5
                tp2 = close + current_atr * 3.0
                tp3 = close + current_atr * 4.5
                pattern_name = bullish_patterns[0]
                logger.debug(f"[PriceAction] BUY signal on {pair} {tf} near support {sup:.5f}")
                return TradeSignal(
                    pair=pair,
                    direction="BUY",
                    strategy_name=self.name,
                    timeframe=tf,
                    entry_price=close,
                    sl_price=round(sl, 5),
                    tp1_price=round(tp1, 5),
                    tp2_price=round(tp2, 5),
                    tp3_price=round(tp3, 5),
                    pattern_detected=pattern_name,
                    indicators={"atr": round(current_atr, 5), "support": round(sup, 5)},
                    metadata={"sr_type": "support", "patterns": bullish_patterns},
                )

        # --- Bearish setup ---
        for res in resistances:
            if abs(close - res) <= tolerance and bearish_patterns:
                sl = res + current_atr * 1.5
                tp1 = close - current_atr * 1.5
                tp2 = close - current_atr * 3.0
                tp3 = close - current_atr * 4.5
                pattern_name = bearish_patterns[0]
                logger.debug(f"[PriceAction] SELL signal on {pair} {tf} near resistance {res:.5f}")
                return TradeSignal(
                    pair=pair,
                    direction="SELL",
                    strategy_name=self.name,
                    timeframe=tf,
                    entry_price=close,
                    sl_price=round(sl, 5),
                    tp1_price=round(tp1, 5),
                    tp2_price=round(tp2, 5),
                    tp3_price=round(tp3, 5),
                    pattern_detected=pattern_name,
                    indicators={"atr": round(current_atr, 5), "resistance": round(res, 5)},
                    metadata={"sr_type": "resistance", "patterns": bearish_patterns},
                )
        return None
