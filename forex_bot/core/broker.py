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
    """MetaTrader 5 broker connector (optional)."""

    def __init__(self):
        self.connected = False

    def connect(self) -> bool:
        try:
            import MetaTrader5 as mt5
            login = int(os.getenv("MT5_LOGIN", "0"))
            password = os.getenv("MT5_PASSWORD", "")
            server = os.getenv("MT5_SERVER", "")
            if not mt5.initialize(login=login, password=password, server=server):
                logger.error(f"[MT5] Init failed: {mt5.last_error()}")
                return False
            self.connected = True
            logger.info("[MT5] Connected")
            return True
        except ImportError:
            logger.warning("[MT5] MetaTrader5 library not installed")
            return False
        except Exception as e:
            logger.error(f"[MT5] Connection error: {e}")
            return False

    def get_account(self) -> dict:
        import MetaTrader5 as mt5
        info = mt5.account_info()
        if info is None:
            return {}
        return {"balance": info.balance, "equity": info.equity, "margin": info.margin}

    def disconnect(self):
        try:
            import MetaTrader5 as mt5
            mt5.shutdown()
        except Exception:
            pass
