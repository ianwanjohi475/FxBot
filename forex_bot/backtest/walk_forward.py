"""Walk-forward optimization: 70% train / 30% test split."""
import pandas as pd
import numpy as np
from typing import Dict, Optional
from .backtest_engine import BacktestEngine, BacktestResult
from utils.logger import get_logger

logger = get_logger(__name__)


class WalkForwardOptimizer:
    def __init__(
        self,
        train_pct: float = 0.70,
        initial_balance: float = 10000,
        risk_pct: float = 0.01,
    ):
        self.train_pct = train_pct
        self.test_pct = 1 - train_pct
        self.initial_balance = initial_balance
        self.risk_pct = risk_pct

    def run(
        self,
        pair: str,
        df: pd.DataFrame,
        strategy_name: Optional[str] = None,
        min_scores: list = None,
    ) -> Dict:
        if min_scores is None:
            min_scores = [55, 60, 65, 70, 75]

        n = len(df)
        split = int(n * self.train_pct)
        train_df = df.iloc[:split]
        test_df = df.iloc[split:]

        logger.info(
            f"[WalkForward] {pair} — train={len(train_df)} test={len(test_df)} bars"
        )

        # Optimize on train: find best min_score
        best_score_threshold = 65
        best_pf = 0.0
        train_results = {}

        for threshold in min_scores:
            engine = BacktestEngine(
                initial_balance=self.initial_balance,
                risk_pct=self.risk_pct,
                min_score=threshold,
            )
            result = engine.run(pair, train_df, strategy_name)
            summary = result.get_summary()
            pf = summary.get("profit_factor", 0)
            train_results[threshold] = summary
            logger.info(f"[WalkForward] Train threshold={threshold} PF={pf:.2f}")
            if pf > best_pf and summary.get("total_trades", 0) >= 10:
                best_pf = pf
                best_score_threshold = threshold

        # Validate on test with best threshold
        logger.info(f"[WalkForward] Best threshold={best_score_threshold} — running test set")
        test_engine = BacktestEngine(
            initial_balance=self.initial_balance,
            risk_pct=self.risk_pct,
            min_score=best_score_threshold,
        )
        test_result = test_engine.run(pair, test_df, strategy_name)
        test_summary = test_result.get_summary()

        return {
            "pair": pair,
            "train_bars": len(train_df),
            "test_bars": len(test_df),
            "best_threshold": best_score_threshold,
            "train_results": train_results,
            "test_summary": test_summary,
            "is_robust": (
                test_summary.get("profit_factor", 0) > 1.0
                and test_summary.get("win_rate", 0) > 0.40
            ),
        }
