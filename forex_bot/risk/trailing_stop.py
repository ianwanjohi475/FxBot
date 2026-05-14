"""Trailing stop logic — activates after TP1 hit, trails by 1x ATR."""
from typing import Optional, Dict
from utils.logger import get_logger

logger = get_logger(__name__)


class TrailingStop:
    def __init__(self):
        self.active_trails: Dict[str, dict] = {}

    def activate(self, trade_id: str, entry: float, direction: str,
                 atr: float, activation_price: float):
        self.active_trails[trade_id] = {
            "entry": entry,
            "direction": direction,
            "atr": atr,
            "activation_price": activation_price,
            "current_sl": (
                activation_price - atr if direction == "BUY"
                else activation_price + atr
            ),
            "activated": False,
            "highest": activation_price if direction == "BUY" else activation_price,
            "lowest": activation_price if direction == "SELL" else activation_price,
        }
        logger.info(f"[TrailingStop] Prepared trail for trade {trade_id}")

    def update(self, trade_id: str, current_price: float, atr: float) -> Optional[float]:
        """Update trail. Returns new SL if changed, else None."""
        trail = self.active_trails.get(trade_id)
        if not trail:
            return None

        direction = trail["direction"]

        # Activate trail when price reaches activation price
        if not trail["activated"]:
            if direction == "BUY" and current_price >= trail["activation_price"]:
                trail["activated"] = True
                logger.info(f"[TrailingStop] Activated for {trade_id}")
            elif direction == "SELL" and current_price <= trail["activation_price"]:
                trail["activated"] = True
                logger.info(f"[TrailingStop] Activated for {trade_id}")
            else:
                return None

        trail["atr"] = atr
        new_sl = None

        if direction == "BUY":
            if current_price > trail["highest"]:
                trail["highest"] = current_price
                candidate_sl = current_price - atr
                if candidate_sl > trail["current_sl"]:
                    trail["current_sl"] = candidate_sl
                    new_sl = candidate_sl
        else:
            if current_price < trail["lowest"]:
                trail["lowest"] = current_price
                candidate_sl = current_price + atr
                if candidate_sl < trail["current_sl"]:
                    trail["current_sl"] = candidate_sl
                    new_sl = candidate_sl

        if new_sl:
            logger.debug(f"[TrailingStop] {trade_id} new SL={new_sl:.5f}")
        return round(new_sl, 5) if new_sl else None

    def get_current_sl(self, trade_id: str) -> Optional[float]:
        trail = self.active_trails.get(trade_id)
        if trail:
            return trail["current_sl"]
        return None

    def deactivate(self, trade_id: str):
        if trade_id in self.active_trails:
            del self.active_trails[trade_id]

    def should_close(self, trade_id: str, current_price: float) -> bool:
        trail = self.active_trails.get(trade_id)
        if not trail or not trail["activated"]:
            return False
        direction = trail["direction"]
        sl = trail["current_sl"]
        if direction == "BUY" and current_price <= sl:
            return True
        if direction == "SELL" and current_price >= sl:
            return True
        return False
