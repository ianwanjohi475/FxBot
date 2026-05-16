"""
Real-time price feed — OANDA streaming or MT5 polling.
Reconnects automatically with exponential backoff.
"""
import threading
import time
import os
from datetime import datetime
import pytz
from typing import Callable, Dict, List, Optional
from utils.logger import get_logger

logger = get_logger(__name__)

PAIRS = [
    "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CHF",
    "NZD_USD", "USD_CAD", "XAU_USD", "GBP_JPY", "EUR_JPY",
]


class LiveFeed:
    def __init__(self):
        self.client = None
        self.prices: Dict[str, dict] = {}
        self.callbacks: List[Callable] = []
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._reconnect_delay = 1
        self._max_reconnect_delay = 60
        self._lock = threading.Lock()
        self._last_heartbeat: Optional[datetime] = None

    def connect(self):
        try:
            from oandapyV20 import API
            api_key = os.getenv("OANDA_API_KEY")
            env = os.getenv("OANDA_ENVIRONMENT", "practice")
            self.client = API(access_token=api_key, environment=env)
            logger.info(f"[LiveFeed] Connected to OANDA ({env})")
        except Exception as e:
            logger.error(f"[LiveFeed] Connection error: {e}")
            raise

    def subscribe(self, callback: Callable):
        self.callbacks.append(callback)

    def start(self):
        self.connect()
        self.is_running = True
        self._thread = threading.Thread(target=self._stream_loop, daemon=True, name="LiveFeedThread")
        self._thread.start()
        logger.info("[LiveFeed] Streaming started")

    def stop(self):
        self.is_running = False
        logger.info("[LiveFeed] Stopped")

    def _stream_loop(self):
        while self.is_running:
            try:
                self._connect_and_stream()
                self._reconnect_delay = 1
            except Exception as e:
                logger.error(f"[LiveFeed] Stream error: {e}")
                if self.is_running:
                    logger.info(f"[LiveFeed] Reconnecting in {self._reconnect_delay}s...")
                    time.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    def _connect_and_stream(self):
        import oandapyV20.endpoints.pricing as pricing
        account_id = os.getenv("OANDA_ACCOUNT_ID")
        params = {"instruments": ",".join(PAIRS)}
        r = pricing.PricingStream(accountID=account_id, params=params)
        for tick in self.client.request(r):
            if not self.is_running:
                break
            self._process_tick(tick)

    def _process_tick(self, tick: dict):
        if tick.get("type") == "HEARTBEAT":
            self._last_heartbeat = datetime.now(tz=pytz.utc)
            return
        if tick.get("type") != "PRICE":
            return

        try:
            pair = tick["instrument"]
            bid = float(tick["bids"][0]["price"])
            ask = float(tick["asks"][0]["price"])
            spread = ask - bid
            ts = datetime.fromisoformat(tick["time"].replace("Z", "+00:00"))

            price_data = {
                "bid": bid,
                "ask": ask,
                "mid": round((bid + ask) / 2, 5),
                "spread": spread,
                "spread_pips": self._to_pips(spread, pair),
                "time": ts,
            }
            with self._lock:
                self.prices[pair] = price_data

            for cb in self.callbacks:
                try:
                    cb(pair, price_data)
                except Exception as e:
                    logger.error(f"[LiveFeed] Callback error: {e}")
        except Exception as e:
            logger.debug(f"[LiveFeed] Tick parse error: {e}")

    def _to_pips(self, spread: float, pair: str) -> float:
        if "JPY" in pair:
            return round(spread * 100, 3)
        if "XAU" in pair:
            return round(spread * 10, 3)
        return round(spread * 10000, 3)

    def get_price(self, pair: str) -> dict:
        with self._lock:
            return dict(self.prices.get(pair, {}))

    def get_all_prices(self) -> dict:
        with self._lock:
            return dict(self.prices)

    def get_spread_pips(self, pair: str) -> float:
        price = self.get_price(pair)
        return price.get("spread_pips", 999.0)

    def is_healthy(self) -> bool:
        if not self.is_running:
            return False
        if self._last_heartbeat is None:
            return len(self.prices) > 0
        elapsed = (datetime.now(tz=pytz.utc) - self._last_heartbeat).total_seconds()
        return elapsed < 60


class MT5LiveFeed:
    """Polling-based live price feed via MetaTrader 5 terminal."""

    OANDA_TO_MT5: Dict[str, str] = {
        "EUR_USD": "EURUSD", "GBP_USD": "GBPUSD", "USD_JPY": "USDJPY",
        "AUD_USD": "AUDUSD", "USD_CHF": "USDCHF", "NZD_USD": "NZDUSD",
        "USD_CAD": "USDCAD", "XAU_USD": "XAUUSD", "GBP_JPY": "GBPJPY",
        "EUR_JPY": "EURJPY",
    }
    POLL_INTERVAL = 1.0  # seconds between price polls

    def __init__(self, pairs: List[str] = None):
        self._pairs = pairs or list(self.OANDA_TO_MT5.keys())
        self.prices: Dict[str, dict] = {}
        self.callbacks: List[Callable] = []
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._mt5 = None

    def connect(self) -> None:
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
            logger.info("[MT5LiveFeed] Ready — using MT5 terminal for prices")
        except ImportError:
            raise RuntimeError("MetaTrader5 package not installed. Run: pip install MetaTrader5")

    def subscribe(self, callback: Callable) -> None:
        self.callbacks.append(callback)

    def start(self) -> None:
        self.connect()
        self.is_running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="MT5FeedThread")
        self._thread.start()
        logger.info("[MT5LiveFeed] Polling started")

    def stop(self) -> None:
        self.is_running = False

    def _to_pips(self, spread: float, pair: str) -> float:
        if "JPY" in pair:
            return round(spread * 100, 3)
        if "XAU" in pair:
            return round(spread * 10, 3)
        return round(spread * 10000, 3)

    def _poll_loop(self) -> None:
        mt5 = self._mt5
        while self.is_running:
            for pair in self._pairs:
                symbol = self.OANDA_TO_MT5.get(pair, pair.replace("_", ""))
                try:
                    tick = mt5.symbol_info_tick(symbol)
                    if tick is None:
                        continue
                    spread = tick.ask - tick.bid
                    price_data = {
                        "bid": tick.bid,
                        "ask": tick.ask,
                        "mid": round((tick.bid + tick.ask) / 2, 5),
                        "spread": spread,
                        "spread_pips": self._to_pips(spread, pair),
                        "time": datetime.utcnow(),
                    }
                    with self._lock:
                        self.prices[pair] = price_data
                    for cb in self.callbacks:
                        try:
                            cb(pair, price_data)
                        except Exception as e:
                            logger.error(f"[MT5LiveFeed] Callback error: {e}")
                except Exception as e:
                    logger.debug(f"[MT5LiveFeed] Tick error for {symbol}: {e}")
            time.sleep(self.POLL_INTERVAL)

    def get_price(self, pair: str) -> dict:
        with self._lock:
            return dict(self.prices.get(pair, {}))

    def get_all_prices(self) -> dict:
        with self._lock:
            return dict(self.prices)

    def get_spread_pips(self, pair: str) -> float:
        return self.get_price(pair).get("spread_pips", 999.0)

    def is_healthy(self) -> bool:
        return self.is_running and len(self.prices) > 0
