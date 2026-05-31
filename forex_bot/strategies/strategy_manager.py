"""
Strategy Manager — orchestrates all 20 strategies and collects signals.
"""
import pandas as pd
from typing import List, Optional, Dict
from datetime import datetime
import pytz

from . import TradeSignal
from .price_action import PriceActionStrategy
from .smc_strategy import SMCStrategy
from .trend_following import TrendFollowingStrategy
from .breakout import BreakoutStrategy
from .mean_reversion import MeanReversionStrategy
from .momentum import MomentumStrategy
from .scalping import ScalpingStrategy
from .swing import SwingStrategy
from .ichimoku_strategy import IchimokuStrategy
from .vwap_strategy import VWAPStrategy
from .wyckoff import WyckoffStrategy
from .harmonic_strategy import HarmonicStrategy
from .session_strategy import SessionStrategy
from .news_strategy import NewsStrategy
from .multi_tf_strategy import MultiTimeframeStrategy
from .carry_trade import CarryTradeStrategy
from .grid import GridStrategy
from utils.logger import get_logger

logger = get_logger(__name__)


class StrategyManager:
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.strategies = {
            "price_action": PriceActionStrategy(),
            "smc_strategy": SMCStrategy(),
            "trend_following": TrendFollowingStrategy(),
            "breakout": BreakoutStrategy(),
            "mean_reversion": MeanReversionStrategy(),
            "momentum": MomentumStrategy(),
            "scalping": ScalpingStrategy(),
            "swing": SwingStrategy(),
            "ichimoku_strategy": IchimokuStrategy(),
            "vwap_strategy": VWAPStrategy(),
            "wyckoff": WyckoffStrategy(),
            "harmonic_strategy": HarmonicStrategy(),
            "session_strategy": SessionStrategy(),
            "news_strategy": NewsStrategy(),
            "multi_tf_strategy": MultiTimeframeStrategy(),
            "carry_trade": CarryTradeStrategy(),
            "grid": GridStrategy(),
        }
        self.weights: Dict[str, float] = {k: 1.0 for k in self.strategies}
        self.paused: Dict[str, bool] = {k: False for k in self.strategies}
        self._load_weights_from_config()

    def _load_weights_from_config(self):
        strategy_cfg = self.config.get("strategy_weights", {})
        for name, weight in strategy_cfg.items():
            if name in self.weights:
                self.weights[name] = float(weight)

    def analyze_all(
        self,
        data: dict,
        pair: str,
        current_price: float,
        spread_pips: float = 1.5,
        session: str = "london",
        news_events: list = None,
        current_time: datetime = None,
    ) -> List[TradeSignal]:
        if current_time is None:
            current_time = datetime.now(tz=pytz.utc)
        if news_events is None:
            news_events = []

        # Calculate ATR from H1 or best available TF
        atr = self._get_atr(data)

        signals: List[TradeSignal] = []

        for name, strategy in self.strategies.items():
            if self.paused.get(name, False):
                continue
            if self.weights.get(name, 1.0) < 0.1:
                continue
            try:
                kwargs = dict(data=data, pair=pair, current_price=current_price, atr=atr,
                              spread_pips=spread_pips)
                # Inject extra kwargs for strategies that accept them
                if hasattr(strategy, "analyze"):
                    import inspect
                    params = inspect.signature(strategy.analyze).parameters
                    if "current_time" in params:
                        kwargs["current_time"] = current_time
                signal = strategy.analyze(**kwargs)
                if signal:
                    # Guarantee strategy_name is always set — never blank
                    if not signal.strategy_name:
                        signal.strategy_name = name
                    signal.metadata["strategy_weight"] = self.weights.get(name, 1.0)
                    signals.append(signal)
                    logger.debug(
                        f"[StrategyManager] {pair} {signal.direction} "
                        f"signal from '{signal.strategy_name}'"
                    )
            except Exception as e:
                logger.error(f"[StrategyManager] Error in strategy {name}: {e}", exc_info=True)

        # ── Directional consensus gate ───────────────────────────────────────
        # Require ≥2 independent strategies to agree on direction before
        # surfacing any signals.  Conflicting or lone signals are skipped.
        buy_signals  = [s for s in signals if s.direction == "BUY"]
        sell_signals = [s for s in signals if s.direction == "SELL"]

        if len(buy_signals) >= 2 and len(buy_signals) > len(sell_signals):
            logger.debug(f"[StrategyManager] {pair} consensus BUY ({len(buy_signals)} strategies)")
            return buy_signals
        if len(sell_signals) >= 2 and len(sell_signals) > len(buy_signals):
            logger.debug(f"[StrategyManager] {pair} consensus SELL ({len(sell_signals)} strategies)")
            return sell_signals

        if signals:
            logger.debug(
                f"[StrategyManager] {pair} no consensus — "
                f"BUY:{len(buy_signals)} SELL:{len(sell_signals)} — skipping"
            )
        return []

    def _get_atr(self, data: dict) -> float:
        from indicators.volatility import VolatilityIndicators
        for tf in ["H1", "M15", "H4", "M5"]:
            if tf in data and data[tf] is not None and len(data[tf]) >= 15:
                try:
                    atr_s = VolatilityIndicators.atr(data[tf], 14)
                    val = atr_s.iloc[-1]
                    if not pd.isna(val):
                        return val
                except Exception:
                    pass
        return 0.0010  # fallback 10 pips EUR/USD

    def get_active_strategies(self) -> List[str]:
        return [k for k, v in self.paused.items() if not v]

    def update_strategy_weight(self, strategy_name: str, weight: float):
        if strategy_name in self.weights:
            self.weights[strategy_name] = max(0.1, min(2.0, weight))
            logger.info(f"[StrategyManager] Updated weight for {strategy_name}: {weight}")

    def pause_strategy(self, strategy_name: str):
        if strategy_name in self.paused:
            self.paused[strategy_name] = True
            logger.info(f"[StrategyManager] Paused strategy: {strategy_name}")

    def resume_strategy(self, strategy_name: str):
        if strategy_name in self.paused:
            self.paused[strategy_name] = False
            logger.info(f"[StrategyManager] Resumed strategy: {strategy_name}")

    def get_strategy_stats(self) -> dict:
        return {
            name: {
                "weight": self.weights.get(name, 1.0),
                "paused": self.paused.get(name, False),
                "active": not self.paused.get(name, False) and self.weights.get(name, 1.0) >= 0.1,
            }
            for name in self.strategies
        }
