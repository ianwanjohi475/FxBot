"""
Grid Strategy — for ranging markets only (ADX < 20 + BB squeeze).
Places grid orders above and below current price.
"""
import pandas as pd
from typing import Optional, List
from . import TradeSignal
from indicators.trend import TrendIndicators
from indicators.volatility import VolatilityIndicators
from utils.logger import get_logger

logger = get_logger(__name__)


class GridStrategy:
    name = "grid"
    preferred_timeframes = ["H1", "H4"]
    grid_levels = 5
    grid_spacing_atr_mult = 0.5

    def __init__(self):
        self.active_grids = {}  # pair -> grid state

    def analyze(self, data, pair, current_price, atr, spread_pips=1.5):
        for tf in self.preferred_timeframes:
            if tf not in data or data[tf] is None or len(data[tf]) < 30:
                continue
            signal = self._analyze_tf(data[tf], pair, tf, current_price, atr)
            if signal:
                return signal
        return None

    def _analyze_tf(self, df, pair, tf, current_price, atr):
        adx_data = TrendIndicators.adx(df, 14)
        adx_val = adx_data["adx"].iloc[-1]

        # Only grid in ranging conditions
        if adx_val > 20:
            return None

        bb = VolatilityIndicators.bollinger_bands(df["close"], 20, 2)
        squeeze = VolatilityIndicators.detect_bb_squeeze(bb)
        is_squeeze = squeeze.iloc[-1] if not squeeze.empty else False

        if not is_squeeze:
            return None

        atr_s = VolatilityIndicators.atr(df, 14)
        cur_atr = atr_s.iloc[-1] if not pd.isna(atr_s.iloc[-1]) else atr
        spacing = cur_atr * self.grid_spacing_atr_mult

        # Find range bounds
        range_high = df["high"].tail(20).max()
        range_low = df["low"].tail(20).min()

        # Only enter if price is near range midpoint
        range_mid = (range_high + range_low) / 2
        if abs(current_price - range_mid) > cur_atr:
            return None

        # Check if we're near a grid level
        grid_state = self.active_grids.get(pair, {})
        grid_base = grid_state.get("base", current_price)

        # Find next unfilled grid level above (sell) and below (buy)
        for i in range(1, self.grid_levels + 1):
            level_above = grid_base + spacing * i
            level_below = grid_base - spacing * i

            if abs(current_price - level_above) < spacing * 0.1:
                # At a sell level
                sl = level_above + spacing
                tp1 = level_above - spacing
                tp2 = grid_base
                tp3 = level_below
                return TradeSignal(
                    pair=pair, direction="SELL", strategy_name=self.name,
                    timeframe=tf, entry_price=current_price,
                    sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                    tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                    indicators={"adx": round(adx_val, 2), "grid_level": i},
                    metadata={"grid_type": "sell_grid", "range_mid": round(range_mid, 5)},
                )

            if abs(current_price - level_below) < spacing * 0.1:
                # At a buy level
                sl = level_below - spacing
                tp1 = level_below + spacing
                tp2 = grid_base
                tp3 = level_above
                return TradeSignal(
                    pair=pair, direction="BUY", strategy_name=self.name,
                    timeframe=tf, entry_price=current_price,
                    sl_price=round(sl, 5), tp1_price=round(tp1, 5),
                    tp2_price=round(tp2, 5), tp3_price=round(tp3, 5),
                    indicators={"adx": round(adx_val, 2), "grid_level": i},
                    metadata={"grid_type": "buy_grid", "range_mid": round(range_mid, 5)},
                )
        return None

    def setup_grid(self, pair: str, base_price: float, spacing: float):
        """Initialize a grid around a price."""
        self.active_grids[pair] = {"base": base_price, "spacing": spacing}
        logger.info(f"[Grid] Set up grid for {pair} at {base_price} spacing {spacing}")

    def clear_grid(self, pair: str):
        if pair in self.active_grids:
            del self.active_grids[pair]
