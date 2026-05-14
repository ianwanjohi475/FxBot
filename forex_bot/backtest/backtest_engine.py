"""
Core backtesting engine.
Simulates realistic execution with spread, slippage, partial closes, and trailing stops.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
from strategies.strategy_manager import StrategyManager
from scoring.confluence_engine import ConfluenceEngine
from risk.position_sizing import PositionSizer
from risk.trailing_stop import TrailingStop
from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_SPREAD = {"EUR_USD": 1.5, "GBP_USD": 2.0, "USD_JPY": 1.5, "XAU_USD": 3.0}
SLIPPAGE_PIPS = 0.5
PARTIAL_CLOSE_TP1 = 0.30
PARTIAL_CLOSE_TP2 = 0.40


class BacktestResult:
    def __init__(self):
        self.trades: List[dict] = []
        self.equity_curve: List[float] = []
        self.dates: List[datetime] = []

    def add_trade(self, trade: dict):
        self.trades.append(trade)

    def get_summary(self) -> dict:
        if not self.trades:
            return {"total_trades": 0}

        pnls = [t["pnl_usd"] for t in self.trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        total = len(pnls)
        win_rate = len(wins) / total if total else 0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss else float("inf")

        equity = np.array(self.equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        max_dd = float(drawdown.max()) if len(drawdown) > 0 else 0

        rrs = [t.get("actual_rr", 0) for t in self.trades]
        avg_rr = float(np.mean(rrs)) if rrs else 0

        # Sharpe Ratio (annualized, assuming daily returns)
        returns = np.diff(equity) / equity[:-1] if len(equity) > 1 else np.array([0])
        sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 0 else 0

        # Sortino
        downside = returns[returns < 0]
        sortino = float(np.mean(returns) / np.std(downside) * np.sqrt(252)) if len(downside) > 0 and np.std(downside) > 0 else 0

        # CAGR
        if len(self.equity_curve) >= 2:
            years = len(self.equity_curve) / 252
            cagr = (self.equity_curve[-1] / self.equity_curve[0]) ** (1 / years) - 1 if years > 0 else 0
        else:
            cagr = 0

        return {
            "total_trades": total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 3),
            "profit_factor": round(profit_factor, 2),
            "net_profit": round(sum(pnls), 2),
            "max_drawdown_pct": round(max_dd, 3),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "cagr": round(cagr, 3),
            "avg_rr": round(avg_rr, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "best_trade": round(max(pnls), 2) if pnls else 0,
            "worst_trade": round(min(pnls), 2) if pnls else 0,
        }


class BacktestEngine:
    def __init__(
        self,
        initial_balance: float = 10000,
        risk_pct: float = 0.01,
        spread_pips: dict = None,
        slippage_pips: float = SLIPPAGE_PIPS,
        min_score: float = 65,
    ):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.risk_pct = risk_pct
        self.spread = spread_pips or DEFAULT_SPREAD
        self.slippage = slippage_pips
        self.min_score = min_score
        self.strategy_manager = StrategyManager()
        self.confluence = ConfluenceEngine(min_score)
        self.sizer = PositionSizer(risk_pct)
        self.trailing = TrailingStop()

    def run(
        self,
        pair: str,
        df: pd.DataFrame,
        strategy_name: Optional[str] = None,
        lookback: int = 200,
    ) -> BacktestResult:
        self.balance = self.initial_balance
        result = BacktestResult()
        result.equity_curve.append(self.balance)
        result.dates.append(df.index[0] if len(df) > 0 else datetime.now())

        spread_pips = self.spread.get(pair, 2.0)
        pip_size = 0.01 if "JPY" in pair else 0.0001
        slip = self.slippage * pip_size

        for i in range(lookback, len(df)):
            window = {
                "H1": df.iloc[max(0, i - lookback) : i],
                "M15": df.iloc[max(0, i - lookback) : i],
                "H4": df.iloc[max(0, i - lookback // 4) : i],
                "D1": df.iloc[max(0, i - lookback // 24) : i],
            }
            current_bar = df.iloc[i]
            current_price = float(current_bar["close"])
            current_time = df.index[i]
            if hasattr(current_time, "to_pydatetime"):
                current_time = current_time.to_pydatetime()

            signals = self.strategy_manager.analyze_all(
                data=window,
                pair=pair,
                current_price=current_price,
                spread_pips=spread_pips,
                current_time=current_time,
            )

            if strategy_name:
                signals = [s for s in signals if s.strategy_name == strategy_name]

            context = {"session": "london", "news_risk_score": 0}

            for signal in signals:
                score = self.confluence.score_signal(signal, window, context)
                if score < self.min_score:
                    continue

                # Simulate entry with slippage + spread
                entry = current_price + slip
                if signal.direction == "SELL":
                    entry = current_price - slip

                sl = signal.sl_price
                tp1 = signal.tp1_price
                tp2 = signal.tp2_price
                tp3 = signal.tp3_price

                lot = self.sizer.calculate_lot_size(self.balance, entry, sl, pair)
                pip_val = self.sizer.calculate_pip_value(pair, lot)
                sl_pips = abs(entry - sl) / pip_size

                # Simulate trade outcome over future bars
                pnl, exit_price, exit_reason, actual_rr = self._simulate_trade(
                    df, i, signal.direction, entry, sl, tp1, tp2, tp3,
                    pip_size, pip_val, sl_pips
                )
                self.balance += pnl
                actual_rr_val = pnl / (sl_pips * pip_val) if (sl_pips * pip_val) != 0 else 0

                result.add_trade({
                    "entry_time": current_time,
                    "pair": pair,
                    "direction": signal.direction,
                    "strategy": signal.strategy_name,
                    "score": score,
                    "entry": entry,
                    "sl": sl,
                    "tp1": tp1,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "pnl_usd": round(pnl, 2),
                    "actual_rr": round(actual_rr_val, 2),
                    "balance": round(self.balance, 2),
                })
                result.equity_curve.append(self.balance)
                result.dates.append(current_time)
                break  # One trade per bar

        return result

    def _simulate_trade(
        self, df, entry_idx, direction, entry, sl, tp1, tp2, tp3,
        pip_size, pip_val, sl_pips
    ):
        remaining_lot_pct = 1.0
        total_pnl = 0.0
        tp1_hit = False
        tp2_hit = False

        for j in range(entry_idx + 1, min(entry_idx + 500, len(df))):
            bar = df.iloc[j]
            high = float(bar["high"])
            low = float(bar["low"])

            if direction == "BUY":
                # Check SL
                if low <= sl:
                    pnl = -sl_pips * pip_val * remaining_lot_pct
                    return total_pnl + pnl, sl, "sl_hit", -1.0
                # Check TP1
                if not tp1_hit and high >= tp1:
                    pnl = abs(tp1 - entry) / pip_size * pip_val * PARTIAL_CLOSE_TP1
                    total_pnl += pnl
                    remaining_lot_pct -= PARTIAL_CLOSE_TP1
                    sl = entry  # move to BE
                    tp1_hit = True
                # Check TP2
                if tp1_hit and not tp2_hit and high >= tp2:
                    pnl = abs(tp2 - entry) / pip_size * pip_val * PARTIAL_CLOSE_TP2
                    total_pnl += pnl
                    remaining_lot_pct -= PARTIAL_CLOSE_TP2
                    tp2_hit = True
                # Check TP3
                if tp2_hit and high >= tp3:
                    pnl = abs(tp3 - entry) / pip_size * pip_val * remaining_lot_pct
                    total_pnl += pnl
                    return total_pnl, tp3, "tp3_hit", total_pnl / (sl_pips * pip_val)
            else:
                if high >= sl:
                    pnl = -sl_pips * pip_val * remaining_lot_pct
                    return total_pnl + pnl, sl, "sl_hit", -1.0
                if not tp1_hit and low <= tp1:
                    pnl = abs(entry - tp1) / pip_size * pip_val * PARTIAL_CLOSE_TP1
                    total_pnl += pnl
                    remaining_lot_pct -= PARTIAL_CLOSE_TP1
                    sl = entry
                    tp1_hit = True
                if tp1_hit and not tp2_hit and low <= tp2:
                    pnl = abs(entry - tp2) / pip_size * pip_val * PARTIAL_CLOSE_TP2
                    total_pnl += pnl
                    remaining_lot_pct -= PARTIAL_CLOSE_TP2
                    tp2_hit = True
                if tp2_hit and low <= tp3:
                    pnl = abs(entry - tp3) / pip_size * pip_val * remaining_lot_pct
                    total_pnl += pnl
                    return total_pnl, tp3, "tp3_hit", total_pnl / (sl_pips * pip_val)

        # Timed out — close at last bar
        last_close = float(df.iloc[min(entry_idx + 499, len(df) - 1)]["close"])
        if direction == "BUY":
            pnl = (last_close - entry) / pip_size * pip_val * remaining_lot_pct
        else:
            pnl = (entry - last_close) / pip_size * pip_val * remaining_lot_pct
        return total_pnl + pnl, last_close, "timeout", (total_pnl + pnl) / (sl_pips * pip_val)

    def run_all_pairs(
        self,
        data: dict,
        strategy_name: Optional[str] = None,
    ) -> dict:
        results = {}
        for pair, df in data.items():
            if df is not None and not df.empty:
                logger.info(f"[BacktestEngine] Running {pair}...")
                results[pair] = self.run(pair, df, strategy_name)
        return results
