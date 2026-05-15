"""Monte Carlo simulation — 1000 random trade orderings."""
import numpy as np
import pandas as pd
from typing import List, Dict
from utils.logger import get_logger

logger = get_logger(__name__)


class MonteCarloSimulator:
    def __init__(self, n_simulations: int = 1000, initial_balance: float = 10000):
        self.n = n_simulations
        self.initial_balance = initial_balance

    def run(self, trade_pnls: List[float]) -> Dict:
        """
        Simulate N random orderings of the given trade P&Ls.
        Returns statistics across all simulations.
        """
        if not trade_pnls:
            return {"error": "No trades to simulate"}

        pnls = np.array(trade_pnls)
        n_trades = len(pnls)
        logger.info(f"[MonteCarlo] Running {self.n} simulations with {n_trades} trades")

        final_balances = []
        max_drawdowns = []
        ruin_count = 0
        ruin_threshold = self.initial_balance * 0.8  # 20% loss = ruin

        all_equity_curves = []
        for _ in range(self.n):
            shuffled = np.random.choice(pnls, size=n_trades, replace=True)
            equity = np.cumsum(shuffled) + self.initial_balance
            equity = np.concatenate([[self.initial_balance], equity])

            final_balances.append(equity[-1])

            peak = np.maximum.accumulate(equity)
            dd = (peak - equity) / peak
            max_drawdowns.append(float(dd.max()))

            if equity.min() <= ruin_threshold:
                ruin_count += 1

            all_equity_curves.append(equity.tolist())

        fb = np.array(final_balances)
        mdd = np.array(max_drawdowns)

        return {
            "n_simulations": self.n,
            "n_trades": n_trades,
            "initial_balance": self.initial_balance,
            "final_balance": {
                "mean": round(float(fb.mean()), 2),
                "median": round(float(np.median(fb)), 2),
                "p5": round(float(np.percentile(fb, 5)), 2),
                "p25": round(float(np.percentile(fb, 25)), 2),
                "p75": round(float(np.percentile(fb, 75)), 2),
                "p95": round(float(np.percentile(fb, 95)), 2),
                "min": round(float(fb.min()), 2),
                "max": round(float(fb.max()), 2),
            },
            "max_drawdown": {
                "mean": round(float(mdd.mean()), 3),
                "median": round(float(np.median(mdd)), 3),
                "p95": round(float(np.percentile(mdd, 95)), 3),
                "worst": round(float(mdd.max()), 3),
            },
            "probability_of_profit": round(float((fb > self.initial_balance).mean()), 3),
            "probability_of_ruin": round(ruin_count / self.n, 3),
            "expected_return_pct": round(float((fb.mean() - self.initial_balance) / self.initial_balance * 100), 2),
            "equity_curves_sample": all_equity_curves[:10],  # first 10 for charting
        }

    def run_from_backtest_result(self, result) -> Dict:
        pnls = [t["pnl_usd"] for t in result.trades]
        return self.run(pnls)
