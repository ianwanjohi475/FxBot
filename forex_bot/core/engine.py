"""
Main trading engine — the central bot loop.
Orchestrates: data feeds → strategies → scoring → risk → execution.
"""
import time
import signal
import threading
from datetime import datetime
import pytz
from typing import Optional

import os
from .broker import OANDABroker, MT5Broker
from .execution import ExecutionEngine
from .session import SessionDetector
from .heartbeat import HeartbeatMonitor
from data.live_feed import LiveFeed, MT5LiveFeed
from data.historical import HistoricalData
from data.data_cleaner import DataCleaner
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

PAIRS = [
    "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CHF",
    "NZD_USD", "USD_CAD", "XAU_USD", "GBP_JPY", "EUR_JPY",
]
TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
CANDLE_COUNT = 300
SCAN_INTERVAL = 60  # seconds between full analysis cycles
MAX_OPEN_TRADES = 5
MAX_SPREAD_PIPS = 3.0  # 3x normal average
DANGER_WIDE_SPREAD_MULT = 3.0


class TradingEngine:
    def __init__(self, is_paper: bool = True):
        self.is_paper = is_paper
        self.is_running = False
        self._shutdown_event = threading.Event()

        # Core components — auto-detect broker from env vars
        _use_mt5 = bool(os.getenv("MT5_LOGIN") and os.getenv("MT5_SERVER"))
        if _use_mt5:
            self.broker = MT5Broker()
            self.live_feed = MT5LiveFeed()
            logger.info("[Engine] Broker: MetaTrader 5")
        else:
            self.broker = OANDABroker()
            self.live_feed = LiveFeed()
            logger.info("[Engine] Broker: OANDA")
        self.db = DatabaseManager()
        self.execution: Optional[ExecutionEngine] = None
        self.historical = HistoricalData()

        # Strategy & scoring
        self.strategy_manager = StrategyManager(config.get("strategy_weights", {}))
        self.confluence = ConfluenceEngine(
            min_score=config.get("risk.min_confluence_score", 65)
        )
        self.adaptive = AdaptiveWeighting()

        # Risk
        risk_pct = config.get("risk.risk_per_trade", 0.01)
        self.sizer = PositionSizer(risk_pct)
        self.sl_calc = StopLossCalculator()
        self.tp_calc = TakeProfitCalculator()
        self.trailing = TrailingStop()
        self.drawdown = DrawdownController(
            max_daily_loss=config.get("risk.max_daily_loss", 0.05),
            max_weekly_loss=config.get("risk.max_weekly_loss", 0.10),
        )
        self.correlation = CorrelationFilter()

        # News
        self.news_filter = NewsFilter(config.raw if hasattr(config, "raw") else {})

        # Alerts
        self.telegram = TelegramBot()

        # Monitoring
        self.heartbeat = HeartbeatMonitor(interval=30, on_failure=self._on_heartbeat_failure)

        # Data cache: pair → timeframe → DataFrame
        self._data_cache: dict = {p: {} for p in PAIRS}
        self._account: dict = {}

    def start(self):
        logger.info(f"[Engine] Starting FxBot (paper={self.is_paper})")
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self.broker.connect()
        self.execution = ExecutionEngine(self.broker, self.db, self.is_paper)
        self.live_feed.start()
        self.live_feed.subscribe(self._on_price_tick)
        self.heartbeat.start()

        self._load_initial_data()
        self._update_account()
        self.is_running = True

        self.telegram.send_message("🤖 FxBot started successfully")
        logger.info("[Engine] Bot is live. Starting main loop.")
        self._main_loop()

    def _main_loop(self):
        while self.is_running and not self._shutdown_event.is_set():
            try:
                self._update_account()
                self._check_drawdown_limits()
                self._update_open_trades()
                self._refresh_historical_data()

                # Run strategy analysis on all pairs
                for pair in PAIRS:
                    try:
                        self._analyze_pair(pair)
                    except Exception as e:
                        logger.error(f"[Engine] Error analyzing {pair}: {e}", exc_info=True)

                # Periodic adaptive weight update
                self.adaptive.update_weights()

            except Exception as e:
                logger.error(f"[Engine] Main loop error: {e}", exc_info=True)

            self._shutdown_event.wait(SCAN_INTERVAL)

        logger.info("[Engine] Main loop exited")
        self._shutdown()

    def _analyze_pair(self, pair: str):
        now = datetime.now(tz=pytz.utc)
        price_info = self.live_feed.get_price(pair)
        if not price_info:
            return

        current_price = price_info.get("mid", 0)
        spread_pips = price_info.get("spread_pips", 999)

        # Wide spread check
        normal_spread = self._get_normal_spread(pair)
        if spread_pips > normal_spread * DANGER_WIDE_SPREAD_MULT:
            logger.debug(f"[Engine] {pair} wide spread ({spread_pips:.1f} pips) — skipping")
            return

        # News filter
        can_trade, reason = self.news_filter.can_trade(pair, now)
        if not can_trade:
            logger.debug(f"[Engine] {pair} blocked: {reason}")
            return

        # Open trades limit
        open_trades = self.db.get_open_trades()
        if len(open_trades) >= MAX_OPEN_TRADES:
            return

        # Drawdown pause
        balance = self._account.get("balance", 10000)
        if self.drawdown.should_stop_trading_today(balance):
            return
        if self.drawdown.should_pause_after_losses(now):
            return

        # Get session context
        session_info = SessionDetector.get_session_info(now)
        session = session_info["primary_session"]
        news_events = self.news_filter.get_upcoming_events(pair, hours=4)
        news_risk = self.news_filter.get_news_risk_score(pair, hours_ahead=2)

        data = self._data_cache.get(pair, {})
        if not data:
            return

        # Run all strategies
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
            "session": session,
            "news_events": news_events,
            "news_risk_score": news_risk,
            "spread": spread_pips,
            "account_balance": balance,
        }

        for signal in signals:
            score = self.confluence.score_signal(signal, data, context)
            self._write_chart_signal(signal, score)  # visualise in MT5 chart EA
            if not self.confluence.is_tradeable(score):
                continue

            # Correlation filter
            allowed, corr_reason = self.correlation.can_open_trade(pair, signal.direction)
            if not allowed:
                logger.info(f"[Engine] {pair} correlation block: {corr_reason}")
                continue

            # Calculate position size
            lot_size = self.sizer.calculate_lot_size(
                account_balance=balance,
                entry_price=current_price,
                sl_price=signal.sl_price,
                pair=pair,
            )
            dd_mult = self.drawdown.get_position_size_multiplier(balance)
            lot_size *= dd_mult

            risk_usd = balance * self.sizer.risk_pct

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
                    f"[Engine] TRADE OPENED {trade_id} | {pair} {signal.direction} | "
                    f"score={score:.1f} strategy={signal.strategy_name}"
                )
                break  # One trade per pair per cycle

    def _update_open_trades(self):
        open_trades = self.db.get_open_trades()
        for trade in open_trades:
            pair = trade.pair
            price_info = self.live_feed.get_price(pair)
            if not price_info:
                continue
            current_price = price_info.get("mid", trade.entry_price)

            # Check trailing stop
            new_sl = self.trailing.update(trade.trade_id, current_price,
                                           atr=self._get_atr(pair))
            if new_sl:
                self.execution.modify_sl(trade.trade_id, new_sl)

            # Check if trailing stop triggered close
            if self.trailing.should_close(trade.trade_id, current_price):
                balance = self._account.get("balance", 10000)
                self.execution.close_trade(trade.trade_id, current_price,
                                           "trailing_stop", balance)
                self.correlation.remove_trade(pair)
                self.telegram.notify_trade_close(trade.trade_id, current_price,
                                                  "trailing_stop")
                continue

            # Check TP1 for partial close and breakeven
            direction = trade.direction
            tp1 = trade.tp1_price
            if tp1 and (
                (direction == "BUY" and current_price >= tp1) or
                (direction == "SELL" and current_price <= tp1)
            ):
                # Move SL to breakeven
                self.execution.modify_sl(trade.trade_id, trade.entry_price)
                # Activate trailing stop
                self.trailing.activate(
                    trade.trade_id, trade.entry_price, direction,
                    atr=self._get_atr(pair),
                    activation_price=current_price,
                )

    def _check_drawdown_limits(self):
        balance = self._account.get("balance", 10000)
        self.drawdown.update_balance(balance)
        if self.drawdown.should_stop_trading_today(balance):
            logger.warning("[Engine] Daily loss limit hit — stopping trading")
            self.telegram.send_message("⛔ Daily loss limit reached — trading paused until tomorrow")
        if self.drawdown.should_pause_until_monday(balance):
            logger.warning("[Engine] Weekly loss limit hit")
            self.telegram.send_message("⛔ Weekly loss limit reached — paused until Monday")

    def _load_initial_data(self):
        logger.info("[Engine] Loading initial historical data...")
        for pair in PAIRS:
            self._data_cache[pair] = self.historical.get_multi_timeframe(pair, TIMEFRAMES, CANDLE_COUNT)
        logger.info("[Engine] Historical data loaded")

    def _refresh_historical_data(self):
        for pair in PAIRS:
            for tf in TIMEFRAMES:
                try:
                    gran = __import__("utils.timeframe", fromlist=["tf_to_oanda_granularity"]).tf_to_oanda_granularity(tf)
                    new_candle = self.historical.get_candles(pair, gran, count=5)
                    if not new_candle.empty and tf in self._data_cache.get(pair, {}):
                        existing = self._data_cache[pair][tf]
                        combined = __import__("pandas").concat([existing, new_candle])
                        combined = combined[~combined.index.duplicated(keep="last")].tail(CANDLE_COUNT)
                        self._data_cache[pair][tf] = combined
                except Exception:
                    pass

    def _update_account(self):
        try:
            self._account = self.broker.get_account()
        except Exception as e:
            logger.warning(f"[Engine] Account update failed: {e}")

    def _get_normal_spread(self, pair: str) -> float:
        spreads = config.get("backtesting.spread_pips", {})
        return spreads.get(pair, 2.0)

    def _get_atr(self, pair: str) -> float:
        from indicators.volatility import VolatilityIndicators
        import pandas as pd
        df = self._data_cache.get(pair, {}).get("H1")
        if df is not None and len(df) >= 15:
            atr_s = VolatilityIndicators.atr(df, 14)
            val = atr_s.iloc[-1]
            if not pd.isna(val):
                return val
        return 0.0010

    def _on_price_tick(self, pair: str, price_data: dict):
        """Called on every price tick from live feed."""
        pass  # Heavy logic is in _main_loop scan; ticks are buffered in live_feed.prices

    def _write_chart_signal(self, signal, score: float) -> None:
        """Write signal to MT5 Files folder so the FxBotSignals EA can draw it."""
        try:
            import MetaTrader5 as mt5
            info = mt5.terminal_info()
            if info is None:
                return
            signals_path = os.path.join(info.data_path, "MQL5", "Files", "fxbot_signals.csv")

            # Load existing lines (keep last 100 signals)
            existing: list = []
            if os.path.exists(signals_path):
                with open(signals_path, "r", encoding="utf-8") as fh:
                    existing = fh.readlines()[1:101]  # skip header, keep 100

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
            pass  # silently skip if MT5 not available

    def _on_heartbeat_failure(self):
        logger.error("[Engine] Heartbeat failure detected!")
        self.telegram.send_message("⚠️ FxBot heartbeat failure — possible issue!")

    def _handle_signal(self, signum, frame):
        logger.info(f"[Engine] Signal {signum} received — shutting down")
        self.telegram.send_message("🛑 FxBot received shutdown signal — stopping gracefully")
        self.is_running = False
        self._shutdown_event.set()

    def emergency_stop(self):
        """Close all trades and shut down immediately."""
        logger.warning("[Engine] EMERGENCY STOP — closing all trades")
        self.telegram.send_message("🚨 EMERGENCY STOP — closing all trades!")
        try:
            self.broker.close_all_trades()
        except Exception as e:
            logger.error(f"[Engine] Emergency close error: {e}")
        self.is_running = False
        self._shutdown_event.set()

    def _shutdown(self):
        logger.info("[Engine] Shutting down components")
        self.live_feed.stop()
        self.heartbeat.stop()
        self.telegram.send_message("🔴 FxBot shutdown complete")
        logger.info("[Engine] Shutdown complete")
