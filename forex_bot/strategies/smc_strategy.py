"""
Smart Money Concepts (SMC) / ICT Strategy.
Entry: BOS/CHoCH for trend → OB or FVG retest in OTE zone during kill zone.
"""
import pandas as pd
from typing import Optional
from . import TradeSignal
from patterns.smc import SmartMoneyConcepts
from indicators.volatility import VolatilityIndicators
from indicators.trend import TrendIndicators
from utils.logger import get_logger
from datetime import datetime
import pytz

logger = get_logger(__name__)


class SMCStrategy:
    name = "smc_strategy"
    preferred_timeframes = ["H1", "H4", "M15"]

    def analyze(
        self,
        data: dict,
        pair: str,
        current_price: float,
        atr: float,
        current_time: datetime = None,
        spread_pips: float = 1.5,
    ) -> Optional[TradeSignal]:
        if current_time is None:
            current_time = datetime.now(tz=pytz.utc)

        # Check kill zone
        kz = SmartMoneyConcepts.kill_zone_active(current_time)

        for tf in self.preferred_timeframes:
            if tf not in data or data[tf] is None or len(data[tf]) < 30:
                continue
            df = data[tf]
            signal = self._analyze_tf(df, pair, tf, current_price, atr, kz)
            if signal:
                return signal
        return None

    def _analyze_tf(
        self,
        df: pd.DataFrame,
        pair: str,
        tf: str,
        current_price: float,
        atr: float,
        kill_zone: dict,
    ) -> Optional[TradeSignal]:
        smc = SmartMoneyConcepts.analyze_all(df)
        atr_series = VolatilityIndicators.atr(df, 14)
        current_atr = atr_series.iloc[-1] if not pd.isna(atr_series.iloc[-1]) else atr

        # Determine bias from BOS / CHoCH
        bos_list = smc.get("bos", [])
        choch_list = smc.get("choch", [])
        direction = None
        smc_concept = None

        if choch_list:
            last = choch_list[-1]
            direction = "BUY" if last["type"] == "bullish_choch" else "SELL"
            smc_concept = last["type"]
        elif bos_list:
            last = bos_list[-1]
            direction = "BUY" if last["type"] == "bullish_bos" else "SELL"
            smc_concept = last["type"]

        if direction is None:
            return None

        # ── Trend strength gate ──────────────────────────────────────────────
        # SMC setups need at least a developing trend (ADX >= 20).
        # DI alignment must match the structural bias.
        try:
            adx_data = TrendIndicators.adx(df, 14)
            adx_val  = adx_data["adx"].iloc[-1]
            plus_di  = adx_data["plus_di"].iloc[-1]
            minus_di = adx_data["minus_di"].iloc[-1]
        except Exception:
            return None
        if adx_val < 20:
            return None  # Ranging market — SMC structure not reliable
        if direction == "BUY" and plus_di <= minus_di:
            return None  # DI not confirming bullish bias
        if direction == "SELL" and minus_di <= plus_di:
            return None  # DI not confirming bearish bias

        # Check for OB in direction
        obs = smc.get("order_blocks", [])
        fvgs = smc.get("fvg", [])

        ob_match = None
        for ob in reversed(obs):
            if direction == "BUY" and ob["type"] == "bullish_ob":
                if ob["low"] <= current_price <= ob["high"]:
                    ob_match = ob
                    break
            elif direction == "SELL" and ob["type"] == "bearish_ob":
                if ob["low"] <= current_price <= ob["high"]:
                    ob_match = ob
                    break

        fvg_match = None
        for fvg in reversed(fvgs):
            if direction == "BUY" and fvg["type"] == "bullish_fvg":
                if fvg["bottom"] <= current_price <= fvg["top"]:
                    fvg_match = fvg
                    break
            elif direction == "SELL" and fvg["type"] == "bearish_fvg":
                if fvg["bottom"] <= current_price <= fvg["top"]:
                    fvg_match = fvg
                    break

        if ob_match is None and fvg_match is None:
            return None

        # Build signal
        structure = ob_match or fvg_match
        concept_name = "order_block" if ob_match else "fvg"
        kz_bonus = kill_zone.get("active", False)

        if direction == "BUY":
            # OB uses "low", FVG uses "bottom" — handle both
            sl_base = structure.get("low") or structure.get("bottom") or (current_price - current_atr)
            sl = sl_base - current_atr * 0.5
            tp1 = current_price + current_atr * 1.5
            tp2 = current_price + current_atr * 3.0
            tp3 = current_price + current_atr * 5.0
        else:
            # OB uses "high", FVG uses "top" — handle both
            sl_base = structure.get("high") or structure.get("top") or (current_price + current_atr)
            sl = sl_base + current_atr * 0.5
            tp1 = current_price - current_atr * 1.5
            tp2 = current_price - current_atr * 3.0
            tp3 = current_price - current_atr * 5.0

        return TradeSignal(
            pair=pair,
            direction=direction,
            strategy_name=self.name,
            timeframe=tf,
            entry_price=current_price,
            sl_price=round(sl, 5),
            tp1_price=round(tp1, 5),
            tp2_price=round(tp2, 5),
            tp3_price=round(tp3, 5),
            smc_concept=smc_concept,
            indicators={"atr": round(current_atr, 5), "adx": round(adx_val, 2),
                        "plus_di": round(plus_di, 2), "minus_di": round(minus_di, 2)},
            metadata={
                "concept": concept_name,
                "kill_zone": kill_zone.get("zone_name"),
                "kill_zone_active": kz_bonus,
                "structure_high": structure.get("high"),
                "structure_low": structure.get("low"),
            },
        )
