"""
FxBot — Production-Grade Forex Trading Bot
Entry point: python main.py           (paper trading mode)
             python main.py --live    (live trading — real money!)
"""
import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap: load .env, ensure the package root is on sys.path
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, ".env"), override=False)
load_dotenv(os.path.join(os.path.dirname(_HERE), ".env"), override=False)
sys.path.insert(0, _HERE)

from utils.config_loader import ConfigLoader
from utils.logger import setup_logger


def parse_args():
    parser = argparse.ArgumentParser(
        description="FxBot — Forex Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                 # Paper trading (safe, default)
  python main.py --live          # Live trading with real money
  python main.py --backtest      # Run backtests and exit
  python main.py --pairs EURUSD GBPUSD  # Override pairs
        """,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--live",
        action="store_true",
        help="Enable LIVE trading (real money). Default is paper trading.",
    )
    mode.add_argument(
        "--paper",
        action="store_true",
        default=True,
        help="Paper trading mode (default — simulated orders, real prices).",
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Run backtests for all configured pairs and exit.",
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        metavar="PAIR",
        help="Override pairs to trade (e.g. EUR_USD GBP_USD).",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    return parser.parse_args()


def confirm_live_mode() -> bool:
    """Require confirmation before enabling live trading.
    Skips the prompt automatically when MT5 is configured (demo account)."""
    has_mt5 = os.getenv("MT5_LOGIN") and os.getenv("MT5_SERVER")
    if has_mt5:
        # MT5 is always a demo/practice account — safe to auto-confirm
        print("\n" + "=" * 60)
        print("  MT5 LIVE MODE — Exness Demo Account")
        print("=" * 60)
        print(f"  Login : {os.getenv('MT5_LOGIN')}")
        print(f"  Server: {os.getenv('MT5_SERVER')}")
        print("  Orders will be executed on your MT5 demo account.")
        print("=" * 60)
        return True

    # OANDA real money — require explicit confirmation
    print("\n" + "=" * 60)
    print("  WARNING: LIVE TRADING WITH REAL MONEY")
    print("=" * 60)
    print("Ensure you have:")
    print("  • A funded OANDA account configured in .env")
    print("  • Tested thoroughly in paper mode first")
    print("  • Set appropriate risk limits in config.yaml")
    print("=" * 60)
    answer = input("\nType 'YES I UNDERSTAND' to proceed: ").strip()
    return answer == "YES I UNDERSTAND"


def run_backtest_mode(config, logger):
    """Run backtests for all configured pairs and print a summary."""
    from backtest.backtest_engine import BacktestEngine
    from backtest.data_downloader import DataDownloader
    from backtest.monte_carlo import MonteCarloSimulator
    from backtest.walk_forward import WalkForwardOptimizer

    pairs = config.get("trading", {}).get("pairs", ["EUR_USD"])
    years = config.get("backtesting", {}).get("years_of_data", 3)
    balance = config.get("backtesting", {}).get("initial_balance", 10000)
    risk_pct = config.get("risk", {}).get("risk_per_trade_pct", 0.01)

    logger.info(f"Starting backtest — {len(pairs)} pairs, {years} years of data")
    downloader = DataDownloader()

    for pair in pairs:
        logger.info(f"Downloading historical data for {pair}…")
        try:
            df = downloader.download_pair(pair, years=years)
            if df is None or df.empty:
                logger.warning(f"No data for {pair}, skipping.")
                continue

            engine = BacktestEngine(initial_balance=balance, risk_pct=risk_pct)
            result = engine.run(pair, df)
            summary = result.get_summary()

            print(f"\n{'=' * 50}")
            print(f"  {pair} Backtest Results ({years}y)")
            print(f"{'=' * 50}")
            for k, v in summary.items():
                if isinstance(v, float):
                    print(f"  {k:30s}: {v:.4f}")
                else:
                    print(f"  {k:30s}: {v}")

            # Walk-forward validation
            wfo = WalkForwardOptimizer()
            wf_result = wfo.optimize(pair, df)
            print(f"\n  Walk-Forward: robust={wf_result.get('robust')}, "
                  f"best_score={wf_result.get('best_score')}")

            # Monte Carlo
            trade_pnls = [t["pnl_usd"] for t in result.trades]
            if trade_pnls:
                mc = MonteCarloSimulator(n_simulations=1000, initial_balance=balance)
                mc_result = mc.run(trade_pnls)
                print(f"  Monte Carlo — P(profit): "
                      f"{mc_result.get('probability_of_profit', 0):.1%}, "
                      f"P(ruin): {mc_result.get('probability_of_ruin', 0):.1%}")

        except Exception as exc:
            logger.error(f"Backtest failed for {pair}: {exc}", exc_info=True)

    logger.info("Backtest complete.")


def setup_scheduler(engine, config, logger) -> BackgroundScheduler:
    """Set up APScheduler tasks: daily summary, weekly email, calendar refresh."""
    scheduler = BackgroundScheduler(timezone="America/New_York")

    # Daily P&L summary via Telegram at 6:00 PM EST
    def _daily_summary():
        try:
            from alerts.telegram_bot import TelegramBot
            bot = TelegramBot()
            db = engine.db if hasattr(engine, "db") else None
            if db:
                trades_today = db.get_trades_today()
                pnl_today = sum(t.pnl_usd or 0 for t in trades_today)
                wins = sum(1 for t in trades_today if (t.pnl_usd or 0) > 0)
                msg = (
                    f"📊 <b>Daily Summary</b>\n"
                    f"Date: {datetime.now().strftime('%Y-%m-%d')}\n"
                    f"Trades: {len(trades_today)} | Wins: {wins}\n"
                    f"P&L: {'+'if pnl_today>=0 else ''}{pnl_today:.2f} USD"
                )
                bot.send_message(msg)
        except Exception as exc:
            logger.error(f"Daily summary task failed: {exc}")

    # Weekly report via email every Sunday at 8:00 AM EST
    def _weekly_email():
        try:
            from alerts.email_report import EmailReporter
            from backtest.report_generator import ReportGenerator
            reporter = EmailReporter()
            gen = ReportGenerator()
            fig = gen.equity_curve_figure(engine.db.get_trades_last_n_days(7))
            reporter.send_weekly_report(fig)
        except Exception as exc:
            logger.error(f"Weekly email task failed: {exc}")

    # Refresh economic calendar every 6 hours
    def _refresh_calendar():
        try:
            from news.forex_factory import ForexFactoryCalendar
            ForexFactoryCalendar().get_week_events()
            logger.debug("Economic calendar refreshed.")
        except Exception as exc:
            logger.warning(f"Calendar refresh failed: {exc}")

    scheduler.add_job(_daily_summary, "cron", hour=18, minute=0, id="daily_summary")
    scheduler.add_job(_weekly_email, "cron", day_of_week="sun", hour=8, id="weekly_email")
    scheduler.add_job(_refresh_calendar, "interval", hours=6, id="calendar_refresh")

    return scheduler


def main():
    args = parse_args()

    # Resolve live / paper flag
    live_mode = args.live
    if live_mode and not confirm_live_mode():
        print("Aborting — live mode not confirmed.")
        sys.exit(0)

    paper_mode = not live_mode

    # Load config
    config_path = os.path.join(os.path.dirname(__file__), args.config)
    config = ConfigLoader(config_path).all()

    # Override config paper_trading flag
    config["paper_trading"] = paper_mode

    # Set up logging
    logger = setup_logger("fxbot", level=args.log_level.upper())

    mode_str = "PAPER TRADING" if paper_mode else "⚠️  LIVE TRADING"
    logger.info(f"FxBot starting — mode: {mode_str}")

    # Fail fast if neither OANDA nor MT5 credentials are present
    has_oanda = os.getenv("OANDA_ACCOUNT_ID") and os.getenv("OANDA_API_KEY")
    has_mt5 = os.getenv("MT5_LOGIN") and os.getenv("MT5_SERVER")
    if not has_oanda and not has_mt5:
        env_file = os.path.join(os.path.dirname(__file__), ".env")
        logger.error(
            f"No broker credentials found. Open {env_file} and set either:\n"
            "  OANDA (practice account at oanda.com):\n"
            "    OANDA_ACCOUNT_ID=101-001-39322460-002\n"
            "    OANDA_API_KEY=<your token>\n"
            "  OR MetaTrader 5 (any MT5 broker demo account):\n"
            "    MT5_LOGIN=<account number>\n"
            "    MT5_PASSWORD=<password>\n"
            "    MT5_SERVER=<broker server, e.g. Exness-MT5Trial>"
        )
        sys.exit(1)

    # Override pairs if provided on CLI
    if args.pairs:
        config.setdefault("trading", {})["pairs"] = args.pairs
        logger.info(f"Pairs overridden from CLI: {args.pairs}")

    # Backtest-only mode
    if args.backtest:
        run_backtest_mode(config, logger)
        return

    # ------------------------------------------------------------------
    # Normal operation: start the trading engine with auto-restart
    # ------------------------------------------------------------------
    restart_delay = 30  # seconds between restart attempts
    attempt = 0

    while True:
        attempt += 1
        logger.info(f"Engine start attempt #{attempt}")
        engine = None
        scheduler = None

        try:
            from core.engine import TradingEngine

            engine = TradingEngine(is_paper=paper_mode)

            # Set up scheduled tasks
            scheduler = setup_scheduler(engine, config, logger)
            scheduler.start()
            logger.info("Scheduler started (daily summary, weekly email, calendar refresh).")

            # Block in the main loop (connects broker, starts live feed, runs loop)
            engine.start()

        except KeyboardInterrupt:
            logger.info("Shutdown requested by keyboard interrupt.")
            break

        except SystemExit:
            logger.info("Clean shutdown via SystemExit.")
            break

        except Exception as exc:
            logger.critical(f"Unhandled exception in engine: {exc}", exc_info=True)
            logger.info(f"Restarting in {restart_delay}s… (attempt {attempt})")
            time.sleep(restart_delay)
            # Exponential backoff, capped at 5 minutes
            restart_delay = min(restart_delay * 2, 300)

        finally:
            if scheduler and scheduler.running:
                scheduler.shutdown(wait=False)
            if engine:
                try:
                    engine.emergency_stop()
                except Exception:
                    pass

    logger.info("FxBot shut down cleanly.")


if __name__ == "__main__":
    main()
