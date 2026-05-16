"""
OANDA broker connector. Handles account info, pricing, and order submission.
MetaTrader 5 support is available when MT5 library is installed.
"""
import os
from typing import Optional, Dict, List
from utils.logger import get_logger

logger = get_logger(__name__)


class OANDABroker:
    def __init__(self):
        self.client = None
        self.account_id = os.getenv("OANDA_ACCOUNT_ID")
        self.api_key = os.getenv("OANDA_API_KEY")
        self.environment = os.getenv("OANDA_ENVIRONMENT", "practice")
        self.is_paper = os.getenv("PAPER_TRADING", "true").lower() == "true"

    def connect(self):
        from oandapyV20 import API
        self.client = API(access_token=self.api_key, environment=self.environment)
        logger.info(f"[OANDABroker] Connected (env={self.environment}, paper={self.is_paper})")

    def get_account(self) -> dict:
        import oandapyV20.endpoints.accounts as accounts
        r = accounts.AccountDetails(accountID=self.account_id)
        self.client.request(r)
        acct = r.response.get("account", {})
        return {
            "balance": float(acct.get("balance", 0)),
            "equity": float(acct.get("NAV", 0)),
            "margin_used": float(acct.get("marginUsed", 0)),
            "margin_available": float(acct.get("marginAvailable", 0)),
            "unrealized_pnl": float(acct.get("unrealizedPL", 0)),
            "currency": acct.get("currency", "USD"),
            "open_trade_count": int(acct.get("openTradeCount", 0)),
        }

    def get_price(self, pair: str) -> dict:
        import oandapyV20.endpoints.pricing as pricing
        r = pricing.PricingInfo(accountID=self.account_id, params={"instruments": pair})
        self.client.request(r)
        prices = r.response.get("prices", [{}])
        if not prices:
            return {}
        p = prices[0]
        bid = float(p["bids"][0]["price"])
        ask = float(p["asks"][0]["price"])
        return {"bid": bid, "ask": ask, "mid": (bid + ask) / 2, "spread": ask - bid}

    def get_open_trades(self) -> List[dict]:
        import oandapyV20.endpoints.trades as trades
        r = trades.TradesList(accountID=self.account_id, params={"state": "OPEN"})
        self.client.request(r)
        return r.response.get("trades", [])

    def get_open_positions(self) -> List[dict]:
        import oandapyV20.endpoints.positions as positions
        r = positions.PositionList(accountID=self.account_id)
        self.client.request(r)
        return r.response.get("positions", [])

    def place_market_order(
        self,
        pair: str,
        units: int,
        sl_price: float = None,
        tp_price: float = None,
        client_ext: str = None,
    ) -> dict:
        """Place a market order. units > 0 = BUY, units < 0 = SELL."""
        import oandapyV20.endpoints.orders as orders

        order_body: dict = {
            "order": {
                "type": "MARKET",
                "instrument": pair,
                "units": str(units),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
            }
        }
        if sl_price:
            order_body["order"]["stopLossOnFill"] = {"price": str(round(sl_price, 5))}
        if tp_price:
            order_body["order"]["takeProfitOnFill"] = {"price": str(round(tp_price, 5))}
        if client_ext:
            order_body["order"]["clientExtensions"] = {"comment": client_ext[:128]}

        r = orders.OrderCreate(accountID=self.account_id, data=order_body)
        self.client.request(r)
        return r.response

    def modify_trade(self, trade_id: str, sl_price: float = None, tp_price: float = None) -> dict:
        import oandapyV20.endpoints.trades as trades
        data: dict = {}
        if sl_price is not None:
            data["stopLoss"] = {"price": str(round(sl_price, 5))}
        if tp_price is not None:
            data["takeProfit"] = {"price": str(round(tp_price, 5))}
        r = trades.TradeCRCDO(accountID=self.account_id, tradeID=trade_id, data=data)
        self.client.request(r)
        return r.response

    def close_trade(self, trade_id: str, units: str = "ALL") -> dict:
        import oandapyV20.endpoints.trades as trades
        data = {"units": units}
        r = trades.TradeClose(accountID=self.account_id, tradeID=trade_id, data=data)
        self.client.request(r)
        return r.response

    def close_all_trades(self) -> list:
        results = []
        for trade in self.get_open_trades():
            try:
                result = self.close_trade(trade["id"])
                results.append(result)
                logger.info(f"[OANDABroker] Closed trade {trade['id']}")
            except Exception as e:
                logger.error(f"[OANDABroker] Failed to close trade {trade['id']}: {e}")
        return results


class MT5Broker:
    """MetaTrader 5 broker connector — full implementation."""

    OANDA_TO_MT5: dict = {
        "EUR_USD": "EURUSD", "GBP_USD": "GBPUSD", "USD_JPY": "USDJPY",
        "AUD_USD": "AUDUSD", "USD_CHF": "USDCHF", "NZD_USD": "NZDUSD",
        "USD_CAD": "USDCAD", "XAU_USD": "XAUUSD", "GBP_JPY": "GBPJPY",
        "EUR_JPY": "EURJPY",
    }

    def __init__(self):
        self._mt5 = None
        self.connected = False

    def _sym(self, pair: str) -> str:
        return self.OANDA_TO_MT5.get(pair, pair.replace("_", ""))

    def connect(self) -> None:
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
            login = int(os.getenv("MT5_LOGIN", "0"))
            password = os.getenv("MT5_PASSWORD", "")
            server = os.getenv("MT5_SERVER", "")
            if not mt5.initialize(login=login, password=password, server=server):
                raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
            info = mt5.account_info()
            self.connected = True
            logger.info(
                f"[MT5Broker] Connected — {info.name} | "
                f"balance={info.balance:.2f} {info.currency} | server={server}"
            )
        except ImportError:
            raise RuntimeError(
                "MetaTrader5 package not installed.\n"
                "  Run: pip install MetaTrader5\n"
                "  Note: MT5 Python API only works on Windows."
            )

    def get_account(self) -> dict:
        info = self._mt5.account_info()
        if info is None:
            return {}
        return {
            "balance": info.balance,
            "equity": info.equity,
            "margin_used": info.margin,
            "margin_available": info.margin_free,
            "unrealized_pnl": info.equity - info.balance,
            "currency": info.currency,
            "open_trade_count": len(self._mt5.positions_get() or []),
        }

    def get_price(self, pair: str) -> dict:
        tick = self._mt5.symbol_info_tick(self._sym(pair))
        if tick is None:
            return {}
        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "mid": (tick.bid + tick.ask) / 2,
            "spread": tick.ask - tick.bid,
        }

    def get_open_trades(self) -> List[dict]:
        positions = self._mt5.positions_get() or []
        return [
            {
                "id": str(p.ticket),
                "instrument": p.symbol,
                "currentUnits": str(int(p.volume * 100000) * (1 if p.type == 0 else -1)),
                "unrealizedPL": str(p.profit),
            }
            for p in positions
        ]

    def get_open_positions(self) -> List[dict]:
        return self.get_open_trades()

    def place_market_order(
        self,
        pair: str,
        units: int,
        sl_price: float = None,
        tp_price: float = None,
        client_ext: str = None,
    ) -> dict:
        mt5 = self._mt5
        symbol = self._sym(pair)
        mt5.symbol_select(symbol, True)
        is_buy = units > 0
        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask if is_buy else tick.bid
        volume = max(0.01, round(abs(units) / 100000, 2))
        request: dict = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": (client_ext or "FxBot")[:32],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if sl_price:
            request["sl"] = round(sl_price, 5)
        if tp_price:
            request["tp"] = round(tp_price, 5)
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            comment = result.comment if result else str(mt5.last_error())
            raise RuntimeError(f"MT5 order failed: {comment}")
        return {"orderFillTransaction": {"id": str(result.order), "price": str(price)}}

    def modify_trade(self, trade_id: str, sl_price: float = None, tp_price: float = None) -> dict:
        mt5 = self._mt5
        positions = mt5.positions_get(ticket=int(trade_id))
        if not positions:
            return {}
        p = positions[0]
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": p.symbol,
            "position": p.ticket,
            "sl": round(sl_price, 5) if sl_price is not None else p.sl,
            "tp": round(tp_price, 5) if tp_price is not None else p.tp,
        }
        result = mt5.order_send(request)
        return {"retcode": result.retcode if result else -1}

    def close_trade(self, trade_id: str, units: str = "ALL") -> dict:
        mt5 = self._mt5
        positions = mt5.positions_get(ticket=int(trade_id))
        if not positions:
            return {}
        p = positions[0]
        is_sell_to_close = p.type == 0  # BUY position → close by SELL
        tick = mt5.symbol_info_tick(p.symbol)
        price = tick.bid if is_sell_to_close else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": mt5.ORDER_TYPE_SELL if is_sell_to_close else mt5.ORDER_TYPE_BUY,
            "position": p.ticket,
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": "FxBot close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        return {"retcode": result.retcode if result else -1}

    def close_all_trades(self) -> list:
        positions = self._mt5.positions_get() or []
        results = []
        for p in positions:
            try:
                results.append(self.close_trade(str(p.ticket)))
                logger.info(f"[MT5Broker] Closed position {p.ticket}")
            except Exception as e:
                logger.error(f"[MT5Broker] Failed to close position {p.ticket}: {e}")
        return results

    def disconnect(self):
        try:
            if self._mt5:
                self._mt5.shutdown()
                self.connected = False
        except Exception:
            pass
