"""
Trend Following Strategy.
Entry: EMA 9/21 cross on M15/H1 + ADX > 25 + price above/below EMA 200.
"""
import pandas as pd
from typing import Optional
from . import TradeSignal
from indicators.trend import TrendIndicators
from indicators.momentum import MomentumIndicators
from indicators.volatility import VolatilityIndicators
from utils.logger import get_logger

logger = get_logger(__name__)


class TrendFollowingStrategy:
    name = "trend_following"
    preferred_timeframes = ["H1", "M15"]

    def analyze(
        self,
        data: dict,
        pair: str,
        current_price: float,
        atr: float,
        spread_pips: float = 1.5,
    ) -> Optional[TradeSignal]:
        for tf in self.preferred_timeframes:
            if tf not in data or data[tf] is None or len(data[tf]) < 210:
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
        close = df["close"]

        ema9 = TrendIndicators.ema(close, 9)
        ema21 = TrendIndicators.ema(close, 21)
        ema50 = TrendIndicators.ema(close, 50)
        ema200 = TrendIndicators.ema(close, 200)

        adx_data = TrendIndicators.adx(df, 14)
        adx = adx_data["adx"].iloc[-1]
        plus_di  = adx_data["plus_di"].iloc[-1]
        minus_di = adx_data["minus_di"].iloc[-1]

        macd_data = TrendIndicators.macd(close)
        macd_hist = macd_data["histogram"]

        atr_series = VolatilityIndicators.atr(df, 14)
        current_atr = atr_series.iloc[-1] if not pd.isna(atr_series.iloc[-1]) else atr

        # EMA crossover
        cross = TrendIndicators.detect_ema_crossover(df, 9, 21)
        last_cross = cross.iloc[-1]

        # ── Trend strength gate ───────────────────────────────────────────────
        # ADX must be ≥ 27 (professional threshold for a confirmed strong trend).
        # ADX 20-26 = weak/developing trend — skip these entirely.
        # Also require the directional index to agree with trade direction.
        if adx < 27:
            return None  # Not a strong enough trend — wait for confirmation

        above_200 = current_price > ema200.iloc[-1]
        below_200 = current_price < ema200.iloc[-1]

        # Bullish: golden cross + above EMA200 + positive MACD + DI+ leads DI-
        if last_cross == 1 and above_200 and macd_hist.iloc[-1] > 0 and plus_di > minus_di:
            sl = ema50.iloc[-1] - current_atr * 0.5
            tp1 = current_price + current_atr * 1.5
            tp2 = current_price + current_atr * 3.0
            tp3 = current_price + current_atr * 5.0
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
                    "ema9": round(ema9.iloc[-1], 5),
                    "ema21": round(ema21.iloc[-1], 5),
                    "ema200": round(ema200.iloc[-1], 5),
                    "adx": round(adx, 2),
                    "plus_di": round(plus_di, 2),
                    "minus_di": round(minus_di, 2),
                    "macd_hist": round(macd_hist.iloc[-1], 6),
                },
                metadata={"cross": "golden", "adx": adx},
            )

        # Bearish: death cross + below EMA200 + negative MACD + DI- leads DI+
        if last_cross == -1 and below_200 and macd_hist.iloc[-1] < 0 and minus_di > plus_di:
            sl = ema50.iloc[-1] + current_atr * 0.5
            tp1 = current_price - current_atr * 1.5
            tp2 = current_price - current_atr * 3.0
            tp3 = current_price - current_atr * 5.0
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
                    "ema9": round(ema9.iloc[-1], 5),
                    "ema21": round(ema21.iloc[-1], 5),
                    "ema200": round(ema200.iloc[-1], 5),
                    "adx": round(adx, 2),
                    "plus_di": round(plus_di, 2),
                    "minus_di": round(minus_di, 2),
                    "macd_hist": round(macd_hist.iloc[-1], 6),
                },
                metadata={"cross": "death", "adx": adx},
            )
        return None
