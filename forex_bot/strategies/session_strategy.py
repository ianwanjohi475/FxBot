"""
Session Trading Strategy — London open play, NY open play, Asian range.
"""
import pandas as pd
from datetime import datetime
from typing import Optional
import pytz
from . import TradeSignal
from indicators.volatility import VolatilityIndicators
from indicators.momentum import MomentumIndicators
from patterns.smc import SmartMoneyConcepts
from utils.logger import get_logger

logger = get_logger(__name__)

SESSION_PAIRS = {
    "london": ["GBP_USD", "EUR_USD", "EUR_GBP", "GBP_JPY"],
    "ny": ["EUR_USD", "GBP_USD", "USD_CAD", "USD_JPY"],
    "asian": ["USD_JPY", "AUD_USD", "NZD_USD"],
}

AVOID_ASIAN = ["GBP_USD", "GBP_JPY"]


class SessionStrategy:
    name = "session_strategy"
    preferred_timeframes = ["M15", "H1"]

    def analyze(self, data, pair, current_price, atr,
                current_time: datetime = None, spread_pips=1.5):
        if current_time is None:
            current_time = datetime.now(tz=pytz.utc)

        est = pytz.timezone("America/New_York")
        local = current_time.astimezone(est)
        hour = local.hour

        # London open 2-5am EST
        if 2 <= hour < 5 and pair in SESSION_PAIRS["london"]:
            return self._london_play(data, pair, current_price, atr)

        # NY open 7-10am EST
        if 7 <= hour < 10 and pair in SESSION_PAIRS["ny"]:
            return self._ny_play(data, pair, current_price, atr)

        # Asian range trade (not GBP)
        if (22 <= hour or hour < 7) and pair in SESSION_PAIRS["asian"] and pair not in AVOID_ASIAN:
            return self._asian_range(data, pair, current_price, atr)

        return None

    def _london_play(self, data, pair, current_price, atr):
        tf = "M15"
        if tf not in data or data[tf] is None or len(data[tf]) < 20:
            return None
        df = data[tf]

        # Detect Judas swing
        session_open = df["close"].iloc[-5]  # Approx open level
        judas = SmartMoneyConcepts.detect_judas_swing(df, session_open)

        atr_s = VolatilityIndicators.atr(df, 14)
        cur_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr

        if judas["detected"]:
            direction = judas["direction"]
            if direction == "BUY":
                sl = current_price - cur_atr * 1.5
                tp1 = current_price + cur_atr * 1.5
                tp2 = current_price + cur_atr * 3.0
                tp3 = current_price + cur_atr * 5.0
            else:
                sl = current_price + cur_atr * 1.5
                tp1 = current_price - cur_atr * 1.5
                tp2 = current_price - cur_atr * 3.0
                tp3 = current_price - cur_atr * 5.0

            return TradeSignal(
                pair=pair, direction=direction, strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                metadata={"session": "london_open", "play": "judas_reversal"},
            )
        return None

    def _ny_play(self, data, pair, current_price, atr):
        tf = "M15"
        if tf not in data or data[tf] is None or len(data[tf]) < 20:
            return None
        df = data[tf]

        atr_s = VolatilityIndicators.atr(df, 14)
        cur_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr
        rsi = MomentumIndicators.rsi(df["close"], 14).iloc[-1]

        # NY momentum bias: if price above last 4-hour high -> buy momentum
        h4_high = df["high"].tail(16).max()  # approx 4h on M15
        h4_low = df["low"].tail(16).min()

        if current_price > h4_high and rsi > 50:
            sl = h4_high - cur_atr * 0.5
            tp1 = current_price + cur_atr * 2
            tp2 = current_price + cur_atr * 4
            tp3 = current_price + cur_atr * 6
            return TradeSignal(
                pair=pair, direction="BUY", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                metadata={"session": "ny_open", "play": "momentum_breakout"},
            )

        if current_price < h4_low and rsi < 50:
            sl = h4_low + cur_atr * 0.5
            tp1 = current_price - cur_atr * 2
            tp2 = current_price - cur_atr * 4
            tp3 = current_price - cur_atr * 6
            return TradeSignal(
                pair=pair, direction="SELL", strategy_name=self.name,
                timeframe=tf, entry_price=current_price,
                sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                metadata={"session": "ny_open", "play": "momentum_breakdown"},
            )
        return None

    def _asian_range(self, data, pair, current_price, atr):
        tf = "H1"
        if tf not in data or data[tf] is None or len(data[tf]) < 10:
            return None
        df = data[tf]

        atr_s = VolatilityIndicators.atr(df, 14)
        cur_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr

        asian_high = df["high"].tail(8).max()
        asian_low = df["low"].tail(8).min()
        range_mid = (asian_high + asian_low) / 2
        range_size = asian_high - asian_low

        # Trade range reversals if range is tight
        if range_size < cur_atr * 2:
            if current_price >= asian_high * 0.999:
                sl = asian_high + cur_atr
                tp1 = range_mid
                tp2 = asian_low
                tp3 = asian_low - cur_atr
                return TradeSignal(
                    pair=pair, direction="SELL", strategy_name=self.name,
                    timeframe=tf, entry_price=current_price,
                    sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                    tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                    metadata={"session": "asian", "play": "range_sell"},
                )
            if current_price <= asian_low * 1.001:
                sl = asian_low - cur_atr
                tp1 = range_mid
                tp2 = asian_high
                tp3 = asian_high + cur_atr
                return TradeSignal(
                    pair=pair, direction="BUY", strategy_name=self.name,
                    timeframe=tf, entry_price=current_price,
                    sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                    tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                    metadata={"session": "asian", "play": "range_buy"},
                )
        return None
