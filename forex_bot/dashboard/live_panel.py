"""
FxBot Live Score Panel — standalone Tkinter window.
Launches automatically with the bot and shows live scores
for all pairs. Reads data/fxbot_scores.csv every 5 seconds.
"""
import csv
import os
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime, timezone

# ── Colours ────────────────────────────────────────────────────────
BG        = "#0d0d0d"
BG2       = "#141414"
BG3       = "#1a1f2e"
FG        = "#e0e0e0"
FG_DIM    = "#555555"
FG_HEAD   = "#888888"
GRN       = "#00e676"   # score ≥ 75
YLW       = "#ffeb3b"   # score ≥ 60
ORG       = "#ff9800"   # score ≥ 45
RED_DIM   = "#444444"   # score < 45
BUY_CLR   = "#29b6f6"
SELL_CLR  = "#ef5350"
TREND_CLR = "#5c6bc0"
RANGE_CLR = "#ab47bc"
VOLT_CLR  = "#ff7043"

W, H      = 760, 295
ROW_H     = 32
BAR_CHARS = 12


def score_color(s: int) -> str:
    if s >= 75: return GRN
    if s >= 60: return YLW
    if s >= 45: return ORG
    return RED_DIM


def score_bar(s: int) -> str:
    filled = round(s / 100 * BAR_CHARS)
    return "█" * filled + "░" * (BAR_CHARS - filled)


def regime_color(r: str) -> str:
    r = r.lower()
    if "trend" in r: return TREND_CLR
    if "rang"  in r: return RANGE_CLR
    if "volat" in r: return VOLT_CLR
    return FG_DIM


def regime_badge(r: str) -> str:
    r = r.lower()
    if "trend" in r: return "TREND  "
    if "rang"  in r: return "RANGE  "
    if "volat" in r: return "VOLAT  "
    return "?      "


def find_scores_file() -> str:
    """Look for fxbot_scores.csv in data/ folder next to forex_bot/."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "..", "data", "fxbot_scores.csv"),
        os.path.join(here, "..", "..", "fxbot_scores.csv"),
        os.path.join(here, "..",        "data", "fxbot_scores.csv"),
    ]
    for p in candidates:
        if os.path.exists(os.path.normpath(p)):
            return os.path.normpath(p)
    # Return preferred write location even if it doesn't exist yet
    preferred = os.path.normpath(candidates[0])
    os.makedirs(os.path.dirname(preferred), exist_ok=True)
    return preferred


def read_scores(path: str) -> list[dict]:
    rows = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except Exception:
        pass
    return rows


class LivePanel:
    def __init__(self, scores_path: str):
        self.scores_path = scores_path
        self.root = tk.Tk()
        self.root.title("FxBot Live Score Dashboard")
        self.root.configure(bg=BG)
        self.root.geometry(f"{W}x{H}+30+30")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", False)

        self._mono  = tkfont.Font(family="Courier New", size=10)
        self._bold  = tkfont.Font(family="Courier New", size=10, weight="bold")
        self._head  = tkfont.Font(family="Arial",       size=11, weight="bold")
        self._small = tkfont.Font(family="Courier New", size=9)

        self._build_ui()
        self._start_refresh()

    # ── UI construction ─────────────────────────────────────────────

    def _build_ui(self):
        # Header bar
        hdr = tk.Frame(self.root, bg=BG3, height=36)
        hdr.pack(fill="x", side="top")

        self._lbl_title = tk.Label(
            hdr, text="  FxBot Live Score Dashboard",
            bg=BG3, fg=FG, font=self._head, anchor="w")
        self._lbl_title.pack(side="left", padx=4, pady=6)

        self._lbl_session = tk.Label(
            hdr, text="", bg=BG3, fg=FG_DIM, font=self._small, anchor="e")
        self._lbl_session.pack(side="right", padx=10, pady=6)

        # Column headers
        cols = tk.Frame(self.root, bg=BG2)
        cols.pack(fill="x", padx=0, pady=(2, 0))
        headers = [
            ("PAIR",     8,  "w"),
            ("SC",       4,  "e"),
            ("SCORE BAR",          14, "w"),
            ("DIR",      6,  "w"),
            ("REGIME",   8,  "w"),
            ("STRATEGY", 22, "w"),
            ("TIME",     6,  "e"),
        ]
        for txt, w, anc in headers:
            tk.Label(cols, text=txt, bg=BG2, fg=FG_HEAD,
                     font=self._small, width=w, anchor=anc
                     ).pack(side="left", padx=(6, 0), pady=2)

        # Separator
        tk.Frame(self.root, bg="#222222", height=1).pack(fill="x")

        # Pair rows
        self._rows: list[dict] = []
        self._row_frames: list[tk.Frame] = []
        for i in range(6):   # max 6 pairs
            row_bg = BG if i % 2 == 0 else BG2
            fr = tk.Frame(self.root, bg=row_bg, height=ROW_H)
            fr.pack(fill="x", padx=0)
            fr.pack_propagate(False)

            lbl_pair  = tk.Label(fr, bg=row_bg, fg=FG,     font=self._bold,  width=8,  anchor="w")
            lbl_score = tk.Label(fr, bg=row_bg, fg=GRN,    font=self._bold,  width=4,  anchor="e")
            lbl_bar   = tk.Label(fr, bg=row_bg, fg=GRN,    font=self._mono,  width=14, anchor="w")
            lbl_dir   = tk.Label(fr, bg=row_bg, fg=BUY_CLR,font=self._bold,  width=6,  anchor="w")
            lbl_reg   = tk.Label(fr, bg=row_bg, fg=TREND_CLR,font=self._small,width=8, anchor="w")
            lbl_strat = tk.Label(fr, bg=row_bg, fg=FG_DIM, font=self._small, width=22, anchor="w")
            lbl_time  = tk.Label(fr, bg=row_bg, fg=FG_DIM, font=self._small, width=6,  anchor="e")

            for lbl in (lbl_pair, lbl_score, lbl_bar, lbl_dir, lbl_reg, lbl_strat, lbl_time):
                lbl.pack(side="left", padx=(6, 0), pady=4)

            self._rows.append({
                "frame": fr, "pair": lbl_pair, "score": lbl_score,
                "bar": lbl_bar, "dir": lbl_dir, "reg": lbl_reg,
                "strat": lbl_strat, "time": lbl_time, "bg": row_bg,
            })

        # Separator
        tk.Frame(self.root, bg="#222222", height=1).pack(fill="x")

        # Footer / best setup
        foot = tk.Frame(self.root, bg=BG3, height=34)
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)

        self._lbl_best = tk.Label(
            foot, text="  Waiting for bot data...",
            bg=BG3, fg=FG_DIM, font=self._head, anchor="w")
        self._lbl_best.pack(side="left", padx=6, pady=5)

        self._lbl_updated = tk.Label(
            foot, text="", bg=BG3, fg=FG_DIM, font=self._small, anchor="e")
        self._lbl_updated.pack(side="right", padx=10, pady=5)

    # ── Refresh logic ────────────────────────────────────────────────

    def _start_refresh(self):
        def _loop():
            while True:
                try:
                    data = read_scores(self.scores_path)
                    self.root.after(0, lambda d=data: self._update(d))
                except Exception:
                    pass
                time.sleep(5)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def _update(self, data: list[dict]):
        now_utc = datetime.now(timezone.utc).strftime("%H:%M UTC")
        best_score, best_text, best_clr = 0, "No setup ready — scanning...", FG_DIM

        session = ""
        for i, row in enumerate(data[:6]):
            pair    = row.get("pair", "").replace("_USD", "").replace("_", "")
            sc_raw  = row.get("score", "0")
            sc      = int(sc_raw) if sc_raw.isdigit() else 0
            dirn    = row.get("direction", "--")
            strat   = row.get("strategy", "scanning")[:20]
            regime  = row.get("regime", "?")
            session = row.get("session", session)
            upd     = row.get("updated", "--")

            sc_clr  = score_color(sc)
            dir_clr = BUY_CLR if dirn == "BUY" else (SELL_CLR if dirn == "SELL" else FG_DIM)
            dir_txt = f"{'↑ BUY' if dirn=='BUY' else ('↓ SELL' if dirn=='SELL' else '-- ')}"

            r = self._rows[i]
            r["pair"].config(text=f" {pair}")
            r["score"].config(text=str(sc), fg=sc_clr)
            r["bar"].config(text=score_bar(sc), fg=sc_clr)
            r["dir"].config(text=dir_txt, fg=dir_clr)
            r["reg"].config(text=regime_badge(regime), fg=regime_color(regime))
            r["strat"].config(text=strat)
            r["time"].config(text=upd)

            if sc > best_score and dirn not in ("--", "NONE"):
                best_score = sc
                emoji = "✅" if sc >= 60 else "👁"
                action = "READY TO EXECUTE" if sc >= 60 else "WATCHING"
                best_text = f"  {emoji} BEST: {pair} {dir_txt}  {sc}/100 — {action}"
                best_clr  = sc_clr

        # Hide unused rows
        for i in range(len(data), 6):
            for lbl_key in ("pair", "score", "bar", "dir", "reg", "strat", "time"):
                self._rows[i][lbl_key].config(text="")

        # Update header session
        sess_upper = session.upper() if session else "SCANNING"
        self._lbl_session.config(text=f"{sess_upper} SESSION  |  {now_utc}  ")
        self._lbl_best.config(text=best_text, fg=best_clr)
        self._lbl_updated.config(text=f"Updated: {now_utc}  ")

    def run(self):
        self.root.mainloop()


def launch_panel_thread(scores_path: str) -> threading.Thread:
    """Start the panel in a background daemon thread."""
    def _run():
        try:
            panel = LivePanel(scores_path)
            panel.run()
        except Exception as e:
            print(f"[LivePanel] Could not open score panel: {e}")

    t = threading.Thread(target=_run, daemon=True, name="FxBotPanel")
    t.start()
    return t
