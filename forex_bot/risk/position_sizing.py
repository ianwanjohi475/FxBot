"""
Position sizing — risk exactly N% of account per trade.
"""
from utils.logger import get_logger
from utils.helpers import price_to_pips

logger = get_logger(__name__)

PIP_SIZES = {
    "JPY": 0.01,
    "XAU": 0.01,
    "XAG": 0.01,
    "US30": 1.0,   # Dow Jones — 1 index point per pip
    "NAS": 1.0,
    "SPX": 1.0,
    "DEFAULT": 0.0001,
}

LOT_STEPS = {
    "nano": 0.001,
    "micro": 0.01,
    "mini": 0.1,
    "standard": 0.01,
}


class PositionSizer:
    def __init__(self, risk_pct: float = 0.01):
        self.risk_pct = risk_pct

    def calculate_lot_size(
        self,
        account_balance: float,
        entry_price: float,
        sl_price: float,
        pair: str,
        account_currency: str = "USD",
    ) -> float:
        pip_size = self._pip_size(pair)
        pip_distance = abs(entry_price - sl_price) / pip_size
        if pip_distance == 0:
            logger.warning("SL distance is zero — returning min lot size")
            return 0.01

        pip_value_per_std_lot = self._pip_value_per_std_lot(pair, entry_price)
        risk_amount = account_balance * self.risk_pct
        lot_size = risk_amount / (pip_distance * pip_value_per_std_lot)

        account_type = self.get_account_size_type(account_balance)
        lot_step = LOT_STEPS.get(account_type, 0.01)
        lot_size = round(lot_size / lot_step) * lot_step
        lot_size = max(lot_step, lot_size)

        # Cap: never exceed 2% margin of account (rough cap)
        max_lot = (account_balance * 0.02) / (entry_price * 100 * pip_value_per_std_lot + 0.0001)
        lot_size = min(lot_size, max_lot)
        lot_size = max(lot_step, round(lot_size, 3))
        logger.debug(f"[PositionSizer] {pair} lot={lot_size} (risk={risk_amount:.2f} pips={pip_distance:.1f})")
        return lot_size

    def _pip_size(self, pair: str) -> float:
        for key, size in PIP_SIZES.items():
            if key != "DEFAULT" and key in pair:
                return size
        return PIP_SIZES["DEFAULT"]

    def _pip_value_per_std_lot(self, pair: str, price: float) -> float:
        """Value in USD of 1 pip for 1 standard lot (100,000 units)."""
        if "JPY" in pair:
            return 1000 / price   # approx
        if "XAU" in pair:
            return 1.0
        if pair.endswith("USD") or pair.endswith("_USD"):
            return 10.0
        if pair.startswith("USD"):
            return 10.0 / price
        return 10.0  # rough default

    def get_account_size_type(self, balance: float) -> str:
        if balance < 1000:
            return "nano"
        if balance < 10000:
            return "micro"
        return "standard"

    def adjust_for_drawdown(self, lot_size: float, daily_drawdown_pct: float) -> float:
        if daily_drawdown_pct > 0.03:
            return round(lot_size * 0.5, 3)
        return lot_size

    def calculate_pip_value(self, pair: str, lot_size: float,
                             account_currency: str = "USD") -> float:
        pip_size = self._pip_size(pair)
        units = lot_size * 100000
        if "JPY" in pair:
            return units * pip_size / 100
        return units * pip_size
