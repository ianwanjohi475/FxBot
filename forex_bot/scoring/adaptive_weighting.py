"""
Adaptive strategy weighting — evaluates performance and adjusts weights.
"""
import numpy as np
from typing import Dict, List, Optional
from database.db import DatabaseManager
from utils.logger import get_logger

logger = get_logger(__name__)

MIN_WEIGHT = 0.1
MAX_WEIGHT = 2.0
MIN_TRADES_TO_EVALUATE = 20
MIN_TRADES_FOR_DOWNGRADE = 30
LOW_WIN_RATE_THRESHOLD = 0.40


class AdaptiveWeighting:
    def __init__(self):
        self.db = DatabaseManager()
        self.weights: Dict[str, float] = {}
        self._load_weights()

    def _load_weights(self):
        try:
            perfs = self.db.get_all_strategy_performance()
            for p in perfs:
                self.weights[p.strategy_name] = p.confluence_weight or 1.0
        except Exception as e:
            logger.debug(f"[AdaptiveWeighting] Could not load weights: {e}")

    def evaluate_strategy(self, strategy_name: str) -> dict:
        try:
            trades = self.db.get_trades(strategy=strategy_name, limit=100)
        except Exception:
            return {}
        if not trades:
            return {"total_trades": 0}

        wins = sum(1 for t in trades if t.result == "WIN")
        losses = sum(1 for t in trades if t.result == "LOSS")
        total = len(trades)
        win_rate = wins / total if total else 0

        gross_profit = sum(t.pnl_usd or 0 for t in trades if (t.pnl_usd or 0) > 0)
        gross_loss = abs(sum(t.pnl_usd or 0 for t in trades if (t.pnl_usd or 0) < 0))
        pf = gross_profit / gross_loss if gross_loss > 0 else (1.0 if gross_profit > 0 else 0)

        rrs = [t.actual_rr for t in trades if t.actual_rr is not None]
        avg_rr = float(np.mean(rrs)) if rrs else 0.0

        return {
            "strategy_name": strategy_name,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 3),
            "profit_factor": round(pf, 2),
            "avg_rr": round(avg_rr, 2),
            "sharpe": self.calculate_sharpe_ratio(trades),
        }

    def calculate_profit_factor(self, trades) -> float:
        gp = sum(t.pnl_usd or 0 for t in trades if (t.pnl_usd or 0) > 0)
        gl = abs(sum(t.pnl_usd or 0 for t in trades if (t.pnl_usd or 0) < 0))
        return round(gp / gl, 2) if gl > 0 else 1.0

    def calculate_sharpe_ratio(self, trades) -> float:
        returns = [t.pnl_usd or 0 for t in trades if t.pnl_usd is not None]
        if len(returns) < 5:
            return 0.0
        arr = np.array(returns)
        mean_r = np.mean(arr)
        std_r = np.std(arr)
        if std_r == 0:
            return 0.0
        return round(float(mean_r / std_r * np.sqrt(252)), 2)

    def update_weights(self):
        """Re-evaluate all strategies and update weights."""
        strategy_names = list(set(list(self.weights.keys())))
        try:
            perfs = self.db.get_all_strategy_performance()
            strategy_names = list(set(strategy_names + [p.strategy_name for p in perfs]))
        except Exception:
            pass

        for name in strategy_names:
            stats = self.evaluate_strategy(name)
            total = stats.get("total_trades", 0)
            win_rate = stats.get("win_rate", 0)
            pf = stats.get("profit_factor", 1.0)
            current_weight = self.weights.get(name, 1.0)
            new_weight = current_weight

            if total >= MIN_TRADES_TO_EVALUATE:
                if win_rate > 0.60 and pf > 1.5:
                    new_weight = min(current_weight * 1.2, MAX_WEIGHT)
                    logger.info(f"[AdaptiveWeighting] {name} boosted → {new_weight:.2f}")

            if total >= MIN_TRADES_FOR_DOWNGRADE:
                if win_rate < LOW_WIN_RATE_THRESHOLD:
                    new_weight = max(current_weight * 0.7, MIN_WEIGHT)
                    logger.info(f"[AdaptiveWeighting] {name} reduced → {new_weight:.2f}")

            self.weights[name] = round(new_weight, 3)
            try:
                self.db.update_strategy_performance(name, {
                    "confluence_weight": new_weight,
                    **stats,
                })
            except Exception:
                pass

    def get_weight(self, strategy_name: str) -> float:
        return self.weights.get(strategy_name, 1.0)

    def get_all_weights(self) -> Dict[str, float]:
        return dict(self.weights)

    def get_performance_table(self) -> List[dict]:
        try:
            perfs = self.db.get_all_strategy_performance()
            return [
                {
                    "strategy": p.strategy_name,
                    "trades": p.total_trades,
                    "win_rate": round((p.wins or 0) / max(p.total_trades, 1), 3),
                    "profit_factor": p.profit_factor,
                    "avg_rr": p.avg_rr,
                    "total_pnl": p.total_pnl_usd,
                    "weight": p.confluence_weight,
                    "paused": p.is_paused,
                }
                for p in perfs
            ]
        except Exception as e:
            logger.error(f"[AdaptiveWeighting] get_performance_table error: {e}")
            return []

    def should_pause_strategy(self, strategy_name: str) -> bool:
        stats = self.evaluate_strategy(strategy_name)
        total = stats.get("total_trades", 0)
        win_rate = stats.get("win_rate", 1.0)
        if total >= MIN_TRADES_FOR_DOWNGRADE and win_rate < 0.25:
            return True
        return False
