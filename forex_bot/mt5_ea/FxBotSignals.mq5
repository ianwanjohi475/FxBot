//+------------------------------------------------------------------+
//|  FxBotSignals.mq5  — Python FxBot Chart Visualiser v4.0        |
//|  - Score panel pinned OUTSIDE candles (top-right corner)        |
//|  - Only LATEST signal drawn on chart (clean)                    |
//|  - Historical signals: tiny dots only (no chart clutter)        |
//|  - TP1/2/3 lines colour-coded and clearly labelled              |
//+------------------------------------------------------------------+
#property copyright "FxBot"
#property version   "4.00"
#property strict

input int  RefreshSeconds = 5;
input bool ShowNews       = true;
input int  NewsHoursAhead = 48;
input int  PanelWidth     = 230;   // px from right edge

#define PFX  "FxBot_"
#define PPFX "FxBotP_"   // panel label prefix (deleted separately)

//+------------------------------------------------------------------+
int OnInit()
  {
   EventSetTimer(RefreshSeconds);
   DrawAll();
   return INIT_SUCCEEDED;
  }

void OnTimer()  { DrawAll(); }
void OnChartEvent(const int id, const long& lp, const double& dp, const string& sp)
  {
   if(id == CHARTEVENT_CHART_CHANGE) DrawAll();
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   ObjectsDeleteAll(0, PFX);
   ObjectsDeleteAll(0, PPFX);
   Comment("");
  }

//+------------------------------------------------------------------+
//  Helpers
//+------------------------------------------------------------------+
string NormSym(string s) { StringReplace(s, "_", ""); return s; }

string PipsStr(double entry, double level, string pair)
  {
   double pipSize = (StringFind(pair,"JPY")>=0 || StringFind(pair,"XAU")>=0) ? 0.01 : 0.0001;
   if(StringFind(pair,"US30")>=0 || StringFind(pair,"NAS")>=0) pipSize = 1.0;
   double pips = MathAbs(entry - level) / pipSize;
   return DoubleToString(pips, 0) + "p";
  }

string ScoreBar(double score)
  {
   int filled = (int)MathRound(score / 10.0);
   if(filled > 10) filled = 10;
   string bar = "";
   for(int i = 0; i < 10; i++) bar += (i < filled) ? "|" : ".";
   return bar;
  }

color ScoreColor(double score)
  {
   if(score >= 80) return clrLime;
   if(score >= 65) return clrYellow;
   if(score >= 50) return clrOrange;
   return clrRed;
  }

//+------------------------------------------------------------------+
//  Panel label helpers — pinned to TOP-RIGHT corner, outside chart
//+------------------------------------------------------------------+
void PanelLabel(string name, int line, string txt, color clr,
                int fontSize = 9, string font = "Courier New")
  {
   string full = PPFX + name;
   if(ObjectFind(0, full) < 0)
      ObjectCreate(0, full, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, full, OBJPROP_CORNER,     CORNER_RIGHT_UPPER);
   ObjectSetInteger(0, full, OBJPROP_XDISTANCE,  PanelWidth);
   ObjectSetInteger(0, full, OBJPROP_YDISTANCE,  6 + line * 15);
   ObjectSetString(0,  full, OBJPROP_TEXT,       txt);
   ObjectSetInteger(0, full, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, full, OBJPROP_FONTSIZE,   fontSize);
   ObjectSetString(0,  full, OBJPROP_FONT,       font);
   ObjectSetInteger(0, full, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, full, OBJPROP_HIDDEN,     true);
  }

void ClearPanel()
  {
   ObjectsDeleteAll(0, PPFX);
  }

//+------------------------------------------------------------------+
void MakeLine(string name, double price, color clr,
              ENUM_LINE_STYLE style, int width)
  {
   if(ObjectFind(0, name) >= 0) ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE,      style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH,      width);
   ObjectSetInteger(0, name, OBJPROP_BACK,       true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

void MakeText(string name, datetime t, double price,
              string txt, color clr, int sz)
  {
   if(ObjectFind(0, name) >= 0) ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_TEXT, 0, t, price);
   ObjectSetString(0,  name, OBJPROP_TEXT,       txt);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,   sz);
   ObjectSetString(0,  name, OBJPROP_FONT,       "Arial Bold");
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

//+------------------------------------------------------------------+
//  Main
//+------------------------------------------------------------------+
void DrawAll()
  {
   ObjectsDeleteAll(0, PFX);
   ClearPanel();
   DrawSignals();
   if(ShowNews) DrawNewsMarkers();
   ChartRedraw();
  }

//+------------------------------------------------------------------+
void DrawSignals()
  {
   string curSym = NormSym(Symbol());
   int fh = FileOpen("fxbot_signals.csv", FILE_READ | FILE_TXT | FILE_ANSI);
   if(fh == INVALID_HANDLE)
     {
      PanelLabel("H0",  0, "  FxBot Signal Panel v4.0  ", clrDimGray, 10);
      PanelLabel("H1",  1, StringFormat("  %s — waiting...", Symbol()), clrGray);
      PanelLabel("H2",  2, "  Run: python main.py       ", clrGray);
      return;
     }

   // ---- parse CSV -------------------------------------------------------
   bool   hdr        = true;
   int    drawn      = 0;
   int    maxHistory = 6;

   // store all matching rows
   string dirs[],  entries[], sls[], tp1s[], tp2s[], tp3s[];
   string strats[], scores[], times[];
   int    rowCount = 0;

   while(!FileIsEnding(fh) && rowCount < maxHistory)
     {
      string line = FileReadString(fh);
      if(hdr) { hdr = false; continue; }
      if(StringLen(line) < 10) continue;

      string p[];
      if(StringSplit(line, ',', p) < 10) continue;
      if(NormSym(p[0]) != curSym) continue;

      int r = rowCount;
      dirs[r]    = p[1];
      entries[r] = p[2];
      sls[r]     = p[3];
      tp1s[r]    = p[4];
      tp2s[r]    = p[5];
      tp3s[r]    = p[6];
      strats[r]  = p[7];
      scores[r]  = p[8];
      times[r]   = (StringLen(p[9]) > 4) ? StringSubstr(p[9], 0, 16) : p[9];
      rowCount++;
     }
   FileClose(fh);

   if(rowCount == 0)
     {
      PanelLabel("H0", 0, "  FxBot Signal Panel v4.0  ", clrDimGray, 10);
      PanelLabel("H1", 1, StringFormat("  %s — no signals yet", Symbol()), clrGray);
      PanelLabel("H2", 2, "  Next scan: candle close   ", clrGray);
      return;
     }

   // ---- draw LATEST signal on chart cleanly ----------------------------
   string dir0   = dirs[0];
   double entry0 = StringToDouble(entries[0]);
   double sl0    = StringToDouble(sls[0]);
   double tp1_0  = StringToDouble(tp1s[0]);
   double tp2_0  = StringToDouble(tp2s[0]);
   double tp3_0  = StringToDouble(tp3s[0]);
   double score0 = StringToDouble(scores[0]);
   datetime ts0  = StringToTime(times[0]);
   bool   isBuy0 = (dir0 == "BUY");
   color  sigClr = isBuy0 ? clrDodgerBlue : clrOrangeRed;

   // Arrow
   string arw = PFX + "ARW";
   ObjectCreate(0, arw, OBJ_ARROW, 0, ts0, isBuy0 ? sl0 - 8*_Point : sl0 + 8*_Point);
   ObjectSetInteger(0, arw, OBJPROP_ARROWCODE,  isBuy0 ? 241 : 242);
   ObjectSetInteger(0, arw, OBJPROP_COLOR,      sigClr);
   ObjectSetInteger(0, arw, OBJPROP_WIDTH,      4);
   ObjectSetInteger(0, arw, OBJPROP_SELECTABLE, false);

   // Entry line — solid, medium
   MakeLine(PFX+"ENT", entry0, sigClr, STYLE_SOLID, 2);
   MakeText(PFX+"ENT_L", ts0, entry0,
            "  ENTRY " + entries[0], sigClr, 9);

   // Risk zone (entry ↔ SL)
   datetime zEnd = ts0 + PeriodSeconds() * 60;
   ObjectCreate(0, PFX+"ZONE", OBJ_RECTANGLE, 0, ts0, entry0, zEnd, sl0);
   ObjectSetInteger(0, PFX+"ZONE", OBJPROP_COLOR, isBuy0 ? C'0,50,0' : C'60,0,0');
   ObjectSetInteger(0, PFX+"ZONE", OBJPROP_FILL,  true);
   ObjectSetInteger(0, PFX+"ZONE", OBJPROP_BACK,  true);
   ObjectSetInteger(0, PFX+"ZONE", OBJPROP_SELECTABLE, false);

   // SL — solid red, thick
   MakeLine(PFX+"SL", sl0, clrRed, STYLE_SOLID, 2);
   MakeText(PFX+"SL_L", ts0, sl0,
            "  SL " + sls[0] + "  (" + PipsStr(entry0, sl0, curSym) + ")", clrRed, 9);

   // TP1 — solid bright green, thickest
   if(tp1_0 > 0)
     {
      MakeLine(PFX+"T1", tp1_0, clrLime, STYLE_SOLID, 2);
      MakeText(PFX+"T1_L", ts0, tp1_0,
               "  TP1 " + tp1s[0] + "  (+" + PipsStr(entry0, tp1_0, curSym) + ")",
               clrLime, 9);
     }
   // TP2 — dashed medium green
   if(tp2_0 > 0)
     {
      MakeLine(PFX+"T2", tp2_0, clrMediumSpringGreen, STYLE_DASH, 2);
      MakeText(PFX+"T2_L", ts0, tp2_0,
               "  TP2 " + tp2s[0] + "  (+" + PipsStr(entry0, tp2_0, curSym) + ")",
               clrMediumSpringGreen, 9);
     }
   // TP3 — dotted light green
   if(tp3_0 > 0)
     {
      MakeLine(PFX+"T3", tp3_0, clrAquamarine, STYLE_DOT, 1);
      MakeText(PFX+"T3_L", ts0, tp3_0,
               "  TP3 " + tp3s[0] + "  (+" + PipsStr(entry0, tp3_0, curSym) + ")",
               clrAquamarine, 8);
     }

   // ---- Historical signals — tiny dots only (no chart text) ------------
   for(int i = 1; i < rowCount; i++)
     {
      datetime tsi = StringToTime(times[i]);
      double ei    = StringToDouble(entries[i]);
      bool buyI    = (dirs[i] == "BUY");
      string dot   = PFX + "DOT_" + IntegerToString(i);
      ObjectCreate(0, dot, OBJ_ARROW, 0, tsi, ei);
      ObjectSetInteger(0, dot, OBJPROP_ARROWCODE,  159);
      ObjectSetInteger(0, dot, OBJPROP_COLOR, buyI ? C'30,100,30' : C'100,30,30');
      ObjectSetInteger(0, dot, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, dot, OBJPROP_SELECTABLE, false);
     }

   // ---- Build corner panel — OUTSIDE the candle area -------------------
   int L = 0;
   string timeTag = StringLen(times[0]) > 10 ? StringSubstr(times[0], 11, 5) : times[0];
   string header  = StringFormat(" FxBot  %s  %s  %s ", Symbol(),
                                 isBuy0 ? "BUY ^" : "SELL v", timeTag);

   PanelLabel("HDR",  L++, header,  isBuy0 ? clrDodgerBlue : clrOrangeRed, 10, "Arial Bold");
   PanelLabel("SEP0", L++, StringFormat(" %s", strats[0]), clrDimGray);
   PanelLabel("SEP1", L++, " ─────────────────────────── ", clrDimGray);

   // Score gauge
   string bar       = ScoreBar(score0);
   color  scoreClr  = ScoreColor(score0);
   string scoreText = StringFormat(" Score  [%s] %s/100", bar, scores[0]);
   PanelLabel("SCR",  L++, scoreText, scoreClr, 10, "Courier New");
   PanelLabel("SEP2", L++, " ─────────────────────────── ", clrDimGray);

   // Signal details
   PanelLabel("ENT",  L++, StringFormat(" Entry  %s", entries[0]),  sigClr);
   PanelLabel("SL0",  L++, StringFormat(" SL     %s  -%s", sls[0],
              PipsStr(entry0, sl0, curSym)),   clrRed);
   if(tp1_0 > 0)
      PanelLabel("TP1",  L++, StringFormat(" TP1    %s  +%s", tp1s[0],
                 PipsStr(entry0, tp1_0, curSym)), clrLime);
   if(tp2_0 > 0)
      PanelLabel("TP2",  L++, StringFormat(" TP2    %s  +%s", tp2s[0],
                 PipsStr(entry0, tp2_0, curSym)), clrMediumSpringGreen);
   if(tp3_0 > 0)
      PanelLabel("TP3",  L++, StringFormat(" TP3    %s  +%s", tp3s[0],
                 PipsStr(entry0, tp3_0, curSym)), clrAquamarine);

   // History section
   PanelLabel("SEP3", L++, " ─────────────────────────── ", clrDimGray);
   PanelLabel("HIST", L++, " HISTORY:", clrDimGray);
   for(int i = 0; i < rowCount; i++)
     {
      string arrow   = (dirs[i] == "BUY") ? " ^ " : " v ";
      color  hClr    = (dirs[i] == "BUY") ? clrCornflowerBlue : clrSalmon;
      double sc      = StringToDouble(scores[i]);
      color  scClr   = ScoreColor(sc);
      string htag    = StringLen(times[i]) > 10 ? StringSubstr(times[i], 11, 5) : times[i];
      // print score in its own color using separate label per row part
      string htxt    = StringFormat("%s%s  %s  scr:", arrow, dirs[i], htag);
      PanelLabel("HR" + IntegerToString(i), L, htxt, hClr);
      PanelLabel("HS" + IntegerToString(i), L, StringFormat("%-39s%s", htxt, scores[i]), scClr);
      // Simpler: one combined line
      string hLine   = StringFormat("%s%s  %s  [%s]", arrow, dirs[i], htag, scores[i]);
      // delete and redo as single label
      ObjectDelete(0, PPFX + "HR" + IntegerToString(i));
      ObjectDelete(0, PPFX + "HS" + IntegerToString(i));
      PanelLabel("H" + IntegerToString(100+i), L++, hLine, hClr);
     }

   // Footer
   PanelLabel("SEP4", L++, " ─────────────────────────── ", clrDimGray);
   PanelLabel("FTR",  L++,
              StringFormat(" Updated: %s", TimeToString(TimeCurrent(), TIME_MINUTES)),
              clrDimGray, 8);
  }

//+------------------------------------------------------------------+
void DrawNewsMarkers()
  {
   int fh = FileOpen("fxbot_news.csv", FILE_READ | FILE_TXT | FILE_ANSI);
   if(fh == INVALID_HANDLE) return;

   bool hdr = true;
   datetime now     = TimeCurrent();
   datetime cutoff  = now + (datetime)(NewsHoursAhead * 3600);
   int      count   = 0;

   while(!FileIsEnding(fh))
     {
      string line = FileReadString(fh);
      if(hdr) { hdr = false; continue; }
      if(StringLen(line) < 5) continue;

      string p[];
      if(StringSplit(line, ',', p) < 4) continue;

      string   currency = p[0];
      string   impact   = p[1];
      string   evName   = p[2];
      datetime ts       = StringToTime(p[3]);

      if(ts == 0 || ts < now - 3600 || ts > cutoff) continue;

      color nClr  = (impact == "HIGH")   ? clrRed    :
                    (impact == "MEDIUM") ? clrOrange : clrGold;
      int   lW    = (impact == "HIGH")   ? 2 : 1;
      string id   = PFX + "NWS_" + currency + IntegerToString((int)ts);

      ObjectCreate(0, id+"_V", OBJ_VLINE, 0, ts, 0);
      ObjectSetInteger(0, id+"_V", OBJPROP_COLOR,      nClr);
      ObjectSetInteger(0, id+"_V", OBJPROP_STYLE,      STYLE_DOT);
      ObjectSetInteger(0, id+"_V", OBJPROP_WIDTH,      lW);
      ObjectSetInteger(0, id+"_V", OBJPROP_BACK,       true);
      ObjectSetInteger(0, id+"_V", OBJPROP_SELECTABLE, false);

      double hi  = ChartGetDouble(0, CHART_PRICE_MAX);
      double lo  = ChartGetDouble(0, CHART_PRICE_MIN);
      double lbY = hi - (hi - lo) * 0.04;
      string imp = (impact == "HIGH") ? "[!]" : (impact == "MEDIUM") ? "[~]" : "[ ]";
      string lbl = imp + " " + currency + ": " + evName;

      ObjectCreate(0, id+"_T", OBJ_TEXT, 0, ts, lbY);
      ObjectSetString(0,  id+"_T", OBJPROP_TEXT,       lbl);
      ObjectSetInteger(0, id+"_T", OBJPROP_COLOR,      nClr);
      ObjectSetInteger(0, id+"_T", OBJPROP_FONTSIZE,   8);
      ObjectSetString(0,  id+"_T", OBJPROP_FONT,       "Arial");
      ObjectSetDouble(0,  id+"_T", OBJPROP_ANGLE,      90.0);
      ObjectSetInteger(0, id+"_T", OBJPROP_ANCHOR,     ANCHOR_LEFT_LOWER);
      ObjectSetInteger(0, id+"_T", OBJPROP_SELECTABLE, false);
      count++;
     }
   FileClose(fh);
  }
//+------------------------------------------------------------------+
