"""Market session detection."""
from datetime import datetime
import pytz
from typing import Dict

EST = pytz.timezone("America/New_York")
UTC = pytz.utc

SESSIONS = {
    "sydney":  {"start": 17, "end": 2,  "tz": "Australia/Sydney"},
    "tokyo":   {"start": 19, "end": 4},
    "london":  {"start": 3,  "end": 12},
    "ny":      {"start": 8,  "end": 17},
    "overlap": {"start": 8,  "end": 12},   # London/NY overlap (EST)
}

SESSION_VOLATILITY = {
    "sydney": "low",
    "tokyo": "medium",
    "london": "high",
    "ny": "high",
    "overlap": "very_high",
}


class SessionDetector:

    @staticmethod
    def get_current_session(dt: datetime = None) -> str:
        if dt is None:
            dt = datetime.now(tz=UTC)
        est = dt.astimezone(EST)
        hour = est.hour

        if 8 <= hour < 12:
            return "overlap"
        if 3 <= hour < 12:
            return "london"
        if 8 <= hour < 17:
            return "ny"
        if 17 <= hour or hour < 4:
            return "asian"
        return "inter_session"

    @staticmethod
    def get_all_active_sessions(dt: datetime = None) -> list:
        if dt is None:
            dt = datetime.now(tz=UTC)
        est = dt.astimezone(EST)
        hour = est.hour
        active = []
        if 3 <= hour < 12:
            active.append("london")
        if 8 <= hour < 17:
            active.append("ny")
        if 8 <= hour < 12:
            active.append("overlap")
        if 17 <= hour or hour < 4:
            active.append("asian")
        return active or ["inter_session"]

    @staticmethod
    def get_session_volatility(session: str) -> str:
        return SESSION_VOLATILITY.get(session, "low")

    @staticmethod
    def is_market_open(dt: datetime = None) -> bool:
        if dt is None:
            dt = datetime.now(tz=UTC)
        est = dt.astimezone(EST)
        # Closed Friday 5pm EST to Sunday 5pm EST
        weekday = est.weekday()
        hour = est.hour
        if weekday == 4 and hour >= 17:
            return False
        if weekday == 5:
            return False
        if weekday == 6 and hour < 17:
            return False
        return True

    @staticmethod
    def get_session_info(dt: datetime = None) -> Dict:
        session = SessionDetector.get_current_session(dt)
        active = SessionDetector.get_all_active_sessions(dt)
        return {
            "primary_session": session,
            "active_sessions": active,
            "volatility": SessionDetector.get_session_volatility(session),
            "market_open": SessionDetector.is_market_open(dt),
        }
