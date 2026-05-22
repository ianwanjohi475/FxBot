"""
Confluence scoring engine — scores every signal 0–100.

Scoring components:
  Trend alignment (3 timeframes)  → max 20
  Strong S/R level                → max 15
  Pattern confirmed               → max 15
  Momentum (RSI + MACD)          → max 15
  SMC structure (OB or FVG)      → max 15
  Volume confirmation             → max 10
  Session timing                  → max  5
  News risk clear                 → max  5
"""
import pandas as pd
from typing import Dict, Optional
from strategies import TradeSignal
from indicators.trend import TrendIndicators
from indicators.momentum import MomentumIndicators
from indicators.volume import VolumeIndicators
from indicators.support_resistance import SupportResistance
from utils.logger import get_logger

logger = get_logger(__name__)

SESSION_PREFERRED_PAIRS = {
    "london": ["EUR_USD", "GBP_USD", "EUR_GBP", "GBP_JPY", "EUR_JPY"],
    "ny": ["EUR_USD", "GBP_USD", "USD_CAD", "USD_JPY", "XAU_USD"],
    "asian": ["USD_JPY", "AUD_USD", "NZD_USD"],
    "overlap": ["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD"],
}

# Higher bar for volatile pairs — require stronger confluence before entry
PAIR_MIN_SCORES: dict = {
    "XAU_USD":  75,   # gold is highly volatile — need very strong confluence
    "US30_USD": 75,   # Dow has large point moves — same strict requirement
    "GBP_JPY":  70,   # high volatility cross — slightly above default
    "USD_JPY":  65,
    "EUR_USD":  60,
}


class ConfluenceEngine:
    def __init__(self, min_score: float = 60.0):
        self.min_score = min_score
        self.weights = {
            "trend_alignment": 20,
            "sr_level": 15,
            "pattern": 15,
            "momentum": 15,
            "smc_structure": 15,
            "volume": 10,
            "session": 5,
            "news_clear": 5,
        }

    def score_signal(self, signal: TradeSignal, data: dict, context: dict) -> float:
        score = 0.0
        breakdown = {}

        s = self._score_trend_alignment(signal, data)
        score += s; breakdown["trend_alignment"] = s

        s = self._score_sr_level(signal, data)
        score += s; breakdown["sr_level"] = s

        s = self._score_pattern(signal)
        score += s; breakdown["pattern"] = s

        s = self._score_momentum(signal, data)
        score += s; breakdown["momentum"] = s

        s = self._score_smc(signal)
        score += s; breakdown["smc_structure"] = s

        s = self._score_volume(signal, data)
        score += s; breakdown["volume"] = s

        s = self._score_session(signal, context)
        score += s; breakdown["session"] = s

        s = self._score_news_clear(signal, context)
        score += s; breakdown["news_clear"] = s

        score = round(min(score, 100), 2)
        signal.confluence_score = score
        signal.confidence_pct = score
        signal.metadata["score_breakdown"] = breakdown
        logger.debug(f"[Confluence] {signal.pair} {signal.strategy_name} score={score} {breakdown}")
        return score

    def _score_trend_alignment(self, signal: TradeSignal, data: dict) -> float:
        """Check EMA50 direction on D1, H4, H1."""
        tfs = ["D1", "H4", "H1"]
        aligned = 0
        total = 0
        for tf in tfs:
            df = data.get(tf)
            if df is None or len(df) < 55:
                continue
            try:
                ema50 = TrendIndicators.ema(df["close"], 50)
                above = df["close"].iloc[-1] > ema50.iloc[-1]
                if signal.direction == "BUY" and above:
                    aligned += 1
                elif signal.direction == "SELL" and not above:
                    aligned += 1
                total += 1
            except Exception:
                pass
        if total == 0:
            return 10.0  # neutral
        ratio = aligned / total
        return round(self.weights["trend_alignment"] * ratio, 2)

    def _score_sr_level(self, signal: TradeSignal, data: dict) -> float:
        """Check if entry is near a key S/R level."""
        df = data.get(signal.timeframe)
        if df is None:
            df = data.get("H1")
        if df is None or len(df) < 20:
            return 5.0
        try:
            sr = SupportResistance.dynamic_sr(df, lookback=50)
            levels = sr.get("support", []) + sr.get("resistance", [])
            close = signal.entry_price
            atr_approx = df["high"].tail(14).mean() - df["low"].tail(14).mean()
            for lvl in levels:
                if abs(close - lvl) < atr_approx * 0.5:
                    return float(self.weights["sr_level"])
        except Exception:
            pass
        return 0.0

    def _score_pattern(self, signal: TradeSignal) -> float:
        if signal.pattern_detected:
            return float(self.weights["pattern"])
        return 0.0

    def _score_momentum(self, signal: TradeSignal, data: dict) -> float:
        df = data.get(signal.timeframe)
        if df is None:
            df = data.get("H1")
        if df is None or len(df) < 30:
            return 5.0
        try:
            rsi = MomentumIndicators.rsi(df["close"], 14).iloc[-1]
            macd_data = TrendIndicators.macd(df["close"])
            macd_hist = macd_data["histogram"].iloc[-1]
            score = 0.0
            if signal.direction == "BUY":
                if 40 < rsi < 65:
                    score += self.weights["momentum"] * 0.5
                if macd_hist > 0:
                    score += self.weights["momentum"] * 0.5
            else:
                if 35 < rsi < 60:
                    score += self.weights["momentum"] * 0.5
                if macd_hist < 0:
                    score += self.weights["momentum"] * 0.5
            return round(score, 2)
        except Exception:
            return 5.0

    def _score_smc(self, signal: TradeSignal) -> float:
        if signal.smc_concept:
            return float(self.weights["smc_structure"])
        meta = signal.metadata or {}
        if meta.get("concept") in ("order_block", "fvg"):
            return float(self.weights["smc_structure"])
        return 0.0

    def _score_volume(self, signal: TradeSignal, data: dict) -> float:
        df = data.get(signal.timeframe)
        if df is None:
            df = data.get("H1")
        if df is None or len(df) < 25 or "volume" not in df.columns:
            return 3.0  # partial credit
        try:
            vol_spike = VolumeIndicators.detect_volume_spike(df["volume"], 20, 1.5)
            if vol_spike.iloc[-1]:
                return float(self.weights["volume"])
            return 0.0
        except Exception:
            return 3.0

    def _score_session(self, signal: TradeSignal, context: dict) -> float:
        session = context.get("session", "")
        pair = signal.pair
        preferred = SESSION_PREFERRED_PAIRS.get(session, [])
        if pair in preferred:
            return float(self.weights["session"])
        return 0.0

    def _score_news_clear(self, signal: TradeSignal, context: dict) -> float:
        news_risk = context.get("news_risk_score", 0)
        if news_risk == 0:
            return float(self.weights["news_clear"])
        if news_risk <= 1.0:
            return float(self.weights["news_clear"]) * 0.5
        return 0.0

    def is_tradeable(self, score: float, pair: str = "") -> bool:
        threshold = PAIR_MIN_SCORES.get(pair, self.min_score)
        return score >= threshold

    def update_weights(self, weights: dict):
        for key, val in weights.items():
            if key in self.weights:
                self.weights[key] = val
        logger.info(f"[Confluence] Weights updated: {self.weights}")
