"""Generate backtest reports with charts."""
import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import Dict, List
from .backtest_engine import BacktestResult
from utils.logger import get_logger

logger = get_logger(__name__)

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")


class ReportGenerator:
    def __init__(self):
        os.makedirs(REPORTS_DIR, exist_ok=True)

    def generate_full_report(
        self,
        result: BacktestResult,
        pair: str,
        strategy_name: str = "all",
    ) -> Dict:
        summary = result.get_summary()
        charts = {}

        if result.equity_curve:
            charts["equity_curve"] = self._equity_curve_chart(result, pair)
            charts["drawdown"] = self._drawdown_chart(result)
        if result.trades:
            charts["monthly_returns"] = self._monthly_heatmap(result)
            charts["per_pair"] = self._per_pair_breakdown(result)

        return {
            "summary": summary,
            "charts": charts,
            "trades": result.trades,
        }

    def _equity_curve_chart(self, result: BacktestResult, pair: str) -> go.Figure:
        dates = result.dates[:len(result.equity_curve)]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=result.equity_curve,
            mode="lines", name="Equity",
            line=dict(color="royalblue", width=2),
        ))
        fig.update_layout(
            title=f"Equity Curve — {pair}",
            xaxis_title="Date", yaxis_title="Balance ($)",
            template="plotly_dark", height=400,
        )
        return fig

    def _drawdown_chart(self, result: BacktestResult) -> go.Figure:
        equity = np.array(result.equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown_pct = (peak - equity) / peak * 100
        dates = result.dates[:len(equity)]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=-drawdown_pct,
            fill="tozeroy", mode="lines",
            line=dict(color="red", width=1),
            name="Drawdown %",
        ))
        fig.update_layout(
            title="Drawdown (%)",
            xaxis_title="Date", yaxis_title="Drawdown %",
            template="plotly_dark", height=300,
        )
        return fig

    def _monthly_heatmap(self, result: BacktestResult) -> go.Figure:
        trades_df = pd.DataFrame(result.trades)
        if trades_df.empty or "entry_time" not in trades_df.columns:
            return go.Figure()

        trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"])
        trades_df["year"] = trades_df["entry_time"].dt.year
        trades_df["month"] = trades_df["entry_time"].dt.month

        monthly = trades_df.groupby(["year", "month"])["pnl_usd"].sum().reset_index()
        pivot = monthly.pivot(index="year", columns="month", values="pnl_usd").fillna(0)

        month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        pivot.columns = [month_names[m - 1] for m in pivot.columns]

        fig = px.imshow(
            pivot,
            color_continuous_scale=["red", "white", "green"],
            color_continuous_midpoint=0,
            aspect="auto",
            title="Monthly Returns ($)",
        )
        fig.update_layout(template="plotly_dark", height=300)
        return fig

    def _per_pair_breakdown(self, result: BacktestResult) -> go.Figure:
        trades_df = pd.DataFrame(result.trades)
        if trades_df.empty or "pair" not in trades_df.columns:
            return go.Figure()
        by_pair = trades_df.groupby("pair")["pnl_usd"].sum().sort_values(ascending=False)
        colors = ["green" if v >= 0 else "red" for v in by_pair.values]
        fig = go.Figure(go.Bar(
            x=by_pair.index, y=by_pair.values,
            marker_color=colors,
        ))
        fig.update_layout(title="P&L by Pair", template="plotly_dark", height=300)
        return fig

    def consecutive_stats(self, result: BacktestResult) -> dict:
        pnls = [t["pnl_usd"] for t in result.trades]
        max_wins = max_losses = cur_wins = cur_losses = 0
        for p in pnls:
            if p > 0:
                cur_wins += 1
                cur_losses = 0
                max_wins = max(max_wins, cur_wins)
            else:
                cur_losses += 1
                cur_wins = 0
                max_losses = max(max_losses, cur_losses)
        return {"max_consecutive_wins": max_wins, "max_consecutive_losses": max_losses}

    def best_worst_month(self, result: BacktestResult) -> dict:
        trades_df = pd.DataFrame(result.trades)
        if trades_df.empty:
            return {}
        trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"])
        trades_df["month"] = trades_df["entry_time"].dt.to_period("M")
        monthly = trades_df.groupby("month")["pnl_usd"].sum()
        return {
            "best_month": str(monthly.idxmax()),
            "best_month_pnl": round(float(monthly.max()), 2),
            "worst_month": str(monthly.idxmin()),
            "worst_month_pnl": round(float(monthly.min()), 2),
        }
