"""
SQLAlchemy 2.0-style ORM models for the Forex trading bot.

All models use Mapped / mapped_column annotations (PEP 681 / SQLAlchemy 2.0).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Shared declarative base for all models."""


# ---------------------------------------------------------------------------
# Trade
# ---------------------------------------------------------------------------

class Trade(Base):
    """Records every trade signal, open position, and closed position."""

    __tablename__ = "trades"

    # ---- primary key --------------------------------------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ---- identity -----------------------------------------------------------
    trade_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    pair: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)

    # ---- entry --------------------------------------------------------------
    entry_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str] = mapped_column(String(4), nullable=False)          # BUY | SELL

    # ---- strategy / pattern -------------------------------------------------
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pattern_detected: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    smc_concept: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # ---- scoring ------------------------------------------------------------
    confluence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # ---- indicator snapshot -------------------------------------------------
    indicators_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # ---- risk levels --------------------------------------------------------
    sl_price: Mapped[float] = mapped_column(Float, nullable=False)
    sl_pips: Mapped[float] = mapped_column(Float, nullable=False)
    tp1_price: Mapped[float] = mapped_column(Float, nullable=False)
    tp2_price: Mapped[float] = mapped_column(Float, nullable=False)
    tp3_price: Mapped[float] = mapped_column(Float, nullable=False)

    # ---- risk / reward ------------------------------------------------------
    risk_amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    risk_pct: Mapped[float] = mapped_column(Float, nullable=False)
    reward_tp1_usd: Mapped[float] = mapped_column(Float, nullable=False)
    reward_tp2_usd: Mapped[float] = mapped_column(Float, nullable=False)
    reward_tp3_usd: Mapped[float] = mapped_column(Float, nullable=False)

    # ---- context ------------------------------------------------------------
    session: Mapped[str] = mapped_column(String(16), nullable=False)           # LONDON/NY/TOKYO/SYDNEY
    news_events_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ---- exit ---------------------------------------------------------------
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    result: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)   # WIN/LOSS/BREAKEVEN
    actual_rr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pips_result: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ---- account snapshot ---------------------------------------------------
    balance_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    balance_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ---- broker / mode ------------------------------------------------------
    is_paper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    oanda_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN", index=True)

    # ---- timestamps ---------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(),
        onupdate=func.now(), server_default=func.now()
    )

    # ---- indexes ------------------------------------------------------------
    __table_args__ = (
        Index("ix_trades_pair_status", "pair", "status"),
        Index("ix_trades_strategy_result", "strategy_name", "result"),
        Index("ix_trades_entry_time", "entry_time"),
    )

    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<Trade id={self.id} trade_id={self.trade_id!r} pair={self.pair!r} "
            f"direction={self.direction!r} status={self.status!r}>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "trade_id": self.trade_id,
            "pair": self.pair,
            "timeframe": self.timeframe,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "entry_price": self.entry_price,
            "direction": self.direction,
            "strategy_name": self.strategy_name,
            "pattern_detected": self.pattern_detected,
            "smc_concept": self.smc_concept,
            "confluence_score": self.confluence_score,
            "confidence_pct": self.confidence_pct,
            "indicators": json.loads(self.indicators_json) if self.indicators_json else {},
            "sl_price": self.sl_price,
            "sl_pips": self.sl_pips,
            "tp1_price": self.tp1_price,
            "tp2_price": self.tp2_price,
            "tp3_price": self.tp3_price,
            "risk_amount_usd": self.risk_amount_usd,
            "risk_pct": self.risk_pct,
            "reward_tp1_usd": self.reward_tp1_usd,
            "reward_tp2_usd": self.reward_tp2_usd,
            "reward_tp3_usd": self.reward_tp3_usd,
            "session": self.session,
            "news_events": json.loads(self.news_events_json) if self.news_events_json else [],
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_price": self.exit_price,
            "exit_reason": self.exit_reason,
            "result": self.result,
            "actual_rr": self.actual_rr,
            "pips_result": self.pips_result,
            "pnl_usd": self.pnl_usd,
            "balance_before": self.balance_before,
            "balance_after": self.balance_after,
            "is_paper": self.is_paper,
            "oanda_order_id": self.oanda_order_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# NewsEvent
# ---------------------------------------------------------------------------

class NewsEvent(Base):
    """Economic calendar events that may affect currency pairs."""

    __tablename__ = "news_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    impact: Mapped[str] = mapped_column(String(8), nullable=False)             # HIGH/MEDIUM/LOW
    scheduled_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    actual_value: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    forecast: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    previous: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    pairs_affected: Mapped[str] = mapped_column(String(256), nullable=False)   # comma-separated
    is_processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_news_scheduled_impact", "scheduled_time", "impact"),
    )

    def __repr__(self) -> str:
        return (
            f"<NewsEvent id={self.id} event_id={self.event_id!r} "
            f"currency={self.currency!r} impact={self.impact!r} "
            f"scheduled_time={self.scheduled_time!r}>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "title": self.title,
            "currency": self.currency,
            "impact": self.impact,
            "scheduled_time": self.scheduled_time.isoformat() if self.scheduled_time else None,
            "actual_value": self.actual_value,
            "forecast": self.forecast,
            "previous": self.previous,
            "pairs_affected": self.pairs_affected.split(",") if self.pairs_affected else [],
            "is_processed": self.is_processed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# StrategyPerformance
# ---------------------------------------------------------------------------

class StrategyPerformance(Base):
    """Aggregated performance metrics per strategy, updated after each trade close."""

    __tablename__ = "strategy_performance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # ---- trade counts -------------------------------------------------------
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    breakevens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ---- performance metrics ------------------------------------------------
    win_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    profit_factor: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_rr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_pnl_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ---- adaptive weighting -------------------------------------------------
    confluence_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ---- timestamps ---------------------------------------------------------
    last_evaluated: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(),
        onupdate=func.now(), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyPerformance strategy={self.strategy_name!r} "
            f"win_rate={self.win_rate:.2f} total_trades={self.total_trades}>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "breakevens": self.breakevens,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "avg_rr": self.avg_rr,
            "total_pnl_usd": self.total_pnl_usd,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "confluence_weight": self.confluence_weight,
            "is_paused": self.is_paused,
            "last_evaluated": self.last_evaluated.isoformat() if self.last_evaluated else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# PriceData
# ---------------------------------------------------------------------------

class PriceData(Base):
    """OHLCV cache for historical and real-time candle data."""

    __tablename__ = "price_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pair: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    open_price: Mapped[float] = mapped_column(Float, nullable=False)
    high_price: Mapped[float] = mapped_column(Float, nullable=False)
    low_price: Mapped[float] = mapped_column(Float, nullable=False)
    close_price: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("pair", "timeframe", "timestamp", name="uq_price_data_pair_tf_ts"),
        Index("ix_price_data_pair_tf_ts", "pair", "timeframe", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<PriceData pair={self.pair!r} timeframe={self.timeframe!r} "
            f"timestamp={self.timestamp!r} close={self.close_price}>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pair": self.pair,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "open": self.open_price,
            "high": self.high_price,
            "low": self.low_price,
            "close": self.close_price,
            "volume": self.volume,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# BotState
# ---------------------------------------------------------------------------

class BotState(Base):
    """Key-value store for persistent bot runtime state."""

    __tablename__ = "bot_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(),
        onupdate=func.now(), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<BotState key={self.key!r} value={self.value!r}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# DailyStats
# ---------------------------------------------------------------------------

class DailyStats(Base):
    """Daily aggregated performance snapshot for the bot."""

    __tablename__ = "daily_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pnl_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    starting_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ending_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<DailyStats date={self.date!r} trades={self.total_trades} "
            f"pnl={self.pnl_usd:.2f}>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date.isoformat() if self.date else None,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "pnl_usd": self.pnl_usd,
            "max_drawdown_pct": self.max_drawdown_pct,
            "starting_balance": self.starting_balance,
            "ending_balance": self.ending_balance,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
