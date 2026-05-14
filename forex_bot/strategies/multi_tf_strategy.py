"""
Multi-Timeframe Confluence Strategy — only trade when 3+ timeframes agree.
"""
import pandas as pd
from typing import Optional
from . import TradeSignal
from indicators.trend import TrendIndicators
from indicators.momentum import MomentumIndicators
from indicators.volatility import VolatilityIndicators
from utils.logger import get_logger

logger = get_logger(__name__)


class MultiTimeframeStrategy:
    name = "multi_tf_strategy"
    required_agreement = 3  # out of 4 timeframes

    def analyze(self, data, pair, current_price, atr, spread_pips=1.5):
        tfs = ["D1", "H4", "H1", "M15"]
        votes = {"BUY": 0, "SELL": 0, "details": {}}

        for tf in tfs:
            if tf not in data or data[tf] is None or len(data[tf]) < 210:
                continue
            bias = self._get_tf_bias(data[tf], current_price)
            votes[bias] += 1 if bias in ("BUY", "SELL") else 0
            votes["details"][tf] = bias

        buy_votes = votes["BUY"]
        sell_votes = votes["SELL"]

        if buy_votes < self.required_agreement and sell_votes < self.required_agreement:
            return None

        direction = "BUY" if buy_votes >= sell_votes else "SELL"
        signal_tf = "H1" if "H1" in data else tfs[-1]
        if signal_tf not in data or data[signal_tf] is None:
            return None

        df = data[signal_tf]
        atr_s = VolatilityIndicators.atr(df, 14)
        cur_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr

        votes_count = buy_votes if direction == "BUY" else sell_votes
        strength = "strong" if votes_count == 4 else "moderate"

        if direction == "BUY":
            sl = current_price - cur_atr * 2.0
            tp1 = current_price + cur_atr * 2.0
            tp2 = current_price + cur_atr * 4.0
            tp3 = current_price + cur_atr * 7.0
        else:
            sl = current_price + cur_atr * 2.0
            tp1 = current_price - cur_atr * 2.0
            tp2 = current_price - cur_atr * 4.0
            tp3 = current_price - cur_atr * 7.0

        return TradeSignal(
            pair=pair, direction=direction, strategy_name=self.name,
            timeframe=signal_tf, entry_price=current_price,
            sl_price=round(sl, 5), tp1_price=round(tp1, 5),
            tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
            indicators={"tf_votes": votes["details"], "agreement": votes_count},
            metadata={"strength": strength, "agreeing_tfs": votes_count},
        )

    def _get_tf_bias(self, df: pd.DataFrame, current_price: float) -> str:
        """Determine directional bias for a single timeframe."""
        try:
            close = df["close"]
            ema50 = TrendIndicators.ema(close, 50)
            ema200 = TrendIndicators.ema(close, 200)
            rsi = MomentumIndicators.rsi(close, 14)
            macd_data = TrendIndicators.macd(close)

            ema50_val = ema50.iloc[-1]
            ema200_val = ema200.iloc[-1]
            rsi_val = rsi.iloc[-1]
            macd_hist = macd_data["histogram"].iloc[-1]

            bull_points = 0
            bear_points = 0

            if current_price > ema50_val:
                bull_points += 1
            else:
                bear_points += 1

            if ema50_val > ema200_val:
                bull_points += 1
            else:
                bear_points += 1

            if rsi_val > 50:
                bull_points += 1
            else:
                bear_points += 1

            if macd_hist > 0:
                bull_points += 1
            else:
                bear_points += 1

            if bull_points > bear_points:
                return "BUY"
            elif bear_points > bull_points:
                return "SELL"
            return "NEUTRAL"
        except Exception:
            return "NEUTRAL"
