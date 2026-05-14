"""
FxBot Live Dashboard — Streamlit multi-page app.
Run: streamlit run dashboard/app.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from utils.config_loader import config

st.set_page_config(
    page_title="FxBot Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom dark theme CSS
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .metric-card {
        background: #1e2130; border-radius: 10px;
        padding: 15px; border: 1px solid #2d3250;
    }
    .stMetric { background: #1e2130; border-radius: 8px; padding: 10px; }
    .profit { color: #00ff88; }
    .loss { color: #ff4444; }
</style>
""", unsafe_allow_html=True)

# Sidebar navigation
st.sidebar.image("https://img.icons8.com/color/96/forex.png", width=60)
st.sidebar.title("FxBot")
st.sidebar.markdown("---")

PAGES = {
    "📊 Live Overview": "pages.overview",
    "📓 Trade Journal": "pages.journal",
    "🧠 Strategy Performance": "pages.strategies",
    "📰 News & Events": "pages.news",
    "🔬 Backtesting": "pages.backtest",
    "🛡️ Risk Monitor": "pages.risk_monitor",
}

selection = st.sidebar.radio("Navigate", list(PAGES.keys()))
st.sidebar.markdown("---")

mode = "PAPER" if os.getenv("PAPER_TRADING", "true").lower() == "true" else "LIVE"
mode_color = "🟡" if mode == "PAPER" else "🔴"
st.sidebar.markdown(f"**Mode:** {mode_color} {mode}")
st.sidebar.markdown(f"**Bot:** {'🟢 Running' if True else '🔴 Stopped'}")

# Load and render selected page
import importlib
module_name = PAGES[selection]
try:
    page = importlib.import_module(module_name)
    page.render()
except Exception as e:
    st.error(f"Error loading page: {e}")
    import traceback
    st.code(traceback.format_exc())
