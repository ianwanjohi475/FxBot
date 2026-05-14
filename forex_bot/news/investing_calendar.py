"""
Investing.com economic calendar scraper + hardcoded central bank schedule.
"""
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import pytz
from utils.logger import get_logger

logger = get_logger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.investing.com/economic-calendar/",
}

# Hardcoded 2025-2026 central bank meeting schedule (approximate)
CENTRAL_BANK_MEETINGS = [
    # FOMC
    {"bank": "FOMC", "currency": "USD", "date": "2025-01-29", "impact": "HIGH"},
    {"bank": "FOMC", "currency": "USD", "date": "2025-03-19", "impact": "HIGH"},
    {"bank": "FOMC", "currency": "USD", "date": "2025-05-07", "impact": "HIGH"},
    {"bank": "FOMC", "currency": "USD", "date": "2025-06-18", "impact": "HIGH"},
    {"bank": "FOMC", "currency": "USD", "date": "2025-07-30", "impact": "HIGH"},
    {"bank": "FOMC", "currency": "USD", "date": "2025-09-17", "impact": "HIGH"},
    {"bank": "FOMC", "currency": "USD", "date": "2025-10-29", "impact": "HIGH"},
    {"bank": "FOMC", "currency": "USD", "date": "2025-12-10", "impact": "HIGH"},
    # ECB
    {"bank": "ECB", "currency": "EUR", "date": "2025-01-30", "impact": "HIGH"},
    {"bank": "ECB", "currency": "EUR", "date": "2025-03-06", "impact": "HIGH"},
    {"bank": "ECB", "currency": "EUR", "date": "2025-04-17", "impact": "HIGH"},
    {"bank": "ECB", "currency": "EUR", "date": "2025-06-05", "impact": "HIGH"},
    {"bank": "ECB", "currency": "EUR", "date": "2025-07-24", "impact": "HIGH"},
    {"bank": "ECB", "currency": "EUR", "date": "2025-09-11", "impact": "HIGH"},
    {"bank": "ECB", "currency": "EUR", "date": "2025-10-30", "impact": "HIGH"},
    {"bank": "ECB", "currency": "EUR", "date": "2025-12-18", "impact": "HIGH"},
    # BOE
    {"bank": "BOE", "currency": "GBP", "date": "2025-02-06", "impact": "HIGH"},
    {"bank": "BOE", "currency": "GBP", "date": "2025-03-20", "impact": "HIGH"},
    {"bank": "BOE", "currency": "GBP", "date": "2025-05-08", "impact": "HIGH"},
    {"bank": "BOE", "currency": "GBP", "date": "2025-06-19", "impact": "HIGH"},
    {"bank": "BOE", "currency": "GBP", "date": "2025-08-07", "impact": "HIGH"},
    {"bank": "BOE", "currency": "GBP", "date": "2025-09-18", "impact": "HIGH"},
    {"bank": "BOE", "currency": "GBP", "date": "2025-11-06", "impact": "HIGH"},
    {"bank": "BOE", "currency": "GBP", "date": "2025-12-18", "impact": "HIGH"},
    # BOJ
    {"bank": "BOJ", "currency": "JPY", "date": "2025-01-24", "impact": "HIGH"},
    {"bank": "BOJ", "currency": "JPY", "date": "2025-03-19", "impact": "HIGH"},
    {"bank": "BOJ", "currency": "JPY", "date": "2025-04-30", "impact": "HIGH"},
    {"bank": "BOJ", "currency": "JPY", "date": "2025-06-17", "impact": "HIGH"},
    {"bank": "BOJ", "currency": "JPY", "date": "2025-07-31", "impact": "HIGH"},
    {"bank": "BOJ", "currency": "JPY", "date": "2025-09-19", "impact": "HIGH"},
    {"bank": "BOJ", "currency": "JPY", "date": "2025-10-29", "impact": "HIGH"},
    {"bank": "BOJ", "currency": "JPY", "date": "2025-12-19", "impact": "HIGH"},
    # RBA
    {"bank": "RBA", "currency": "AUD", "date": "2025-02-18", "impact": "HIGH"},
    {"bank": "RBA", "currency": "AUD", "date": "2025-04-01", "impact": "HIGH"},
    {"bank": "RBA", "currency": "AUD", "date": "2025-05-20", "impact": "HIGH"},
    {"bank": "RBA", "currency": "AUD", "date": "2025-07-08", "impact": "HIGH"},
    {"bank": "RBA", "currency": "AUD", "date": "2025-08-05", "impact": "HIGH"},
    {"bank": "RBA", "currency": "AUD", "date": "2025-09-23", "impact": "HIGH"},
    {"bank": "RBA", "currency": "AUD", "date": "2025-11-04", "impact": "HIGH"},
    {"bank": "RBA", "currency": "AUD", "date": "2025-12-09", "impact": "HIGH"},
]


class InvestingCalendar:
    BASE_URL = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_events(self, days_ahead: int = 7) -> pd.DataFrame:
        """Fetch from Investing.com API."""
        now = datetime.now(tz=pytz.utc)
        end = now + timedelta(days=days_ahead)
        payload = {
            "dateFrom": now.strftime("%Y-%m-%d"),
            "dateTo": end.strftime("%Y-%m-%d"),
            "timeZone": "0",
            "timeFilter": "timeOnly",
            "currentTab": "custom",
            "limit_from": "0",
            "importance[]": ["3"],  # High impact only
        }
        try:
            resp = self.session.post(self.BASE_URL, data=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(data)
        except Exception as e:
            logger.error(f"[InvestingCalendar] Failed: {e}")
            return pd.DataFrame()

    def _parse_response(self, data: dict) -> pd.DataFrame:
        html = data.get("data", "")
        if not html:
            return pd.DataFrame()
        soup = BeautifulSoup(html, "lxml")
        rows = soup.select("tr.js-event-item")
        events = []
        for row in rows:
            try:
                event_name = row.select_one(".event")
                currency = row.select_one(".flagCur")
                time_cell = row.select_one(".time")
                events.append({
                    "event": event_name.get_text(strip=True) if event_name else "",
                    "currency": currency.get_text(strip=True) if currency else "",
                    "time": time_cell.get_text(strip=True) if time_cell else "",
                    "impact": "HIGH",
                })
            except Exception:
                continue
        return pd.DataFrame(events)

    def get_central_bank_meetings(self) -> list:
        """Return upcoming central bank meetings from hardcoded schedule."""
        now = datetime.now(tz=pytz.utc)
        upcoming = []
        for meeting in CENTRAL_BANK_MEETINGS:
            try:
                mt = datetime.strptime(meeting["date"], "%Y-%m-%d").replace(tzinfo=pytz.utc)
                if mt >= now:
                    upcoming.append({**meeting, "datetime": mt})
            except ValueError:
                continue
        return sorted(upcoming, key=lambda x: x["datetime"])

    def get_major_events(self) -> dict:
        """Return structured list of major recurring events."""
        meetings = self.get_central_bank_meetings()
        return {
            "central_bank_meetings": meetings,
            "next_fomc": next((m for m in meetings if m["bank"] == "FOMC"), None),
            "next_ecb": next((m for m in meetings if m["bank"] == "ECB"), None),
            "next_boe": next((m for m in meetings if m["bank"] == "BOE"), None),
        }
