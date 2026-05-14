"""
Mean Reversion Strategy — Bollinger Band extremes + RSI + Stochastic confluence.
"""
import pandas as pd
from typing import Optional
from . import TradeSignal
from indicators.volatility import VolatilityIndicators
from indicators.momentum import MomentumIndicators
from utils.logger import get_logger

logger = get_logger(__name__)


class MeanReversionStrategy:
    name = "mean_reversion"
    preferred_timeframes = ["M15", "H1"]

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

    def _analyze_tf(self, df, pair, tf, current_price, atr):
        close = df["close"]
        bb = VolatilityIndicators.bollinger_bands(close, 20, 2)
        squeeze = VolatilityIndicators.detect_bb_squeeze(bb)
        rsi = MomentumIndicators.rsi(close, 14)
        stoch = MomentumIndicators.stochastic(df, 14, 3, 3)

        atr_s = VolatilityIndicators.atr(df, 14)
        current_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr

        upper = bb["upper"].iloc[-1]
        lower = bb["lower"].iloc[-1]
        mid = bb["middle"].iloc[-1]
        rsi_val = rsi.iloc[-1]
        stoch_k = stoch["k"].iloc[-1]

        # BB squeeze was active (low volatility consolidation)
        was_squeeze = squeeze.iloc[-3:-1].any() if len(squeeze) >= 3 else False

        # Bullish mean reversion: price at/below lower band, RSI < 35, Stoch < 25
        if current_price <= lower and rsi_val < 35 and stoch_k < 25:
            sl = lower - current_atr * 1.2
            tp1 = mid
            tp2 = upper * 0.98
            tp3 = upper
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
                indicators={"rsi": round(rsi_val, 2), "stoch_k": round(stoch_k, 2),
                            "bb_lower": round(lower, 5), "bb_mid": round(mid, 5)},
                metadata={"squeeze_prior": bool(was_squeeze)},
            )

        # Bearish mean reversion: price at/above upper band, RSI > 65, Stoch > 75
        if current_price >= upper and rsi_val > 65 and stoch_k > 75:
            sl = upper + current_atr * 1.2
            tp1 = mid
            tp2 = lower * 1.02
            tp3 = lower
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
                indicators={"rsi": round(rsi_val, 2), "stoch_k": round(stoch_k, 2),
                            "bb_upper": round(upper, 5), "bb_mid": round(mid, 5)},
                metadata={"squeeze_prior": bool(was_squeeze)},
            )
        return None
