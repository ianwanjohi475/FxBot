"""
Geopolitical event monitoring using NewsAPI + keyword classification.
"""
import requests
import os
from datetime import datetime, timedelta
import pytz
from typing import List, Dict
from utils.logger import get_logger

logger = get_logger(__name__)

RISK_OFF_KEYWORDS = [
    "war", "conflict", "invasion", "attack", "sanctions", "crisis",
    "recession", "inflation", "tariff", "default", "bank run",
    "geopolitical", "nuclear", "escalation", "trade war",
]
RISK_ON_KEYWORDS = [
    "trade deal", "ceasefire", "stimulus", "recovery", "growth",
    "rate cut", "peace", "agreement", "surplus",
]
ELECTION_KEYWORDS = ["election", "vote", "referendum", "resign", "impeach", "cabinet"]
OIL_KEYWORDS = ["oil", "opec", "crude", "petroleum", "energy", "brent", "wti"]

SAFE_HAVEN_PAIRS = ["USD_JPY", "USD_CHF", "XAU_USD"]
OIL_PAIRS = ["USD_CAD"]


class GeopoliticalMonitor:
    def __init__(self):
        self.news_api_key = os.getenv("NEWS_API_KEY", "")
        self.cached_events: List[dict] = []
        self.last_fetch: datetime = None
        self.cache_ttl_minutes = 60

    def fetch_news(self, query: str = "forex OR currency OR central bank",
                   hours_back: int = 6) -> List[dict]:
        if not self.news_api_key:
            logger.debug("[GeopoliticalMonitor] No NEWS_API_KEY set")
            return []

        # Use cache if fresh
        if (self.last_fetch and
                (datetime.now(tz=pytz.utc) - self.last_fetch).total_seconds() < self.cache_ttl_minutes * 60):
            return self.cached_events

        try:
            from_time = (datetime.now(tz=pytz.utc) - timedelta(hours=hours_back)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": query,
                "from": from_time,
                "sortBy": "publishedAt",
                "language": "en",
                "apiKey": self.news_api_key,
                "pageSize": 30,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
            self.cached_events = articles
            self.last_fetch = datetime.now(tz=pytz.utc)
            return articles
        except Exception as e:
            logger.error(f"[GeopoliticalMonitor] NewsAPI error: {e}")
            return []

    def classify_event(self, headline: str) -> dict:
        h = headline.lower()
        event_type = "neutral"
        if any(kw in h for kw in RISK_OFF_KEYWORDS):
            event_type = "risk_off"
        elif any(kw in h for kw in RISK_ON_KEYWORDS):
            event_type = "risk_on"
        elif any(kw in h for kw in ELECTION_KEYWORDS):
            event_type = "election"
        elif any(kw in h for kw in OIL_KEYWORDS):
            event_type = "oil"
        return {"headline": headline, "event_type": event_type}

    def get_affected_pairs(self, event_type: str) -> List[str]:
        if event_type == "risk_off":
            return SAFE_HAVEN_PAIRS + ["XAU_USD"]
        if event_type == "risk_on":
            return ["AUD_USD", "NZD_USD", "GBP_USD", "EUR_USD"]
        if event_type == "oil":
            return OIL_PAIRS
        return []

    def get_current_risk_sentiment(self) -> str:
        articles = self.fetch_news()
        risk_off_count = 0
        risk_on_count = 0
        for article in articles:
            title = article.get("title", "")
            desc = article.get("description", "")
            text = f"{title} {desc}".lower()
            for kw in RISK_OFF_KEYWORDS:
                if kw in text:
                    risk_off_count += 1
                    break
            for kw in RISK_ON_KEYWORDS:
                if kw in text:
                    risk_on_count += 1
                    break
        if risk_off_count > risk_on_count * 1.5:
            return "risk_off"
        if risk_on_count > risk_off_count * 1.5:
            return "risk_on"
        return "neutral"

    def get_upcoming_elections(self, days_ahead: int = 30) -> List[dict]:
        """Hardcoded major upcoming elections/political events 2025-2026."""
        elections = [
            {"country": "Germany", "currency": "EUR", "date": "2025-02-23", "event": "Federal Election"},
            {"country": "Australia", "currency": "AUD", "date": "2025-05-17", "event": "Federal Election"},
            {"country": "Japan", "currency": "JPY", "date": "2025-07-27", "event": "Upper House Election"},
            {"country": "Canada", "currency": "CAD", "date": "2025-04-28", "event": "Federal Election"},
        ]
        now = datetime.now(tz=pytz.utc)
        upcoming = []
        for e in elections:
            try:
                dt = datetime.strptime(e["date"], "%Y-%m-%d").replace(tzinfo=pytz.utc)
                days_until = (dt - now).days
                if 0 <= days_until <= days_ahead:
                    upcoming.append({**e, "days_until": days_until, "datetime": dt})
            except ValueError:
                continue
        return upcoming

    def should_avoid_pair(self, pair: str) -> tuple:
        sentiment = self.get_current_risk_sentiment()
        if sentiment == "risk_off" and pair in ["AUD_USD", "NZD_USD", "GBP_USD"]:
            return True, f"Risk-off sentiment detected — avoiding {pair}"
        return False, "OK"
