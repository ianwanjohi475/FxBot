"""Data cleaning and validation for OHLCV data."""
import pandas as pd
import numpy as np
from utils.logger import get_logger

logger = get_logger(__name__)

COLUMN_MAP = {
    "Open": "open", "High": "high", "Low": "low", "Close": "close",
    "Volume": "volume", "Time": "time", "timestamp": "time",
    "Date": "time", "Datetime": "time", "Adj Close": "close",
}


class DataCleaner:

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        df = df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns})
        return df

    @staticmethod
    def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        df = DataCleaner.normalize_columns(df)
        original_len = len(df)

        # Remove duplicate timestamps
        df = df[~df.index.duplicated(keep="last")]

        # Remove invalid OHLC relationships
        df = df[df["high"] >= df["low"]]
        df = df[df["high"] >= df["open"]]
        df = df[df["high"] >= df["close"]]
        df = df[df["low"] <= df["open"]]
        df = df[df["low"] <= df["close"]]

        # Remove zero prices
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df = df[df[col] > 0]

        # Volume non-negative
        if "volume" in df.columns:
            df["volume"] = df["volume"].clip(lower=0)

        df = df.sort_index()
        removed = original_len - len(df)
        if removed > 0:
            logger.debug(f"[DataCleaner] Removed {removed} invalid rows")
        return df

    @staticmethod
    def fill_gaps(df: pd.DataFrame, max_gap: int = 5) -> pd.DataFrame:
        """Forward-fill small gaps (weekends excluded)."""
        if df.empty:
            return df
        df = df.ffill(limit=max_gap)
        return df

    @staticmethod
    def validate_data(df: pd.DataFrame) -> tuple:
        """Returns (is_valid: bool, issues: list)."""
        issues = []
        if df is None or df.empty:
            return False, ["DataFrame is empty"]
        for col in ["open", "high", "low", "close"]:
            if col not in df.columns:
                issues.append(f"Missing column: {col}")
        if df[["open", "high", "low", "close"]].isnull().any().any():
            null_count = df[["open", "high", "low", "close"]].isnull().sum().sum()
            issues.append(f"{null_count} NaN values in OHLC columns")
        if (df.get("high", df.get("close", pd.Series())) < df.get("low", pd.Series())).any():
            issues.append("Found rows where high < low")
        return len(issues) == 0, issues

    @staticmethod
    def add_returns(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))
        df["pct_change"] = df["close"].pct_change()
        return df

    @staticmethod
    def resample_to_higher_tf(df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
        from utils.timeframe import tf_to_pandas_freq
        freq = tf_to_pandas_freq(target_tf)
        resampled = df.resample(freq).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()
        return resampled
