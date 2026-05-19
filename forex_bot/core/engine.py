"""
Main trading engine — the central bot loop.
Orchestrates: data feeds → strategies → scoring → risk → execution.

Real-time design:
  • MT5LiveFeed polls every 1 second → prices always fresh
  • _on_price_tick() fires every second → instant TP1/breakeven detection
  • _candle_just_closed() detects M15/H1/H4 candle closes → immediate analysis
  • Main loop runs every 15 seconds as a safety fallback scan
"""
import time
import signal
import threading
from datetime import datetime
import pytz
from typing import Optional, Set

import os
from .broker import OANDABroker, MT5Broker
from .execution import ExecutionEngine
from .session import SessionDetector
from .heartbeat import HeartbeatMonitor
from data.live_feed import LiveFeed, MT5LiveFeed
from data.historical import HistoricalData, OANDA_TO_MT5
from strategies.strategy_manager import StrategyManager
from scoring.confluence_engine import ConfluenceEngine
from scoring.adaptive_weighting import AdaptiveWeighting
from risk.position_sizing import PositionSizer
from risk.stop_loss import StopLossCalculator
from risk.take_profit import TakeProfitCalculator
from risk.trailing_stop import TrailingStop
from risk.drawdown_control import DrawdownController
from risk.correlation_filter import CorrelationFilter
from news.news_filter import NewsFilter
from database.db import DatabaseManager
from alerts.telegram_bot import TelegramBot
from utils.logger import get_logger
from utils.config_loader import config

logger = get_logger(__name__)

# ── Trading universe ──────────────────────────────────────────────────────────
PAIRS       = ["EUR_USD", "USD_JPY", "XAU_USD", "US30_USD"]  # all 4 active pairs
TIMEFRAMES  = ["M15", "H1", "H4", "D1"]
CANDLE_COUNT = 300

# ── Timing ────────────────────────────────────────────────────────────────────
SCAN_INTERVAL       = 15    # seconds — full analysis fallback (candle-close = faster)
NEWS_WRITE_INTERVAL = 1800  # 30 min between news CSV writes

# ── Risk / position limits ────────────────────────────────────────────────────
MAX_OPEN_TRADES       = 2      # max concurrent positions on $100 account
DANGER_WIDE_SPREAD_MULT = 3.0  # skip if spread > 3× normal
FIXED_LOT_SIZE        = 0.03   # every trade uses exactly 0.03 lots
MIN_RR_RATIO          = 1.5    # skip signal if TP1 < 1.5× SL distance

# Timeframes we watch for candle-close events (most reactive → least)
CANDLE_WATCH_TFS = ["M15", "H1", "H4"]


class TradingEngine:
    def __init__(self, is_paper: bool = True):
        self.is_paper = is_paper
        self.is_running = False
        self._shutdown_event = threading.Event()
        self._trade_lock    = threading.Lock()   # guards tick ↔ main-loop trade ops

        # ── Broker auto-detect ────────────────────────────────────────────────
        _use_mt5 = bool(os.getenv("MT5_LOGIN") and os.getenv("MT5_SERVER"))
        if _use_mt5:
            self.broker    = MT5Broker()
            self.live_feed = MT5LiveFeed(pairs=PAIRS)  # feed tracks all 4 pairs
            logger.info("[Engine] Broker: MetaTrader 5")
        else:
            self.broker    = OANDABroker()
            self.live_feed = LiveFeed()
            logger.info("[Engine] Broker: OANDA")

        self.db        = DatabaseManager()
        self.execution: Optional[ExecutionEngine] = None
        self.historical = HistoricalData()

        # ── Strategy & scoring ────────────────────────────────────────────────
        self.strategy_manager = StrategyManager(config.get("strategy_weights", {}))
        self.confluence = ConfluenceEngine(
            min_score=config.get("risk.min_confluence_score", 55)
        )
        self.adaptive = AdaptiveWeighting()

        # ── Risk ──────────────────────────────────────────────────────────────
        self.sizer    = PositionSizer(config.get("risk.risk_per_trade", 0.01))
        self.sl_calc  = StopLossCalculator()
        self.tp_calc  = TakeProfitCalculator()
        self.trailing = TrailingStop()
        self.drawdown = DrawdownController(
            max_daily_loss =config.get("risk.max_daily_loss",  0.05),
            max_weekly_loss=config.get("risk.max_weekly_loss", 0.10),
        )
        self.correlation = CorrelationFilter()

        # ── News ──────────────────────────────────────────────────────────────
        self.news_filter = NewsFilter(config.raw if hasattr(config, "raw") else {})

        # ── Alerts ───────────────────────────────────────────────────────────
        self.telegram = TelegramBot()

        # ── Monitoring ───────────────────────────────────────────────────────
        self.heartbeat = HeartbeatMonitor(interval=30, on_failure=self._on_heartbeat_failure)

        # ── State ─────────────────────────────────────────────────────────────
        self._data_cache:     dict  = {p: {} for p in PAIRS}
        self._account:        dict  = {}
        self._last_news_write: float = 0.0
        # candle-close tracking: "PAIR_TF" → last candle open timestamp (int)
        self._last_candle_ts: dict  = {}
        # pairs flagged by tick handler as needing urgent analysis
        self._urgent_pairs:   Set[str] = set()

    # ══════════════════════════════════════════════════════════════════════════
    # Startup / shutdown
    # ══════════════════════════════════════════════════════════════════════════

    def start(self):
        logger.info(f"[Engine] Starting FxBot (paper={self.is_paper})")
        signal.signal(signal.SIGINT,  self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self.broker.connect()
        self.execution = ExecutionEngine(self.broker, self.db, self.is_paper)
        self.live_feed.start()
        self.live_feed.subscribe(self._on_price_tick)
        self.heartbeat.start()

        self._load_initial_data()
        self._update_account()
        self.is_running = True

        self.telegram.send_message("FxBot started | pairs: " + ", ".join(PAIRS))
        logger.info("[Engine] Bot is live. Starting real-time main loop.")
        self._main_loop()

    def _main_loop(self):
        while self.is_running and not self._shutdown_event.is_set():
            try:
                self._update_account()
                self._check_drawdown_limits()
                self._update_open_trades()       # trailing stops + MT5 sync
                self._refresh_historical_data()  # append latest candles to cache

                # ── Candle-close detection → immediate analysis ───────────────
                candle_pairs: Set[str] = set()
                for pair in PAIRS:
                    for tf in CANDLE_WATCH_TFS:
                        if self._candle_just_closed(pair, tf):
                            candle_pairs.add(pair)
                            logger.info(f"[Engine] {pair} {tf} candle closed — analysing now")
                            break  # one TF trigger per pair per cycle

                # ── Urgent pairs flagged by tick handler ──────────────────────
                with self._trade_lock:
                    urgent = self._urgent_pairs.copy()
                    self._urgent_pairs.clear()
                all_priority = candle_pairs | urgent

                # Priority pairs first, then the rest
                for pair in all_priority:
                    self._safe_analyze(pair)
                for pair in PAIRS:
                    if pair not in all_priority:
                        self._safe_analyze(pair)

                self.adaptive.update_weights()

                now_ts = time.time()
                if now_ts - self._last_news_write >= NEWS_WRITE_INTERVAL:
                    self._write_news_events()
                    self._last_news_write = now_ts

            except Exception as e:
                logger.error(f"[Engine] Main loop error: {e}", exc_info=True)

            self._shutdown_event.wait(SCAN_INTERVAL)

        logger.info("[Engine] Main loop exited")
        self._shutdown()

    def _safe_analyze(self, pair: str):
        try:
            self._analyze_pair(pair)
        except Exception as e:
            logger.error(f"[Engine] Analysis error {pair}: {e}", exc_info=True)

    # ══════════════════════════════════════════════════════════════════════════
    # Real-time tick handler  (runs in LiveFeed background thread every ~1 s)
    # ══════════════════════════════════════════════════════════════════════════

    def _on_price_tick(self, pair: str, price_data: dict):
        """
        Fires every ~1 second per pair.
        Fast path only — no heavy strategy work here.
        Detects TP1 cross and breakeven move in real time.
        """
        if not self.is_running or self.execution is None:
            return
        current = price_data.get("mid", 0)
        if not current:
            return

        try:
            open_trades = self.db.get_open_trades()
            for trade in open_trades:
                if trade.pair != pair:
                    continue

                direction = trade.direction
                tp1       = trade.tp1_price
                entry     = trade.entry_price
                sl        = trade.sl_price

                # ── TP1 hit → move SL to breakeven + start trailing ───────────
                tp1_hit = (
                    tp1 and
                    sl != entry and          # not already at breakeven
                    not self.trailing.active_trails.get(trade.trade_id) and
                    (
                        (direction == "BUY"  and current >= tp1) or
                        (direction == "SELL" and current <= tp1)
                    )
                )
                if tp1_hit:
                    with self._trade_lock:
                        self.execution.modify_sl(trade.trade_id, entry)
                        self.trailing.activate(
                            trade.trade_id, entry, direction,
                            atr=self._get_atr(pair),
                            activation_price=current,
                        )
                    logger.info(
                        f"[Engine] {pair} TP1 reached @ {current:.5f} — "
                        f"SL moved to breakeven {entry:.5f}"
                    )

                # ── Flag pair for priority analysis on big price move ─────────
                atr = self._get_atr(pair)
                if atr > 0:
                    move = abs(current - entry)
                    if move > atr * 0.5:   # half ATR move = significant candle body
                        with self._trade_lock:
                            self._urgent_pairs.add(pair)

        except Exception:
            pass   # tick handler must never crash

    # ══════════════════════════════════════════════════════════════════════════
    # Candle-close detection
    # ══════════════════════════════════════════════════════════════════════════

    def _candle_just_closed(self, pair: str, tf: str) -> bool:
        """
        Returns True once per candle close for each pair+timeframe.
        Compares the current candle's open timestamp against the last seen one.
        """
        if not isinstance(self.broker, MT5Broker):
            return False
        try:
            import MetaTrader5 as mt5
            tf_map = {
                "M15": mt5.TIMEFRAME_M15,
                "H1":  mt5.TIMEFRAME_H1,
                "H4":  mt5.TIMEFRAME_H4,
                "D1":  mt5.TIMEFRAME_D1,
            }
            mt5_tf = tf_map.get(tf)
            if mt5_tf is None:
                return False
            symbol = OANDA_TO_MT5.get(pair, pair.replace("_", ""))
            rates  = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, 1)
            if rates is None or len(rates) == 0:
                return False
            current_ts = int(rates[0]["time"])
            key        = f"{pair}_{tf}"
            prev_ts    = self._last_candle_ts.get(key, 0)
            self._last_candle_ts[key] = current_ts
            if prev_ts == 0:
                return False   # first call — just initialise timestamp
            return current_ts != prev_ts
        except Exception:
            return False

    # ══════════════════════════════════════════════════════════════════════════
    # Core analysis
    # ══════════════════════════════════════════════════════════════════════════

    def _analyze_pair(self, pair: str):
        now = datetime.now(tz=pytz.utc)
        price_info = self.live_feed.get_price(pair)
        if not price_info:
            return

        current_price = price_info.get("mid", 0)
        spread_pips   = price_info.get("spread_pips", 999)

        # Wide spread check (news spike / thin market)
        normal_spread = self._get_normal_spread(pair)
        if spread_pips > normal_spread * DANGER_WIDE_SPREAD_MULT:
            logger.debug(f"[Engine] {pair} spread {spread_pips:.1f} pips — skipping")
            return

        # News blackout
        can_trade, reason = self.news_filter.can_trade(pair, now)
        if not can_trade:
            logger.debug(f"[Engine] {pair} news block: {reason}")
            return

        # Position limits
        open_trades = self.db.get_open_trades()
        if len(open_trades) >= MAX_OPEN_TRADES:
            return
        if any(t.pair == pair for t in open_trades):
            return   # already have a trade on this pair

        # Drawdown guards
        balance = self._account.get("balance", 10000)
        if self.drawdown.should_stop_trading_today(balance):
            return
        if self.drawdown.should_pause_after_losses(now):
            return

        data = self._data_cache.get(pair, {})
        if not data:
            return

        session_info = SessionDetector.get_session_info(now)
        session      = session_info["primary_session"]
        news_events  = self.news_filter.get_upcoming_events(pair, hours=4)
        news_risk    = self.news_filter.get_news_risk_score(pair, hours_ahead=2)

        signals = self.strategy_manager.analyze_all(
            data=data,
            pair=pair,
            current_price=current_price,
            spread_pips=spread_pips,
            session=session,
            news_events=news_events,
            current_time=now,
        )

        context = {
            "session":        session,
            "news_events":    news_events,
            "news_risk_score": news_risk,
            "spread":         spread_pips,
            "account_balance": balance,
        }

        for signal in signals:
            score = self.confluence.score_signal(signal, data, context)
            self._write_chart_signal(signal, score)   # always draw — even if not traded
            if not self.confluence.is_tradeable(score):
                continue

            # Minimum R:R gate
            risk_dist   = abs(signal.entry_price - signal.sl_price)
            reward_dist = abs(signal.tp1_price   - signal.entry_price)
            if risk_dist == 0 or (reward_dist / risk_dist) < MIN_RR_RATIO:
                logger.debug(f"[Engine] {pair} RR={reward_dist/max(risk_dist,1e-9):.2f} < {MIN_RR_RATIO} — skip")
                continue

            # Correlation guard
            allowed, corr_reason = self.correlation.can_open_trade(pair, signal.direction)
            if not allowed:
                logger.info(f"[Engine] {pair} correlation block: {corr_reason}")
                continue

            lot_size = FIXED_LOT_SIZE
            risk_usd = round(lot_size * risk_dist * 10000 * 10, 2)

            trade_id = self.execution.open_trade(
                signal=signal,
                lot_size=lot_size,
                account_balance=balance,
                risk_amount_usd=risk_usd,
                session=session,
                news_events=news_events,
            )

            if trade_id:
                self.correlation.add_trade(pair, signal.direction)
                self.telegram.notify_trade_open(signal, trade_id, lot_size, risk_usd)
                logger.info(
                    f"[Engine] TRADE OPENED {trade_id} | {pair} {signal.direction} "
                    f"@ {signal.entry_price} SL={signal.sl_price} TP1={signal.tp1_price} "
                    f"lot={lot_size} score={score:.1f} strat={signal.strategy_name}"
                )
                break   # one trade per pair per cycle

    # ══════════════════════════════════════════════════════════════════════════
    # Open trade management
    # ══════════════════════════════════════════════════════════════════════════

    def _sync_mt5_positions(self) -> None:
        """Detect positions MT5 closed (SL/TP hit) and mark them in our DB."""
        if not isinstance(self.broker, MT5Broker):
            return
        try:
            open_db = self.db.get_open_trades()
            if not open_db:
                return
            live_tickets = {t["id"] for t in self.broker.get_open_trades()}
            balance = self._account.get("balance", 10000)
            for trade in open_db:
                ticket = trade.oanda_order_id
                if not ticket or ticket in live_tickets:
                    continue
                price_info = self.live_feed.get_price(trade.pair)
                exit_price = price_info.get("mid", trade.entry_price) if price_info else trade.entry_price
                result = self.execution.close_trade(
                    trade.trade_id, exit_price, "sl_tp_hit", balance
                )
                pnl = result.get("pnl_usd", 0)
                if pnl > 0:
                    self.drawdown.register_win()
                else:
                    self.drawdown.register_loss()
                self.correlation.remove_trade(trade.pair)
                self.telegram.notify_trade_close(trade.trade_id, exit_price, "sl_tp_hit")
                logger.info(
                    f"[Engine] {trade.pair} {trade.trade_id} closed by MT5 "
                    f"| exit={exit_price} pnl={pnl:+.2f}"
                )
        except Exception as e:
            logger.debug(f"[Engine] MT5 sync error: {e}")

    def _update_open_trades(self):
        self._sync_mt5_positions()

        open_trades = self.db.get_open_trades()
        for trade in open_trades:
            pair       = trade.pair
            price_info = self.live_feed.get_price(pair)
            if not price_info:
                continue
            current = price_info.get("mid", trade.entry_price)
            atr     = self._get_atr(pair)

            with self._trade_lock:
                # Update trailing stop
                new_sl = self.trailing.update(trade.trade_id, current, atr)
                if new_sl:
                    self.execution.modify_sl(trade.trade_id, new_sl)
                    logger.info(f"[Engine] {pair} trailing SL → {new_sl:.5f}")

                # Trailing stop triggered close
                if self.trailing.should_close(trade.trade_id, current):
                    balance = self._account.get("balance", 10000)
                    result  = self.execution.close_trade(
                        trade.trade_id, current, "trailing_stop", balance
                    )
                    pnl = result.get("pnl_usd", 0)
                    if pnl > 0:
                        self.drawdown.register_win()
                    else:
                        self.drawdown.register_loss()
                    self.correlation.remove_trade(pair)
                    self.telegram.notify_trade_close(trade.trade_id, current, "trailing_stop")
                    logger.info(f"[Engine] {pair} trailing stop closed | pnl={pnl:+.2f}")

    # ══════════════════════════════════════════════════════════════════════════
    # Data management
    # ══════════════════════════════════════════════════════════════════════════

    def _load_initial_data(self):
        logger.info("[Engine] Loading initial historical data...")
        for pair in PAIRS:
            self._data_cache[pair] = self.historical.get_multi_timeframe(
                pair, TIMEFRAMES, CANDLE_COUNT
            )
            # Prime candle timestamps so first real close is detected correctly
            for tf in CANDLE_WATCH_TFS:
                self._candle_just_closed(pair, tf)
        logger.info("[Engine] Historical data loaded")

    def _refresh_historical_data(self):
        import pandas as pd
        from utils.timeframe import tf_to_oanda_granularity
        for pair in PAIRS:
            for tf in TIMEFRAMES:
                try:
                    gran       = tf_to_oanda_granularity(tf)
                    new_candle = self.historical.get_candles(pair, gran, count=5)
                    if not new_candle.empty and tf in self._data_cache.get(pair, {}):
                        existing = self._data_cache[pair][tf]
                        combined = pd.concat([existing, new_candle])
                        combined = combined[~combined.index.duplicated(keep="last")].tail(CANDLE_COUNT)
                        self._data_cache[pair][tf] = combined
                except Exception:
                    pass

    # ══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _update_account(self):
        try:
            self._account = self.broker.get_account()
        except Exception as e:
            logger.warning(f"[Engine] Account update failed: {e}")

    def _check_drawdown_limits(self):
        balance = self._account.get("balance", 10000)
        self.drawdown.update_balance(balance)
        if self.drawdown.should_stop_trading_today(balance):
            logger.warning("[Engine] Daily loss limit — trading paused")
            self.telegram.send_message("Daily loss limit reached — paused until tomorrow")
        if self.drawdown.should_pause_until_monday(balance):
            logger.warning("[Engine] Weekly loss limit")
            self.telegram.send_message("Weekly loss limit — paused until Monday")

    def _get_normal_spread(self, pair: str) -> float:
        return config.get("backtesting.spread_pips", {}).get(pair, 2.0)

    def _get_atr(self, pair: str) -> float:
        from indicators.volatility import VolatilityIndicators
        import pandas as pd
        df = self._data_cache.get(pair, {}).get("H1")
        if df is not None and len(df) >= 15:
            atr_s = VolatilityIndicators.atr(df, 14)
            val   = atr_s.iloc[-1]
            if not pd.isna(val):
                return float(val)
        return 0.0010   # fallback ≈ 10 pips EURUSD

    def _write_chart_signal(self, signal, score: float) -> None:
        """Write signal to MT5 Files folder so the FxBotSignals EA can draw it."""
        try:
            import MetaTrader5 as mt5
            info = mt5.terminal_info()
            if info is None:
                return
            signals_path = os.path.join(info.data_path, "MQL5", "Files", "fxbot_signals.csv")
            existing: list = []
            if os.path.exists(signals_path):
                with open(signals_path, "r", encoding="utf-8") as fh:
                    existing = fh.readlines()[1:101]
            ts = datetime.now(tz=pytz.utc).strftime("%Y.%m.%d %H:%M:%S")
            new_line = (
                f"{signal.pair},{signal.direction},"
                f"{signal.entry_price:.5f},{signal.sl_price:.5f},"
                f"{signal.tp1_price:.5f},{signal.tp2_price:.5f},{signal.tp3_price:.5f},"
                f"{signal.strategy_name},{score:.1f},{ts}\n"
            )
            with open(signals_path, "w", encoding="utf-8") as fh:
                fh.write("pair,direction,entry,sl,tp1,tp2,tp3,strategy,score,timestamp\n")
                fh.write(new_line)
                fh.writelines(existing)
        except Exception:
            pass

    def _write_news_events(self) -> None:
        try:
            import MetaTrader5 as mt5
            info = mt5.terminal_info()
            if info is None:
                return
            news_path = os.path.join(info.data_path, "MQL5", "Files", "fxbot_news.csv")
            if self.news_filter._should_refresh():
                self.news_filter.refresh_calendar()
            events = self.news_filter.upcoming
            est = pytz.timezone("America/New_York")
            with open(news_path, "w", encoding="utf-8") as fh:
                fh.write("currency,impact,event,scheduled_time\n")
                for ev in events:
                    ev_time = ev.get("time")
                    if ev_time is None:
                        continue
                    if hasattr(ev_time, "tzinfo") and ev_time.tzinfo is None:
                        ev_time = est.localize(ev_time)
                    ts_str   = ev_time.strftime("%Y.%m.%d %H:%M:%S")
                    currency = str(ev.get("currency", "")).replace(",", "")
                    impact   = str(ev.get("impact",   "LOW"))
                    name     = str(ev.get("event",    "")).replace(",", " ")
                    fh.write(f"{currency},{impact},{name},{ts_str}\n")
            logger.info(f"[Engine] Wrote {len(events)} news events to MT5 chart")
        except Exception as e:
            logger.debug(f"[Engine] News write skipped: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Lifecycle callbacks
    # ══════════════════════════════════════════════════════════════════════════

    def _on_heartbeat_failure(self):
        logger.error("[Engine] Heartbeat failure detected!")
        self.telegram.send_message("FxBot heartbeat failure — check the bot!")

    def _handle_signal(self, signum, frame):
        logger.info(f"[Engine] Signal {signum} — shutting down gracefully")
        self.telegram.send_message("FxBot shutdown signal received — stopping")
        self.is_running = False
        self._shutdown_event.set()

    def emergency_stop(self):
        logger.warning("[Engine] EMERGENCY STOP — closing all trades")
        self.telegram.send_message("EMERGENCY STOP — closing all trades!")
        try:
            self.broker.close_all_trades()
        except Exception as e:
            logger.error(f"[Engine] Emergency close error: {e}")
        self.is_running = False
        self._shutdown_event.set()

    def _shutdown(self):
        logger.info("[Engine] Shutting down")
        self.live_feed.stop()
        self.heartbeat.stop()
        self.telegram.send_message("FxBot shutdown complete")
        logger.info("[Engine] Shutdown complete")
