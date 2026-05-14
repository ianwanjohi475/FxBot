"""
Scalping Strategy — M1/M5 with EMA + fast Stochastic + candlestick confirmation.
"""
import pandas as pd
from typing import Optional
from . import TradeSignal
from indicators.trend import TrendIndicators
from indicators.momentum import MomentumIndicators
from indicators.volatility import VolatilityIndicators
from patterns.candlestick import CandlestickPatterns
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_SPREAD_PIPS = 1.5


class ScalpingStrategy:
    name = "scalping"
    preferred_timeframes = ["M1", "M5"]

    def analyze(self, data, pair, current_price, atr, spread_pips=1.0):
        if spread_pips > MAX_SPREAD_PIPS:
            return None

        for tf in self.preferred_timeframes:
            if tf not in data or data[tf] is None or len(data[tf]) < 30:
                continue
            signal = self._analyze_tf(data[tf], pair, tf, current_price, atr)
            if signal:
                return signal
        return None

    def _analyze_tf(self, df, pair, tf, current_price, atr):
        close = df["close"]
        ema9 = TrendIndicators.ema(close, 9)
        ema21 = TrendIndicators.ema(close, 21)
        stoch_fast = MomentumIndicators.stochastic_fast(df, 5, 3)

        atr_s = VolatilityIndicators.atr(df, 14)
        cur_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr

        # Scalping ATR multiples are tight
        sl_mult = 1.5
        tp_mult = 1.5

        k = stoch_fast["k"].iloc[-1]
        d = stoch_fast["d"].iloc[-1]
        ema9_val = ema9.iloc[-1]
        ema21_val = ema21.iloc[-1]

        patterns = CandlestickPatterns.detect_all(df.tail(5))
        bullish_p = [k2 for k2, v in patterns.items()
                     if isinstance(v, pd.Series) and not v.empty and v.iloc[-1] == 1]
        bearish_p = [k2 for k2, v in patterns.items()
                     if isinstance(v, pd.Series) and not v.empty and v.iloc[-1] == -1]

        # Bullish scalp: EMA9 > EMA21, stoch oversold crossing up, bullish candle
        if ema9_val > ema21_val and k < 25 and k > d and bullish_p:
            sl = current_price - cur_atr * sl_mult
            tp1 = current_price + cur_atr * tp_mult
            tp2 = current_price + cur_atr * tp_mult * 1.5
            tp3 = current_price + cur_atr * tp_mult * 2.0
            return TradeSignal(
                pair=pair, direction="BUY", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                pattern_detected=bullish_p[0] if bullish_p else None,
                indicators={"stoch_k": round(k, 2), "ema9": round(ema9_val, 5),
                            "ema21": round(ema21_val, 5)},
                metadata={"scalp_tf": tf},
            )

        # Bearish scalp: EMA9 < EMA21, stoch overbought crossing down, bearish candle
        if ema9_val < ema21_val and k > 75 and k < d and bearish_p:
            sl = current_price + cur_atr * sl_mult
            tp1 = current_price - cur_atr * tp_mult
            tp2 = current_price - cur_atr * tp_mult * 1.5
            tp3 = current_price - cur_atr * tp_mult * 2.0
            return TradeSignal(
                pair=pair, direction="SELL", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                pattern_detected=bearish_p[0] if bearish_p else None,
                indicators={"stoch_k": round(k, 2), "ema9": round(ema9_val, 5),
                            "ema21": round(ema21_val, 5)},
                metadata={"scalp_tf": tf},
            )
        return None
