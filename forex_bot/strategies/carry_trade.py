"""
Carry Trade Strategy — flag high interest rate differential pairs.
Does not execute trades directly; flags opportunities for the engine.
"""
from typing import Optional, List, Dict
from utils.logger import get_logger

logger = get_logger(__name__)

# Approximate central bank interest rates (update periodically)
INTEREST_RATES = {
    "USD": 5.25,
    "EUR": 4.00,
    "GBP": 5.25,
    "JPY": -0.10,
    "AUD": 4.35,
    "NZD": 5.50,
    "CAD": 5.00,
    "CHF": 1.75,
    "NOK": 4.50,
    "SEK": 4.00,
}

CARRY_PAIRS = [
    ("AUD_JPY", "AUD", "JPY"),
    ("NZD_JPY", "NZD", "JPY"),
    ("GBP_JPY", "GBP", "JPY"),
    ("EUR_JPY", "EUR", "JPY"),
    ("USD_JPY", "USD", "JPY"),
    ("AUD_CHF", "AUD", "CHF"),
    ("NZD_CHF", "NZD", "CHF"),
]


class CarryTradeStrategy:
    name = "carry_trade"
    min_differential = 2.0  # Minimum % rate differential to flag

    def get_carry_opportunities(self) -> List[Dict]:
        """Return list of carry trade opportunities sorted by differential."""
        opportunities = []
        for pair, base, quote in CARRY_PAIRS:
            base_rate = INTEREST_RATES.get(base, 0)
            quote_rate = INTEREST_RATES.get(quote, 0)
            differential = base_rate - quote_rate

            if abs(differential) >= self.min_differential:
                direction = "BUY" if differential > 0 else "SELL"
                opportunities.append({
                    "pair": pair,
                    "direction": direction,
                    "base_rate": base_rate,
                    "quote_rate": quote_rate,
                    "differential": round(differential, 2),
                    "annual_carry_pct": round(abs(differential), 2),
                })
        return sorted(opportunities, key=lambda x: abs(x["differential"]), reverse=True)

    def analyze(self, data, pair, current_price, atr, spread_pips=1.5):
        """Returns None — carry trade is flagging only, not direct signal generation."""
        opps = {o["pair"]: o for o in self.get_carry_opportunities()}
        if pair in opps:
            opp = opps[pair]
            logger.info(
                f"[CarryTrade] {pair} carry opportunity: {opp['direction']} "
                f"differential={opp['differential']}%"
            )
        return None

    def update_rates(self, rates: dict):
        """Update interest rates from external source."""
        INTEREST_RATES.update(rates)
        logger.info(f"[CarryTrade] Updated interest rates: {rates}")
