"""
Forex Factory economic calendar scraper.
"""
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import pytz
import json
import re
from utils.logger import get_logger

logger = get_logger(__name__)

IMPACT_MAP = {
    "red": "HIGH",
    "orange": "MEDIUM",
    "yellow": "LOW",
    "gray": "HOLIDAY",
    "icon--ff-impact-red": "HIGH",
    "icon--ff-impact-ora": "MEDIUM",
    "icon--ff-impact-yel": "LOW",
    "icon--ff-impact-gra": "HOLIDAY",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
}


class ForexFactoryCalendar:
    BASE_URL = "https://www.forexfactory.com/calendar"
    EST = pytz.timezone("America/New_York")

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._cached_events = []
        self._cache_time = None
        self._cache_ttl = 3600  # 1 hour

    def get_calendar(self, target_date: datetime = None) -> pd.DataFrame:
        if target_date is None:
            target_date = datetime.now(tz=self.EST)
        date_str = target_date.strftime("%b%d.%Y").lower()
        url = f"{self.BASE_URL}?day={date_str}"

        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            return self._parse_html(response.text, target_date)
        except requests.RequestException as e:
            logger.error(f"[ForexFactory] Request failed: {e}")
            return pd.DataFrame()

    def _parse_html(self, html: str, base_date: datetime) -> pd.DataFrame:
        soup = BeautifulSoup(html, "lxml")
        rows = soup.select("tr.calendar__row")
        events = []
        current_date = base_date

        for row in rows:
            try:
                date_cell = row.select_one("td.calendar__date span")
                time_cell = row.select_one("td.calendar__time")
                currency_cell = row.select_one("td.calendar__currency")
                impact_cell = row.select_one("td.calendar__impact span")
                event_cell = row.select_one("td.calendar__event span.calendar__event-title")
                actual_cell = row.select_one("td.calendar__actual")
                forecast_cell = row.select_one("td.calendar__forecast")
                previous_cell = row.select_one("td.calendar__previous")

                if currency_cell is None or event_cell is None:
                    continue

                currency = currency_cell.get_text(strip=True)
                event_name = event_cell.get_text(strip=True)

                impact = "LOW"
                if impact_cell:
                    classes = " ".join(impact_cell.get("class", []))
                    for cls_key, imp_val in IMPACT_MAP.items():
                        if cls_key in classes:
                            impact = imp_val
                            break

                time_str = time_cell.get_text(strip=True) if time_cell else ""
                event_time = self._parse_time(time_str, current_date)

                actual = actual_cell.get_text(strip=True) if actual_cell else ""
                forecast = forecast_cell.get_text(strip=True) if forecast_cell else ""
                previous = previous_cell.get_text(strip=True) if previous_cell else ""

                events.append({
                    "time": event_time,
                    "currency": currency,
                    "impact": impact,
                    "event": event_name,
                    "actual": actual,
                    "forecast": forecast,
                    "previous": previous,
                })
            except Exception as e:
                logger.debug(f"[ForexFactory] Row parse error: {e}")
                continue

        return pd.DataFrame(events)

    def _parse_time(self, time_str: str, base_date: datetime) -> datetime:
        time_str = time_str.strip()
        if not time_str or time_str.lower() in ("all day", "tentative"):
            return base_date.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            t = datetime.strptime(time_str, "%I:%M%p")
            dt = base_date.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            if dt.tzinfo is None:
                dt = self.EST.localize(dt)
            return dt
        except ValueError:
            return base_date

    def get_week_events(self) -> pd.DataFrame:
        frames = []
        now = datetime.now(tz=self.EST)
        # Get Mon-Fri of current week
        weekday = now.weekday()
        monday = now - timedelta(days=weekday)
        for i in range(5):
            day = monday + timedelta(days=i)
            df = self.get_calendar(day)
            if not df.empty:
                frames.append(df)
        if frames:
            return pd.concat(frames, ignore_index=True)
        return pd.DataFrame()

    def get_high_impact_events(self, hours_ahead: int = 24) -> list:
        now = datetime.now(tz=self.EST)
        cutoff = now + timedelta(hours=hours_ahead)
        events = []
        df = self.get_week_events()
        if df.empty:
            return events
        high = df[df["impact"] == "HIGH"]
        for _, row in high.iterrows():
            t = row["time"]
            if hasattr(t, "tzinfo") and t.tzinfo is None:
                t = self.EST.localize(t)
            if now <= t <= cutoff:
                events.append(row.to_dict())
        return events

    def get_events_for_currency(self, currency: str, hours_ahead: int = 48) -> list:
        now = datetime.now(tz=self.EST)
        cutoff = now + timedelta(hours=hours_ahead)
        df = self.get_week_events()
        if df.empty:
            return []
        filtered = df[df["currency"] == currency.upper()]
        result = []
        for _, row in filtered.iterrows():
            t = row["time"]
            if hasattr(t, "tzinfo") and t.tzinfo is None:
                t = self.EST.localize(t)
            if now <= t <= cutoff:
                result.append(row.to_dict())
        return result

    def save_to_db(self, events: list):
        from database.db import DatabaseManager
        db = DatabaseManager()
        for ev in events:
            try:
                db.save_news_event({
                    "event_id": f"ff_{ev.get('currency','')}_{ev.get('event','').replace(' ','_')}_{ev.get('time','')}",
                    "title": ev.get("event", ""),
                    "currency": ev.get("currency", ""),
                    "impact": ev.get("impact", "LOW"),
                    "scheduled_time": ev.get("time"),
                    "forecast": str(ev.get("forecast", "")),
                    "previous": str(ev.get("previous", "")),
                    "pairs_affected": ev.get("currency", ""),
                })
            except Exception as e:
                logger.debug(f"[ForexFactory] DB save error: {e}")
