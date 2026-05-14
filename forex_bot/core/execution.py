"""
Order execution — open, modify, partial close, full close.
Handles paper trading mode and live mode.
"""
import uuid
from datetime import datetime
import pytz
from typing import Optional
from strategies import TradeSignal
from .broker import OANDABroker
from database.db import DatabaseManager
from utils.logger import get_logger
from utils.helpers import price_to_pips

logger = get_logger(__name__)

LOT_TO_UNITS = 100_000


class ExecutionEngine:
    def __init__(self, broker: OANDABroker, db: DatabaseManager, is_paper: bool = True):
        self.broker = broker
        self.db = db
        self.is_paper = is_paper
        self._paper_trades: dict = {}

    def open_trade(
        self,
        signal: TradeSignal,
        lot_size: float,
        account_balance: float,
        risk_amount_usd: float,
        session: str = "",
        news_events: list = None,
    ) -> Optional[str]:
        trade_id = str(uuid.uuid4())[:8].upper()
        entry_time = datetime.now(tz=pytz.utc)
        units = int(lot_size * LOT_TO_UNITS)
        if signal.direction == "SELL":
            units = -units

        oanda_order_id = None
        if not self.is_paper:
            try:
                resp = self.broker.place_market_order(
                    pair=signal.pair,
                    units=units,
                    sl_price=signal.sl_price,
                    tp_price=signal.tp1_price,
                    client_ext=trade_id,
                )
                fill = resp.get("orderFillTransaction", {})
                oanda_order_id = fill.get("id")
                entry_price = float(fill.get("price", signal.entry_price))
                logger.info(f"[Execution] LIVE trade opened: {trade_id} OANDA={oanda_order_id}")
            except Exception as e:
                logger.error(f"[Execution] LIVE order failed: {e}")
                return None
        else:
            entry_price = signal.entry_price
            logger.info(f"[Execution] PAPER trade opened: {trade_id} {signal.pair} {signal.direction}")

        pip_dist = price_to_pips(abs(entry_price - signal.sl_price), signal.pair)
        tp1_pip_dist = price_to_pips(abs(signal.tp1_price - entry_price), signal.pair)
        tp2_pip_dist = price_to_pips(abs(signal.tp2_price - entry_price), signal.pair)
        tp3_pip_dist = price_to_pips(abs(signal.tp3_price - entry_price), signal.pair)

        import json
        trade_data = {
            "trade_id": trade_id,
            "pair": signal.pair,
            "timeframe": signal.timeframe,
            "entry_time": entry_time,
            "entry_price": entry_price,
            "direction": signal.direction,
            "strategy_name": signal.strategy_name,
            "pattern_detected": signal.pattern_detected,
            "smc_concept": signal.smc_concept,
            "confluence_score": signal.confluence_score,
            "confidence_pct": signal.confidence_pct,
            "indicators_json": json.dumps(signal.indicators),
            "sl_price": signal.sl_price,
            "sl_pips": pip_dist,
            "tp1_price": signal.tp1_price,
            "tp2_price": signal.tp2_price,
            "tp3_price": signal.tp3_price,
            "risk_amount_usd": risk_amount_usd,
            "risk_pct": risk_amount_usd / account_balance if account_balance else 0,
            "reward_tp1_usd": risk_amount_usd * (tp1_pip_dist / pip_dist) if pip_dist else 0,
            "reward_tp2_usd": risk_amount_usd * (tp2_pip_dist / pip_dist) if pip_dist else 0,
            "reward_tp3_usd": risk_amount_usd * (tp3_pip_dist / pip_dist) if pip_dist else 0,
            "session": session,
            "news_events_json": json.dumps(news_events or []),
            "balance_before": account_balance,
            "is_paper": self.is_paper,
            "oanda_order_id": oanda_order_id,
            "status": "OPEN",
        }

        try:
            self.db.save_trade(trade_data)
        except Exception as e:
            logger.error(f"[Execution] DB save error: {e}")

        if self.is_paper:
            self._paper_trades[trade_id] = {**trade_data, "lot_size": lot_size}

        return trade_id

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        account_balance: float,
        units: str = "ALL",
    ) -> dict:
        trade = self.db.get_trade_by_id(trade_id)
        if trade is None:
            logger.warning(f"[Execution] Trade {trade_id} not found in DB")
            return {}

        if not self.is_paper and trade.oanda_order_id:
            try:
                self.broker.close_trade(trade.oanda_order_id, units)
            except Exception as e:
                logger.error(f"[Execution] LIVE close failed: {e}")

        direction = trade.direction
        entry = trade.entry_price
        pip_diff = price_to_pips(abs(exit_price - entry), trade.pair)
        if direction == "BUY":
            pnl_pips = price_to_pips(exit_price - entry, trade.pair)
        else:
            pnl_pips = price_to_pips(entry - exit_price, trade.pair)

        risk = trade.risk_amount_usd or 0
        sl_dist = trade.sl_pips or 1
        pnl_usd = pnl_pips / sl_dist * risk if sl_dist else 0
        actual_rr = pnl_pips / sl_dist if sl_dist else 0

        result = "WIN" if pnl_usd > 0 else ("LOSS" if pnl_usd < 0 else "BREAKEVEN")
        updates = {
            "exit_time": datetime.now(tz=pytz.utc),
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "result": result,
            "actual_rr": round(actual_rr, 2),
            "pips_result": round(pnl_pips, 1),
            "pnl_usd": round(pnl_usd, 2),
            "balance_after": account_balance + pnl_usd,
            "status": "CLOSED",
        }
        try:
            self.db.update_trade(trade_id, updates)
        except Exception as e:
            logger.error(f"[Execution] DB update error: {e}")

        if trade_id in self._paper_trades:
            del self._paper_trades[trade_id]

        logger.info(
            f"[Execution] Trade {trade_id} closed | {result} | "
            f"PnL={pnl_usd:+.2f} pips={pnl_pips:+.1f} reason={exit_reason}"
        )
        return updates

    def modify_sl(self, trade_id: str, new_sl: float) -> bool:
        trade = self.db.get_trade_by_id(trade_id)
        if not trade:
            return False
        if not self.is_paper and trade.oanda_order_id:
            try:
                self.broker.modify_trade(trade.oanda_order_id, sl_price=new_sl)
            except Exception as e:
                logger.error(f"[Execution] Modify SL failed: {e}")
                return False
        self.db.update_trade(trade_id, {"sl_price": new_sl})
        logger.debug(f"[Execution] SL updated for {trade_id}: {new_sl}")
        return True

    def get_paper_pnl(self, trade_id: str, current_price: float) -> float:
        pt = self._paper_trades.get(trade_id)
        if not pt:
            return 0.0
        entry = pt["entry_price"]
        direction = pt["direction"]
        lot = pt.get("lot_size", 0.01)
        pip_val = lot * 10
        pips = price_to_pips(
            current_price - entry if direction == "BUY" else entry - current_price,
            pt["pair"]
        )
        return round(pips * pip_val, 2)
