"""Correlation filter — prevents opening over-correlated trades."""
from typing import List, Tuple, Dict
import pandas as pd
from utils.logger import get_logger

logger = get_logger(__name__)

# Pairs that are highly correlated (should not be opened same direction simultaneously)
HIGH_CORRELATION_GROUPS = [
    ["EUR_USD", "GBP_USD"],
    ["AUD_USD", "NZD_USD"],
    ["USD_JPY", "USD_CHF"],  # positive USD pairs
]

MAX_SAME_DIRECTION_USD = 3


class CorrelationFilter:
    def __init__(self):
        self.open_trades: List[Dict] = []  # [{"pair": str, "direction": str}]

    def add_trade(self, pair: str, direction: str):
        self.open_trades.append({"pair": pair, "direction": direction})

    def remove_trade(self, pair: str):
        self.open_trades = [t for t in self.open_trades if t["pair"] != pair]

    def can_open_trade(self, pair: str, direction: str) -> Tuple[bool, str]:
        """Returns (allowed, reason)."""
        for group in HIGH_CORRELATION_GROUPS:
            if pair not in group:
                continue
            for trade in self.open_trades:
                if trade["pair"] in group and trade["pair"] != pair:
                    if trade["direction"] == direction:
                        reason = (
                            f"Correlation block: {pair} and {trade['pair']} "
                            f"both {direction} — highly correlated pairs"
                        )
                        logger.info(f"[CorrelationFilter] {reason}")
                        return False, reason

        # Count same-direction USD exposure
        usd_pairs_same_dir = [
            t for t in self.open_trades
            if "USD" in t["pair"] and t["direction"] == direction
        ]
        if len(usd_pairs_same_dir) >= MAX_SAME_DIRECTION_USD:
            reason = f"Too many {direction} USD trades open ({len(usd_pairs_same_dir)})"
            return False, reason

        return True, "OK"

    def get_correlation_coefficient(self, pair1: str, pair2: str,
                                     price_data: dict) -> float:
        """Calculate rolling correlation between two pairs."""
        df1 = price_data.get(pair1)
        df2 = price_data.get(pair2)
        if df1 is None or df2 is None:
            return 0.0
        try:
            r1 = df1["close"].pct_change().dropna()
            r2 = df2["close"].pct_change().dropna()
            common = r1.index.intersection(r2.index)
            if len(common) < 20:
                return 0.0
            return float(r1.loc[common].corr(r2.loc[common]))
        except Exception:
            return 0.0

    def calculate_portfolio_exposure(self, open_trades: List[dict]) -> dict:
        """Estimate currency exposure from all open trades."""
        exposure: Dict[str, float] = {}
        for trade in open_trades:
            pair = trade.get("pair", "")
            direction = trade.get("direction", "BUY")
            lot = trade.get("lot_size", 1.0)
            parts = pair.replace("_", "")
            if len(parts) == 6:
                base = parts[:3]
                quote = parts[3:]
                sign = 1 if direction == "BUY" else -1
                exposure[base] = exposure.get(base, 0) + sign * lot
                exposure[quote] = exposure.get(quote, 0) - sign * lot
        return exposure
