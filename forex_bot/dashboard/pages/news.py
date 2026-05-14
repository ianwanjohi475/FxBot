"""News & Events dashboard page."""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def render():
    st.title("📰 News & Events")

    tab1, tab2, tab3 = st.tabs(["Economic Calendar", "Central Bank Meetings", "Geopolitical"])

    with tab1:
        st.subheader("This Week's Economic Calendar")
        with st.spinner("Loading calendar..."):
            events_df = _load_forex_factory()

        if not events_df.empty:
            # Color by impact
            def impact_color(impact):
                colors = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢", "HOLIDAY": "⚪"}
                return colors.get(impact, "⚪")

            events_df["Impact"] = events_df.get("impact", pd.Series(["LOW"]*len(events_df))).apply(impact_color)
            display_cols = ["Impact", "time", "currency", "event", "actual", "forecast", "previous"]
            available = [c for c in display_cols if c in events_df.columns]
            st.dataframe(events_df[available], use_container_width=True, hide_index=True)
        else:
            st.info("Could not load calendar data. Check internet connection.")

        # Countdown to next high-impact event
        st.subheader("Next High-Impact Event")
        next_event = _get_next_high_impact(events_df)
        if next_event:
            now = datetime.now(tz=pytz.timezone("America/New_York"))
            ev_time = next_event.get("time")
            if ev_time and hasattr(ev_time, "__sub__"):
                try:
                    delta = ev_time - now
                    mins = int(delta.total_seconds() / 60)
                    if mins > 0:
                        st.metric(
                            f"⏰ {next_event.get('event','?')} ({next_event.get('currency','?')})",
                            f"In {mins//60}h {mins%60}m"
                        )
                except Exception:
                    st.info(f"Next: {next_event.get('event')}")

    with tab2:
        st.subheader("Central Bank Meetings — Next 30 Days")
        try:
            from news.investing_calendar import InvestingCalendar
            cal = InvestingCalendar()
            meetings = cal.get_central_bank_meetings()
            now = datetime.now(tz=pytz.utc)
            upcoming = [
                m for m in meetings
                if (m["datetime"] - now).days <= 30
            ]
            if upcoming:
                rows = [{
                    "Bank": m["bank"],
                    "Currency": m["currency"],
                    "Date": m["date"],
                    "Days Until": f"{(m['datetime']-now).days}d",
                    "Impact": "🔴 HIGH",
                } for m in upcoming]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info("No central bank meetings in the next 30 days")
        except Exception as e:
            st.error(f"Error loading meetings: {e}")

    with tab3:
        st.subheader("Geopolitical & Political Events")
        try:
            from news.geopolitical import GeopoliticalMonitor
            geo = GeopoliticalMonitor()
            elections = geo.get_upcoming_elections(days_ahead=60)
            sentiment = geo.get_current_risk_sentiment()

            st.metric("Current Market Sentiment", sentiment.upper().replace("_", " "))
            st.markdown("---")

            if elections:
                rows = [{
                    "Country": e["country"],
                    "Currency": e["currency"],
                    "Event": e["event"],
                    "Date": e["date"],
                    "Days Until": e["days_until"],
                } for e in elections]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info("No major elections in the next 60 days")
        except Exception as e:
            st.warning(f"Geopolitical data unavailable: {e}")


def _load_forex_factory():
    try:
        from news.forex_factory import ForexFactoryCalendar
        ff = ForexFactoryCalendar()
        return ff.get_week_events()
    except Exception:
        return pd.DataFrame()


def _get_next_high_impact(df: pd.DataFrame) -> dict:
    if df.empty:
        return None
    high = df[df.get("impact", pd.Series()) == "HIGH"] if "impact" in df.columns else pd.DataFrame()
    if high.empty:
        return None
    return high.iloc[0].to_dict() if not high.empty else None
