"""
Telegram bot for trade alerts and bot control.
Supports /stop emergency command.
"""
import os
import threading
import asyncio
from datetime import datetime
from typing import Optional
import pytz
from utils.logger import get_logger

logger = get_logger(__name__)


class TelegramBot:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.token and self.chat_id)
        self._engine_ref = None  # Set by engine for /stop command
        if not self.enabled:
            logger.warning("[Telegram] Bot token or chat ID not set — alerts disabled")

    def set_engine(self, engine):
        self._engine_ref = engine

    def send_message(self, text: str) -> bool:
        if not self.enabled:
            logger.info(f"[Telegram][DISABLED] {text}")
            return False
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"[Telegram] Send error: {e}")
            return False

    def notify_trade_open(self, signal, trade_id: str, lot_size: float, risk_usd: float):
        direction_emoji = "📈" if signal.direction == "BUY" else "📉"
        msg = (
            f"{direction_emoji} <b>TRADE OPENED</b>\n"
            f"ID: <code>{trade_id}</code>\n"
            f"Pair: <b>{signal.pair}</b> | {signal.direction}\n"
            f"Strategy: {signal.strategy_name}\n"
            f"Entry: {signal.entry_price:.5f}\n"
            f"SL: {signal.sl_price:.5f} | TP1: {signal.tp1_price:.5f}\n"
            f"Lot: {lot_size:.3f} | Risk: ${risk_usd:.2f}\n"
            f"Score: {signal.confluence_score:.1f}/100\n"
            f"Time: {datetime.now(tz=pytz.utc).strftime('%H:%M UTC')}"
        )
        self.send_message(msg)

    def notify_trade_close(self, trade_id: str, exit_price: float, reason: str,
                            pnl_usd: float = None, pips: float = None):
        if pnl_usd is not None:
            emoji = "✅" if pnl_usd >= 0 else "❌"
            pnl_str = f"${pnl_usd:+.2f}"
            pips_str = f" ({pips:+.1f} pips)" if pips is not None else ""
        else:
            emoji = "🔔"
            pnl_str = "N/A"
            pips_str = ""
        msg = (
            f"{emoji} <b>TRADE CLOSED</b>\n"
            f"ID: <code>{trade_id}</code>\n"
            f"Exit: {exit_price:.5f} | Reason: {reason}\n"
            f"P&L: <b>{pnl_str}{pips_str}</b>\n"
            f"Time: {datetime.now(tz=pytz.utc).strftime('%H:%M UTC')}"
        )
        self.send_message(msg)

    def notify_tp_hit(self, trade_id: str, tp_level: str, price: float):
        msg = (
            f"🎯 <b>{tp_level} HIT</b>\n"
            f"ID: <code>{trade_id}</code>\n"
            f"Price: {price:.5f}"
        )
        self.send_message(msg)

    def notify_sl_hit(self, trade_id: str, price: float):
        msg = (
            f"🛑 <b>STOP LOSS HIT</b>\n"
            f"ID: <code>{trade_id}</code>\n"
            f"Price: {price:.5f}"
        )
        self.send_message(msg)

    def notify_danger_zone(self, zone: str, pair: str, detail: str = ""):
        msg = f"⚠️ <b>DANGER ZONE</b>: {zone}\nPair: {pair}\n{detail}"
        self.send_message(msg)

    def notify_news_warning(self, event_name: str, currency: str, minutes_until: int):
        msg = (
            f"📰 <b>NEWS ALERT</b> in {minutes_until} min\n"
            f"Event: {event_name}\nCurrency: {currency}"
        )
        self.send_message(msg)

    def send_daily_summary(self, stats: dict):
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        pnl = stats.get("pnl_usd", 0)
        emoji = "📊✅" if pnl >= 0 else "📊❌"
        msg = (
            f"{emoji} <b>DAILY SUMMARY</b>\n"
            f"Date: {datetime.now(tz=pytz.utc).strftime('%Y-%m-%d')}\n"
            f"Trades: {wins + losses} | W: {wins} L: {losses}\n"
            f"P&L: <b>${pnl:+.2f}</b>\n"
            f"Win Rate: {wins/(wins+losses)*100:.1f}%" if (wins + losses) > 0 else "Win Rate: N/A"
        )
        self.send_message(msg)

    def send_weekly_summary(self, stats: dict):
        msg = (
            f"📅 <b>WEEKLY SUMMARY</b>\n"
            f"Trades: {stats.get('total_trades', 0)}\n"
            f"Win Rate: {stats.get('win_rate', 0)*100:.1f}%\n"
            f"P&L: <b>${stats.get('pnl_usd', 0):+.2f}</b>\n"
            f"Profit Factor: {stats.get('profit_factor', 0):.2f}"
        )
        self.send_message(msg)

    def start_listener(self):
        """Start polling for /stop and other commands."""
        if not self.enabled:
            return
        thread = threading.Thread(target=self._poll_loop, daemon=True, name="TelegramPoll")
        thread.start()

    def _poll_loop(self):
        import requests
        offset = 0
        while True:
            try:
                url = f"https://api.telegram.org/bot{self.token}/getUpdates"
                resp = requests.get(url, params={"offset": offset, "timeout": 30}, timeout=35)
                updates = resp.json().get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    msg = update.get("message", {}).get("text", "")
                    chat = update.get("message", {}).get("chat", {}).get("id")
                    if str(chat) == str(self.chat_id):
                        self._handle_command(msg)
            except Exception as e:
                logger.debug(f"[Telegram] Poll error: {e}")
                import time; time.sleep(5)

    def _handle_command(self, text: str):
        if text.strip().lower() in ("/stop", "/stop@your_bot"):
            logger.warning("[Telegram] /stop command received!")
            self.send_message("🚨 EMERGENCY STOP command received — closing all trades...")
            if self._engine_ref:
                self._engine_ref.emergency_stop()
        elif text.strip().lower() == "/status":
            self.send_message(f"🟢 FxBot is running\n{datetime.now(tz=pytz.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        elif text.strip().lower() == "/help":
            self.send_message(
                "📋 <b>FxBot Commands</b>\n"
                "/stop — Emergency stop (close all trades)\n"
                "/status — Check bot status\n"
                "/help — Show this message"
            )
