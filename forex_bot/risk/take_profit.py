"""Take Profit calculation utilities."""
from typing import List, Tuple, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class TakeProfitCalculator:

    # Volatile pairs need wider TP targets because price makes larger swings.
    # Standard pairs use 1:1, 2:1, 3:1.  Volatile pairs use 1.5:1, 3:1, 5:1.
    PAIR_RR_LEVELS: dict = {
        "XAU_USD":  (1.5, 3.0, 5.0),
        "US30_USD": (1.5, 2.5, 4.0),
        "GBP_JPY":  (1.2, 2.2, 3.5),
        "USD_JPY":  (1.0, 2.0, 3.0),
        "EUR_USD":  (1.0, 2.0, 3.0),
    }

    def calculate_tp_levels(
        self,
        entry: float,
        sl: float,
        direction: str,
        pair: str = "EUR_USD",
        rr_tp1: float = None,
        rr_tp2: float = None,
        rr_tp3: float = None,
    ) -> Tuple[float, float, float]:
        # Use pair-specific RR levels if caller didn't override
        default_rr = self.PAIR_RR_LEVELS.get(pair, (1.0, 2.0, 3.0))
        if rr_tp1 is None: rr_tp1 = default_rr[0]
        if rr_tp2 is None: rr_tp2 = default_rr[1]
        if rr_tp3 is None: rr_tp3 = default_rr[2]

        risk = abs(entry - sl)
        if direction == "BUY":
            tp1 = entry + risk * rr_tp1
            tp2 = entry + risk * rr_tp2
            tp3 = entry + risk * rr_tp3
        else:
            tp1 = entry - risk * rr_tp1
            tp2 = entry - risk * rr_tp2
            tp3 = entry - risk * rr_tp3
        return round(tp1, 5), round(tp2, 5), round(tp3, 5)

    def sr_based_tp(self, entry: float, direction: str,
                    sr_levels: list, pair: str = "EUR_USD") -> List[float]:
        if not sr_levels:
            return []
        if direction == "BUY":
            candidates = sorted([l for l in sr_levels if l > entry])
        else:
            candidates = sorted([l for l in sr_levels if l < entry], reverse=True)
        return [round(l, 5) for l in candidates[:3]]

    def fibonacci_tp(self, swing_low: float, swing_high: float,
                     direction: str) -> List[float]:
        rng = swing_high - swing_low
        if direction == "BUY":
            return [
                round(swing_high + rng * 0.618, 5),
                round(swing_high + rng * 1.618, 5),
                round(swing_high + rng * 2.618, 5),
            ]
        return [
            round(swing_low - rng * 0.618, 5),
            round(swing_low - rng * 1.618, 5),
            round(swing_low - rng * 2.618, 5),
        ]

    def partial_close_plan(self) -> List[Tuple[str, float]]:
        """Returns list of (tp_label, close_percentage) tuples."""
        return [("tp1", 0.30), ("tp2", 0.40), ("tp3", 0.30)]
