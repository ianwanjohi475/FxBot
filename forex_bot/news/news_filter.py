"""
News filter — controls trading around high-impact events.
"""
from datetime import datetime, timedelta
import pytz
from typing import Tuple, List
from .forex_factory import ForexFactoryCalendar
from utils.logger import get_logger

logger = get_logger(__name__)

VERY_HIGH_IMPACT_EVENTS = [
    "FOMC", "NFP", "Non-Farm", "CPI", "Interest Rate",
    "Fed Chair", "Federal Reserve", "ECB Press", "BOE Rate",
    "Employment Change", "Unemployment",
]

EST = pytz.timezone("America/New_York")
UTC = pytz.utc


class NewsFilter:
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.ff = ForexFactoryCalendar()
        self.upcoming: List[dict] = []
        self.last_refresh: datetime = None
        self.refresh_interval = 3600  # seconds
        self.pause_before_high = self.config.get("pause_before_high_impact", 30)
        self.pause_before_vh = self.config.get("pause_before_fomc_nfp_cpi", 60)
        self.resume_after_high = self.config.get("resume_after", 15)
        self.resume_after_vh = 30

    def refresh_calendar(self):
        try:
            events_df = self.ff.get_week_events()
            if events_df.empty:
                return
            self.upcoming = []
            for _, row in events_df.iterrows():
                if row.get("impact") in ("HIGH", "MEDIUM"):
                    self.upcoming.append(row.to_dict())
            self.last_refresh = datetime.now(tz=UTC)
            logger.info(f"[NewsFilter] Loaded {len(self.upcoming)} upcoming events")
        except Exception as e:
            logger.error(f"[NewsFilter] Calendar refresh error: {e}")

    def _should_refresh(self) -> bool:
        if self.last_refresh is None:
            return True
        elapsed = (datetime.now(tz=UTC) - self.last_refresh).total_seconds()
        return elapsed > self.refresh_interval

    def can_trade(self, pair: str, current_time: datetime = None) -> Tuple[bool, str]:
        if current_time is None:
            current_time = datetime.now(tz=UTC)
        if current_time.tzinfo is None:
            current_time = UTC.localize(current_time)

        if self.is_friday_afternoon(current_time):
            return False, "Friday afternoon filter — no new trades after 3pm EST"

        if self.is_sunday_open(current_time):
            return False, "Sunday gap risk — no trades in first 15 min of weekly open"

        if self._should_refresh():
            self.refresh_calendar()

        currencies = self.get_pair_currencies(pair)

        for event in self.upcoming:
            ev_time = event.get("time")
            if ev_time is None:
                continue
            if hasattr(ev_time, "tzinfo") and ev_time.tzinfo is None:
                ev_time = EST.localize(ev_time)

            ev_currency = event.get("currency", "")
            if ev_currency not in currencies:
                continue

            ev_name = event.get("event", "")
            is_vh = any(kw.lower() in ev_name.lower() for kw in VERY_HIGH_IMPACT_EVENTS)
            pause_before = self.pause_before_vh if is_vh else self.pause_before_high
            resume_after = self.resume_after_vh if is_vh else self.resume_after_high

            mins_to_event = (ev_time - current_time).total_seconds() / 60
            mins_since_event = (current_time - ev_time).total_seconds() / 60

            if 0 < mins_to_event <= pause_before:
                return False, f"Paused {pause_before}m before {ev_name} ({ev_currency})"

            if 0 < mins_since_event <= resume_after:
                return False, f"Paused {resume_after}m after {ev_name} ({ev_currency})"

        return True, "OK"

    def get_upcoming_events(self, pair: str, hours: int = 4) -> List[dict]:
        if self._should_refresh():
            self.refresh_calendar()
        currencies = self.get_pair_currencies(pair)
        now = datetime.now(tz=UTC)
        cutoff = now + timedelta(hours=hours)
        result = []
        for event in self.upcoming:
            if event.get("currency") not in currencies:
                continue
            ev_time = event.get("time")
            if ev_time is None:
                continue
            if hasattr(ev_time, "tzinfo") and ev_time.tzinfo is None:
                ev_time = EST.localize(ev_time)
            if now <= ev_time <= cutoff:
                result.append(event)
        return result

    def get_pair_currencies(self, pair: str) -> List[str]:
        clean = pair.replace("_", "").replace("/", "")
        if len(clean) == 6:
            return [clean[:3], clean[3:]]
        return [pair]

    def is_friday_afternoon(self, dt: datetime = None) -> bool:
        if dt is None:
            dt = datetime.now(tz=UTC)
        est_dt = dt.astimezone(EST)
        return est_dt.weekday() == 4 and est_dt.hour >= 15

    def is_sunday_open(self, dt: datetime = None) -> bool:
        if dt is None:
            dt = datetime.now(tz=UTC)
        est_dt = dt.astimezone(EST)
        return est_dt.weekday() == 6 and est_dt.hour == 17 and est_dt.minute < 15

    def get_news_risk_score(self, pair: str, hours_ahead: int = 2) -> float:
        events = self.get_upcoming_events(pair, hours_ahead)
        score = 0.0
        for event in events:
            impact = event.get("impact", "LOW")
            if impact == "HIGH":
                score += 2.0
            elif impact == "MEDIUM":
                score += 1.0
        return min(score, 5.0)
