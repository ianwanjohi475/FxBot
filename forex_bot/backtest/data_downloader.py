"""Download and cache historical data for backtesting."""
import os
import pandas as pd
from datetime import datetime, timedelta
import pytz
from typing import Dict
from data.historical import HistoricalData
from data.data_cleaner import DataCleaner
from utils.logger import get_logger

logger = get_logger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
PAIRS = [
    "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CHF",
    "NZD_USD", "USD_CAD", "XAU_USD", "GBP_JPY", "EUR_JPY",
]


class DataDownloader:
    def __init__(self):
        self.historical = HistoricalData()
        os.makedirs(CACHE_DIR, exist_ok=True)

    def download_pair(
        self,
        pair: str,
        granularity: str = "D1",
        years: int = 10,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        cache_path = os.path.join(CACHE_DIR, f"{pair}_{granularity}_{years}y.parquet")

        if use_cache and os.path.exists(cache_path):
            age_days = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_path))).days
            if age_days < 1:
                logger.info(f"[DataDownloader] Loading cached {pair} {granularity}")
                return pd.read_parquet(cache_path)

        logger.info(f"[DataDownloader] Downloading {pair} {granularity} ({years}y)")
        df = self.historical.get_long_history(pair, granularity, years)
        df = DataCleaner.clean_ohlcv(df)

        if not df.empty:
            df.to_parquet(cache_path)
            logger.info(f"[DataDownloader] Saved {len(df)} rows for {pair}")
        return df

    def download_all(
        self,
        granularity: str = "H1",
        years: int = 10,
        use_cache: bool = True,
    ) -> Dict[str, pd.DataFrame]:
        data = {}
        for pair in PAIRS:
            try:
                df = self.download_pair(pair, granularity, years, use_cache)
                if not df.empty:
                    data[pair] = df
                    logger.info(f"[DataDownloader] {pair}: {len(df)} bars ({df.index[0]} to {df.index[-1]})")
            except Exception as e:
                logger.error(f"[DataDownloader] Failed {pair}: {e}")
        return data

    def get_cached_pairs(self) -> list:
        return [
            f.replace(".parquet", "")
            for f in os.listdir(CACHE_DIR)
            if f.endswith(".parquet")
        ]
