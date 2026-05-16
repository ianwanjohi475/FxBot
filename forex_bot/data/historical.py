"""Historical OHLCV data fetcher — OANDA primary, yfinance fallback."""
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from typing import Optional, Dict
from utils.logger import get_logger
from utils.timeframe import tf_to_oanda_granularity

logger = get_logger(__name__)

OANDA_TO_YFINANCE: Dict[str, str] = {
    "EUR_USD": "EURUSD=X", "GBP_USD": "GBPUSD=X", "USD_JPY": "USDJPY=X",
    "AUD_USD": "AUDUSD=X", "USD_CHF": "USDCHF=X", "NZD_USD": "NZDUSD=X",
    "USD_CAD": "USDCAD=X", "XAU_USD": "GC=F",
    "GBP_JPY": "GBPJPY=X", "EUR_JPY": "EURJPY=X",
}

YF_TF_MAP = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1": "1d", "W1": "1wk",
}

MAX_OANDA_CANDLES = 5000


class HistoricalData:
    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from oandapyV20 import API
            api_key = os.getenv("OANDA_API_KEY")
            env = os.getenv("OANDA_ENVIRONMENT", "practice")
            self._client = API(access_token=api_key, environment=env)
        return self._client

    def get_candles(
        self,
        pair: str,
        granularity: str,
        count: int = 500,
        start: datetime = None,
        end: datetime = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV from OANDA."""
        try:
            import oandapyV20.endpoints.instruments as instruments
            client = self._get_client()
            account_id = os.getenv("OANDA_ACCOUNT_ID")
            params: dict = {"granularity": granularity, "price": "M"}
            if start and end:
                params["from"] = start.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
                params["to"] = end.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
            else:
                params["count"] = min(count, MAX_OANDA_CANDLES)

            r = instruments.InstrumentsCandles(instrument=pair, params=params)
            client.request(r)
            candles = r.response.get("candles", [])
            return self._parse_oanda_candles(candles)
        except Exception as e:
            logger.warning(f"[HistoricalData] OANDA fetch failed for {pair}: {e} — trying yfinance")
            return self.get_candles_yfinance(pair, granularity, count=count)

    def _parse_oanda_candles(self, candles: list) -> pd.DataFrame:
        rows = []
        for c in candles:
            if not c.get("complete", True):
                continue
            mid = c.get("mid", {})
            rows.append({
                "time": pd.to_datetime(c["time"]),
                "open": float(mid.get("o", 0)),
                "high": float(mid.get("h", 0)),
                "low": float(mid.get("l", 0)),
                "close": float(mid.get("c", 0)),
                "volume": float(c.get("volume", 0)),
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.set_index("time").sort_index()
        return df

    def get_candles_yfinance(
        self,
        pair: str,
        granularity: str = "H1",
        count: int = 500,
        start: str = None,
        end: str = None,
    ) -> pd.DataFrame:
        """Fetch from yfinance as fallback."""
        try:
            import yfinance as yf
            symbol = OANDA_TO_YFINANCE.get(pair, pair)
            interval = YF_TF_MAP.get(granularity, "1h")

            if start and end:
                data = yf.download(symbol, start=start, end=end, interval=interval,
                                   auto_adjust=True, progress=False)
            else:
                period = "60d" if granularity in ("M1", "M5", "M15") else "2y"
                data = yf.download(symbol, period=period, interval=interval,
                                   auto_adjust=True, progress=False)

            if data.empty:
                return pd.DataFrame()

            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [c[0].lower() for c in data.columns]
            else:
                data.columns = [c.lower() for c in data.columns]
            data.index.name = "time"
            for col in ["open", "high", "low", "close"]:
                if col not in data.columns and "adj close" in data.columns:
                    data[col] = data["adj close"]
            if "volume" not in data.columns:
                data["volume"] = 0.0
            return data[["open", "high", "low", "close", "volume"]].tail(count)
        except Exception as e:
            logger.error(f"[HistoricalData] yfinance error for {pair}: {e}")
            return pd.DataFrame()

    def get_multi_timeframe(
        self, pair: str, timeframes: list, count: int = 200
    ) -> dict:
        result = {}
        for tf in timeframes:
            gran = tf_to_oanda_granularity(tf)
            result[tf] = self.get_candles(pair, gran, count)
        return result

    def get_long_history(self, pair: str, granularity: str = "D1", years: int = 10) -> pd.DataFrame:
        end = datetime.now(tz=pytz.utc)
        start = end - timedelta(days=years * 365)
        yf_sym = OANDA_TO_YFINANCE.get(pair, pair)
        try:
            import yfinance as yf
            interval = YF_TF_MAP.get(granularity, "1d")
            data = yf.download(
                yf_sym,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval=interval,
                auto_adjust=True,
                progress=False,
            )
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [c[0].lower() for c in data.columns]
            else:
                data.columns = [c.lower() for c in data.columns]
            if "volume" not in data.columns:
                data["volume"] = 0.0
            return data[["open", "high", "low", "close", "volume"]]
        except Exception as e:
            logger.error(f"[HistoricalData] Long history error for {pair}: {e}")
            return pd.DataFrame()

    def update_candle(self, pair: str, granularity: str, df: pd.DataFrame) -> pd.DataFrame:
        """Append latest candle to existing dataframe."""
        new_candle = self.get_candles(pair, granularity, count=1)
        if new_candle.empty:
            return df
        return pd.concat([df, new_candle]).loc[~df.index.duplicated(keep="last")]
