"""Trading strategies package."""
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class TradeSignal:
    pair: str
    direction: str          # 'BUY' or 'SELL'
    strategy_name: str
    timeframe: str
    entry_price: float
    sl_price: float
    tp1_price: float
    tp2_price: float
    tp3_price: float
    confluence_score: float = 0.0
    confidence_pct: float = 0.0
    pattern_detected: Optional[str] = None
    smc_concept: Optional[str] = None
    indicators: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)

    def risk_pips(self, pip_value: float = 0.0001) -> float:
        return abs(self.entry_price - self.sl_price) / pip_value

    def reward_pips_tp1(self, pip_value: float = 0.0001) -> float:
        return abs(self.tp1_price - self.entry_price) / pip_value

    def rr_ratio(self) -> float:
        risk = abs(self.entry_price - self.sl_price)
        if risk == 0:
            return 0.0
        reward = abs(self.tp1_price - self.entry_price)
        return round(reward / risk, 2)

    def to_dict(self) -> dict:
        return {
            "pair": self.pair,
            "direction": self.direction,
            "strategy_name": self.strategy_name,
            "timeframe": self.timeframe,
            "entry_price": self.entry_price,
            "sl_price": self.sl_price,
            "tp1_price": self.tp1_price,
            "tp2_price": self.tp2_price,
            "tp3_price": self.tp3_price,
            "confluence_score": self.confluence_score,
            "confidence_pct": self.confidence_pct,
            "pattern_detected": self.pattern_detected,
            "smc_concept": self.smc_concept,
            "indicators": self.indicators,
            "metadata": self.metadata,
        }
