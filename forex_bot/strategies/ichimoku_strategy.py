"""
Ichimoku Strategy — Kumo breakout + TK cross + Chikou confirmation.
"""
import pandas as pd
from typing import Optional
from . import TradeSignal
from indicators.trend import TrendIndicators
from indicators.volatility import VolatilityIndicators
from utils.logger import get_logger

logger = get_logger(__name__)


class IchimokuStrategy:
    name = "ichimoku_strategy"
    preferred_timeframes = ["H4", "H1", "D1"]

    def analyze(self, data, pair, current_price, atr, spread_pips=1.5):
        for tf in self.preferred_timeframes:
            if tf not in data or data[tf] is None or len(data[tf]) < 60:
                continue
            signal = self._analyze_tf(data[tf], pair, tf, current_price, atr)
            if signal:
                return signal
        return None

    def _analyze_tf(self, df, pair, tf, current_price, atr):
        ichi = TrendIndicators.ichimoku(df)
        atr_s = VolatilityIndicators.atr(df, 14)
        cur_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr

        tenkan = ichi["tenkan_sen"].iloc[-1]
        kijun = ichi["kijun_sen"].iloc[-1]
        senkou_a = ichi["senkou_a"].iloc[-1]
        senkou_b = ichi["senkou_b"].iloc[-1]
        chikou = ichi["chikou_span"].iloc[-26] if len(ichi["chikou_span"]) > 26 else None

        cloud_top = max(senkou_a, senkou_b)
        cloud_bottom = min(senkou_a, senkou_b)

        # TK cross detection
        prev_tenkan = ichi["tenkan_sen"].iloc[-2]
        prev_kijun = ichi["kijun_sen"].iloc[-2]
        tk_bullish_cross = prev_tenkan <= prev_kijun and tenkan > kijun
        tk_bearish_cross = prev_tenkan >= prev_kijun and tenkan < kijun

        # Conditions count (strong = 4, medium = 3, weak = 2)
        conditions_bull = 0
        conditions_bear = 0

        if current_price > cloud_top:
            conditions_bull += 1
        if current_price < cloud_bottom:
            conditions_bear += 1

        if tk_bullish_cross:
            conditions_bull += 1
        if tk_bearish_cross:
            conditions_bear += 1

        if chikou is not None:
            if chikou > df["close"].iloc[-26]:
                conditions_bull += 1
            elif chikou < df["close"].iloc[-26]:
                conditions_bear += 1

        # Future cloud (next period's cloud direction)
        if len(ichi["senkou_a"]) > 1 and len(ichi["senkou_b"]) > 1:
            future_a = ichi["senkou_a"].iloc[-1]
            future_b = ichi["senkou_b"].iloc[-1]
            if future_a > future_b:
                conditions_bull += 1
            elif future_a < future_b:
                conditions_bear += 1

        if conditions_bull >= 2:
            sl = kijun - cur_atr * 0.5
            tp1 = current_price + cur_atr * 2.0
            tp2 = current_price + cur_atr * 4.0
            tp3 = current_price + cur_atr * 6.0
            strength = "strong" if conditions_bull == 4 else ("medium" if conditions_bull == 3 else "weak")
            return TradeSignal(
                pair=pair, direction="BUY", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                indicators={"tenkan": round(tenkan, 5), "kijun": round(kijun, 5),
                            "cloud_top": round(cloud_top, 5)},
                metadata={"conditions": conditions_bull, "strength": strength},
            )

        if conditions_bear >= 2:
            sl = kijun + cur_atr * 0.5
            tp1 = current_price - cur_atr * 2.0
            tp2 = current_price - cur_atr * 4.0
            tp3 = current_price - cur_atr * 6.0
            strength = "strong" if conditions_bear == 4 else ("medium" if conditions_bear == 3 else "weak")
            return TradeSignal(
                pair=pair, direction="SELL", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                indicators={"tenkan": round(tenkan, 5), "kijun": round(kijun, 5),
                            "cloud_bottom": round(cloud_bottom, 5)},
                metadata={"conditions": conditions_bear, "strength": strength},
            )
        return None
