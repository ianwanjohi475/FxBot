"""
Database manager for the Forex trading bot.

Uses SQLAlchemy 2.0 with a thread-safe singleton engine and scoped sessions.
All public helper functions operate on a single shared DatabaseManager instance
so the rest of the codebase can simply call module-level convenience functions.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator, List, Optional

import pandas as pd
from sqlalchemy import and_, create_engine, select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from .models import (
    Base,
    BotState,
    DailyStats,
    NewsEvent,
    PriceData,
    StrategyPerformance,
    Trade,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default database URL — override with the FXBOT_DATABASE_URL env variable.
# ---------------------------------------------------------------------------
_DEFAULT_DB_URL = os.environ.get(
    "FXBOT_DATABASE_URL",
    f"sqlite:///{os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'fxbot.db')}",
)


# ---------------------------------------------------------------------------
# Singleton DatabaseManager
# ---------------------------------------------------------------------------

class DatabaseManager:
    """Thread-safe singleton that owns the SQLAlchemy engine and session factory."""

    _instance: Optional[DatabaseManager] = None
    _lock: threading.Lock = threading.Lock()

    # ------------------------------------------------------------------
    # Construction / singleton boilerplate
    # ------------------------------------------------------------------

    def __new__(cls, db_url: str = _DEFAULT_DB_URL) -> DatabaseManager:
        with cls._lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._initialised = False
                cls._instance = instance
            return cls._instance

    def __init__(self, db_url: str = _DEFAULT_DB_URL) -> None:
        if self._initialised:
            return
        with self._lock:
            if self._initialised:
                return
            self._db_url = db_url
            connect_args: dict = {}
            if db_url.startswith("sqlite"):
                # SQLite needs check_same_thread=False for multi-threaded usage.
                connect_args = {"check_same_thread": False}
                # Ensure the parent directory exists.
                db_path = db_url.replace("sqlite:///", "")
                os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

            self._engine = create_engine(
                db_url,
                connect_args=connect_args,
                echo=False,
                pool_pre_ping=True,
                pool_recycle=3600,
            )
            self._session_factory = sessionmaker(
                bind=self._engine, autoflush=True, autocommit=False
            )
            self._Session = scoped_session(self._session_factory)
            self._initialised = True
            logger.info("DatabaseManager initialised with URL: %s", db_url)

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """Create all tables defined in Base.metadata (idempotent)."""
        Base.metadata.create_all(self._engine)
        logger.info("Database tables created / verified.")

    # ------------------------------------------------------------------
    # Session context manager
    # ------------------------------------------------------------------

    @contextmanager
    def get_db(self) -> Generator[Session, None, None]:
        """Yield a scoped Session; commit on success, rollback on error."""
        session: Session = self._Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            self._Session.remove()

    # ------------------------------------------------------------------
    # Trade helpers
    # ------------------------------------------------------------------

    def save_trade(self, trade_data: dict) -> Trade:
        """
        Persist a new trade record.

        ``trade_data`` may contain an ``indicators`` key (dict) or
        ``indicators_json`` key (str); likewise ``news_events`` (list) or
        ``news_events_json`` (str).
        """
        data = _normalise_trade_data(trade_data)
        trade = Trade(**data)
        with self.get_db() as session:
            session.add(trade)
            session.flush()
            session.refresh(trade)
            # Detach so the object can be used after the session closes.
            session.expunge(trade)
        logger.debug("Saved trade %s", trade.trade_id)
        return trade

    def update_trade(self, trade_id: str, updates: dict) -> Trade:
        """
        Apply ``updates`` to the trade identified by ``trade_id``.

        Handles ``indicators`` -> ``indicators_json`` and
        ``news_events`` -> ``news_events_json`` conversion automatically.
        """
        updates = dict(updates)  # shallow copy; don't mutate caller's dict
        if "indicators" in updates and "indicators_json" not in updates:
            updates["indicators_json"] = json.dumps(updates.pop("indicators"))
        elif "indicators" in updates:
            updates.pop("indicators")

        if "news_events" in updates and "news_events_json" not in updates:
            updates["news_events_json"] = json.dumps(updates.pop("news_events"))
        elif "news_events" in updates:
            updates.pop("news_events")

        with self.get_db() as session:
            trade = session.scalars(
                select(Trade).where(Trade.trade_id == trade_id)
            ).one_or_none()
            if trade is None:
                raise ValueError(f"Trade not found: {trade_id!r}")
            for key, value in updates.items():
                setattr(trade, key, value)
            trade.updated_at = datetime.now(tz=timezone.utc)
            session.flush()
            session.refresh(trade)
            session.expunge(trade)
        logger.debug("Updated trade %s", trade_id)
        return trade

    def get_open_trades(self) -> List[Trade]:
        """Return all trades with status='OPEN'."""
        with self.get_db() as session:
            trades = session.scalars(
                select(Trade).where(Trade.status == "OPEN").order_by(Trade.entry_time)
            ).all()
            for t in trades:
                session.expunge(t)
        return list(trades)

    def get_trades(
        self,
        pair: Optional[str] = None,
        strategy: Optional[str] = None,
        result: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Trade]:
        """
        Flexible trade query with optional filters.

        All datetime arguments should be timezone-aware UTC; naive datetimes
        are accepted and treated as UTC.
        """
        conditions = []
        if pair:
            conditions.append(Trade.pair == pair)
        if strategy:
            conditions.append(Trade.strategy_name == strategy)
        if result:
            conditions.append(Trade.result == result)
        if start_date:
            conditions.append(Trade.entry_time >= _ensure_naive(start_date))
        if end_date:
            conditions.append(Trade.entry_time <= _ensure_naive(end_date))

        stmt = select(Trade)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.order_by(Trade.entry_time.desc())
        if limit:
            stmt = stmt.limit(limit)

        with self.get_db() as session:
            trades = session.scalars(stmt).all()
            for t in trades:
                session.expunge(t)
        return list(trades)

    def get_trade_by_id(self, trade_id: str) -> Optional[Trade]:
        """Return a single trade by its unique trade_id, or None."""
        with self.get_db() as session:
            trade = session.scalars(
                select(Trade).where(Trade.trade_id == trade_id)
            ).one_or_none()
            if trade is not None:
                session.expunge(trade)
        return trade

    # ------------------------------------------------------------------
    # News event helpers
    # ------------------------------------------------------------------

    def save_news_event(self, event_data: dict) -> NewsEvent:
        """
        Insert or update a news event by ``event_id``.

        Uses SQLite's INSERT OR REPLACE via ``on_conflict_do_update`` when
        the driver supports it, otherwise falls back to a plain upsert.
        """
        data = dict(event_data)
        if isinstance(data.get("pairs_affected"), list):
            data["pairs_affected"] = ",".join(data["pairs_affected"])

        with self.get_db() as session:
            existing = session.scalars(
                select(NewsEvent).where(NewsEvent.event_id == data["event_id"])
            ).one_or_none()
            if existing is not None:
                for k, v in data.items():
                    setattr(existing, k, v)
                event = existing
            else:
                event = NewsEvent(**data)
                session.add(event)
            session.flush()
            session.refresh(event)
            session.expunge(event)
        return event

    def get_upcoming_news(self, hours_ahead: int = 4) -> List[NewsEvent]:
        """Return unprocessed news events scheduled within the next ``hours_ahead`` hours."""
        now = datetime.utcnow()
        cutoff = now + timedelta(hours=hours_ahead)
        with self.get_db() as session:
            events = session.scalars(
                select(NewsEvent)
                .where(
                    and_(
                        NewsEvent.scheduled_time >= now,
                        NewsEvent.scheduled_time <= cutoff,
                        NewsEvent.is_processed == False,  # noqa: E712
                    )
                )
                .order_by(NewsEvent.scheduled_time)
            ).all()
            for e in events:
                session.expunge(e)
        return list(events)

    def get_news_by_currency(self, currency: str) -> List[NewsEvent]:
        """Return all news events for a given currency code (e.g. 'USD')."""
        with self.get_db() as session:
            events = session.scalars(
                select(NewsEvent)
                .where(NewsEvent.currency == currency)
                .order_by(NewsEvent.scheduled_time.desc())
            ).all()
            for e in events:
                session.expunge(e)
        return list(events)

    # ------------------------------------------------------------------
    # Strategy performance helpers
    # ------------------------------------------------------------------

    def update_strategy_performance(self, strategy_name: str, stats: dict) -> None:
        """
        Upsert strategy performance metrics.

        ``stats`` keys should match StrategyPerformance column names, minus
        ``strategy_name``, ``id``, and ``updated_at``.
        """
        with self.get_db() as session:
            perf = session.scalars(
                select(StrategyPerformance).where(
                    StrategyPerformance.strategy_name == strategy_name
                )
            ).one_or_none()
            if perf is None:
                perf = StrategyPerformance(strategy_name=strategy_name)
                session.add(perf)
            for key, value in stats.items():
                if hasattr(perf, key):
                    setattr(perf, key, value)
            perf.updated_at = datetime.now(tz=timezone.utc)
            session.flush()

    def get_all_strategy_performance(self) -> List[StrategyPerformance]:
        """Return all strategy performance records ordered by total PnL descending."""
        with self.get_db() as session:
            perfs = session.scalars(
                select(StrategyPerformance).order_by(
                    StrategyPerformance.total_pnl_usd.desc()
                )
            ).all()
            for p in perfs:
                session.expunge(p)
        return list(perfs)

    # ------------------------------------------------------------------
    # Bot state helpers
    # ------------------------------------------------------------------

    def get_bot_state(self, key: str) -> Optional[str]:
        """Return the string value stored for ``key``, or None if absent."""
        with self.get_db() as session:
            row = session.scalars(
                select(BotState).where(BotState.key == key)
            ).one_or_none()
            if row is not None:
                session.expunge(row)
                return row.value
        return None

    def set_bot_state(self, key: str, value: str) -> None:
        """Insert or replace a key-value pair in the bot state store."""
        with self.get_db() as session:
            row = session.scalars(
                select(BotState).where(BotState.key == key)
            ).one_or_none()
            if row is None:
                row = BotState(key=key, value=value)
                session.add(row)
            else:
                row.value = value
                row.updated_at = datetime.now(tz=timezone.utc)
            session.flush()

    # ------------------------------------------------------------------
    # Daily stats helpers
    # ------------------------------------------------------------------

    def save_daily_stats(self, stats: dict) -> None:
        """
        Upsert daily statistics for a specific date.

        ``stats`` must contain a ``date`` key (``datetime.date`` or ISO string).
        """
        data = dict(stats)
        if isinstance(data.get("date"), str):
            from datetime import date as date_type
            data["date"] = date_type.fromisoformat(data["date"])

        with self.get_db() as session:
            existing = session.scalars(
                select(DailyStats).where(DailyStats.date == data["date"])
            ).one_or_none()
            if existing is None:
                existing = DailyStats(**data)
                session.add(existing)
            else:
                for key, value in data.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
            session.flush()

    def get_daily_stats(self, days: int = 30) -> List[DailyStats]:
        """Return daily stats for the last ``days`` calendar days, newest first."""
        from datetime import date as date_type, timedelta as td
        cutoff = date_type.today() - td(days=days)
        with self.get_db() as session:
            rows = session.scalars(
                select(DailyStats)
                .where(DailyStats.date >= cutoff)
                .order_by(DailyStats.date.desc())
            ).all()
            for r in rows:
                session.expunge(r)
        return list(rows)

    # ------------------------------------------------------------------
    # Price data helpers
    # ------------------------------------------------------------------

    def bulk_save_price_data(self, records: List[dict]) -> None:
        """
        Efficiently upsert a batch of OHLCV candle records.

        Each record must contain: pair, timeframe, timestamp, open_price,
        high_price, low_price, close_price.  ``volume`` is optional.

        Duplicate (pair, timeframe, timestamp) rows are silently ignored
        (INSERT OR IGNORE semantics via on_conflict_do_nothing for SQLite,
        or a plain try/except fallback for other dialects).
        """
        if not records:
            return

        db_url = self._db_url
        with self.get_db() as session:
            if db_url.startswith("sqlite"):
                stmt = sqlite_insert(PriceData).prefix_with("OR IGNORE")
                session.execute(stmt, records)
            else:
                # Generic fallback: filter out already-existing rows first.
                for rec in records:
                    ts = rec["timestamp"]
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts)
                    exists = session.scalars(
                        select(PriceData).where(
                            and_(
                                PriceData.pair == rec["pair"],
                                PriceData.timeframe == rec["timeframe"],
                                PriceData.timestamp == ts,
                            )
                        )
                    ).one_or_none()
                    if exists is None:
                        session.add(PriceData(**rec))
            session.flush()

    def get_price_data(
        self,
        pair: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Return OHLCV candles for ``pair``/``timeframe`` between ``start`` and ``end``.

        Returns a :class:`pandas.DataFrame` indexed by ``timestamp`` with columns:
        ``open``, ``high``, ``low``, ``close``, ``volume``.

        An empty DataFrame (with the same columns) is returned when no data is found.
        """
        columns = ["open", "high", "low", "close", "volume"]
        with self.get_db() as session:
            rows = session.scalars(
                select(PriceData)
                .where(
                    and_(
                        PriceData.pair == pair,
                        PriceData.timeframe == timeframe,
                        PriceData.timestamp >= _ensure_naive(start),
                        PriceData.timestamp <= _ensure_naive(end),
                    )
                )
                .order_by(PriceData.timestamp)
            ).all()

        if not rows:
            return pd.DataFrame(columns=columns)

        data = {
            "timestamp": [r.timestamp for r in rows],
            "open": [r.open_price for r in rows],
            "high": [r.high_price for r in rows],
            "low": [r.low_price for r in rows],
            "close": [r.close_price for r in rows],
            "volume": [r.volume for r in rows],
        }
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        return df

    # ------------------------------------------------------------------
    # Health / maintenance
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Return True if the database is reachable."""
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:  # pragma: no cover
            logger.error("Database ping failed: %s", exc)
            return False

    def dispose(self) -> None:
        """Dispose the connection pool (call on shutdown)."""
        self._engine.dispose()
        logger.info("Database connection pool disposed.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise_trade_data(data: dict) -> dict:
    """Coerce ``indicators`` / ``news_events`` dict/list values to JSON strings."""
    data = dict(data)
    if "indicators" in data and "indicators_json" not in data:
        data["indicators_json"] = json.dumps(data.pop("indicators"))
    elif "indicators" in data:
        data.pop("indicators")

    if "news_events" in data and "news_events_json" not in data:
        data["news_events_json"] = json.dumps(data.pop("news_events"))
    elif "news_events" in data:
        data.pop("news_events")

    return data


def _ensure_naive(dt: datetime) -> datetime:
    """Strip timezone info from a datetime so SQLite comparisons work correctly."""
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


# ---------------------------------------------------------------------------
# Module-level singleton and convenience API
# ---------------------------------------------------------------------------

_manager: Optional[DatabaseManager] = None


def _get_manager() -> DatabaseManager:
    global _manager
    if _manager is None:
        _manager = DatabaseManager()
    return _manager


# ---- public API used throughout the rest of the codebase ----------------

def init_db(db_url: str = _DEFAULT_DB_URL) -> None:
    """Initialise the database (create tables).  Call once at startup."""
    global _manager
    _manager = DatabaseManager(db_url)
    _manager.init_db()


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager that yields a SQLAlchemy :class:`Session`."""
    with _get_manager().get_db() as session:
        yield session


def save_trade(trade_data: dict) -> Trade:
    return _get_manager().save_trade(trade_data)


def update_trade(trade_id: str, updates: dict) -> Trade:
    return _get_manager().update_trade(trade_id, updates)


def get_open_trades() -> List[Trade]:
    return _get_manager().get_open_trades()


def get_trades(
    pair: Optional[str] = None,
    strategy: Optional[str] = None,
    result: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> List[Trade]:
    return _get_manager().get_trades(
        pair=pair,
        strategy=strategy,
        result=result,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


def get_trade_by_id(trade_id: str) -> Optional[Trade]:
    return _get_manager().get_trade_by_id(trade_id)


def save_news_event(event_data: dict) -> NewsEvent:
    return _get_manager().save_news_event(event_data)


def get_upcoming_news(hours_ahead: int = 4) -> List[NewsEvent]:
    return _get_manager().get_upcoming_news(hours_ahead)


def get_news_by_currency(currency: str) -> List[NewsEvent]:
    return _get_manager().get_news_by_currency(currency)


def update_strategy_performance(strategy_name: str, stats: dict) -> None:
    return _get_manager().update_strategy_performance(strategy_name, stats)


def get_all_strategy_performance() -> List[StrategyPerformance]:
    return _get_manager().get_all_strategy_performance()


def get_bot_state(key: str) -> Optional[str]:
    return _get_manager().get_bot_state(key)


def set_bot_state(key: str, value: str) -> None:
    return _get_manager().set_bot_state(key, value)


def save_daily_stats(stats: dict) -> None:
    return _get_manager().save_daily_stats(stats)


def get_daily_stats(days: int = 30) -> List[DailyStats]:
    return _get_manager().get_daily_stats(days)


def bulk_save_price_data(records: List[dict]) -> None:
    return _get_manager().bulk_save_price_data(records)


def get_price_data(
    pair: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    return _get_manager().get_price_data(pair, timeframe, start, end)
