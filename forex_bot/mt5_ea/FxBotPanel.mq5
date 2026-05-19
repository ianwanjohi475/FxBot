//+------------------------------------------------------------------+
//|  FxBotPanel.mq5  — FxBot Live Score Dashboard (Sub-Window)     |
//|  Attach to ANY chart. Shows live scores for all 5 pairs.        |
//|  Reads fxbot_scores.csv written by Python bot every 15 seconds. |
//|                                                                  |
//|  HOW TO USE:                                                     |
//|  1. In MT5 Navigator → Indicators → FxBotPanel                  |
//|  2. Drag onto any chart — appears as sub-panel BELOW candles    |
//|  3. No config needed                                             |
//+------------------------------------------------------------------+
#property copyright "FxBot"
#property version   "1.00"
#property strict
#property indicator_separate_window
#property indicator_minimum   0
#property indicator_maximum   105
#property indicator_plots     0
#property indicator_height    175

#define PFXD "FxBotDash_"

string g_sn    = "FxBotPanel";
int    g_win   = -1;

//+------------------------------------------------------------------+
int OnInit()
  {
   IndicatorSetString(INDICATOR_SHORTNAME, g_sn);
   EventSetTimer(5);
   // window index resolved after first draw
   DrawDash();
   return INIT_SUCCEEDED;
  }

void OnTimer()          { DrawDash(); }
void OnChartEvent(const int id, const long& lp, const double& dp, const string& sp)
  { if(id == CHARTEVENT_CHART_CHANGE) DrawDash(); }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   ObjectsDeleteAll(0, PFXD);
  }

int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[],
                const double &close[], const long &volume[],
                const long &tick_volume[], const int &spread[])
  { return rates_total; }

//+------------------------------------------------------------------+
//  Layout helpers
//+------------------------------------------------------------------+
int ResolveWindow()
  {
   for(int w = 1; w < ChartGetInteger(0, CHART_WINDOWS_TOTAL); w++)
      if(ChartGetString(0, CHART_INDICATOR_SHORTNAME(w, 0)) == g_sn ||
         StringFind(ChartGetString(0, CHART_INDICATOR_SHORTNAME(w, 0)), g_sn) >= 0)
         return w;
   return 1;  // fallback: first sub-window
  }

void DLabel(string key, int x, int y, string txt, color clr,
            int sz = 9, string font = "Courier New",
            ENUM_BASE_CORNER corner = CORNER_LEFT_UPPER)
  {
   string n = PFXD + key;
   if(ObjectFind(0, n) < 0)
      ObjectCreate(0, n, OBJ_LABEL, g_win, 0, 0);
   ObjectSetInteger(0, n, OBJPROP_CORNER,     corner);
   ObjectSetInteger(0, n, OBJPROP_XDISTANCE,  x);
   ObjectSetInteger(0, n, OBJPROP_YDISTANCE,  y);
   ObjectSetString(0,  n, OBJPROP_TEXT,       txt);
   ObjectSetInteger(0, n, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, n, OBJPROP_FONTSIZE,   sz);
   ObjectSetString(0,  n, OBJPROP_FONT,       font);
   ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, n, OBJPROP_HIDDEN,     true);
  }

string ScoreBar(int score)
  {
   int f = score / 10;
   if(f > 10) f = 10;
   string b = "";
   for(int i = 0; i < 10; i++) b += (i < f) ? (char)9608 : (char)9617;
   return b;
  }

color ScoreClr(int score)
  {
   if(score >= 75) return clrLime;
   if(score >= 60) return clrYellow;
   if(score >= 45) return clrOrange;
   return clrDimGray;
  }

string DirArrow(string dir)
  {
   if(dir == "BUY")  return " ^ BUY ";
   if(dir == "SELL") return " v SELL";
   return "  --   ";
  }

color DirClr(string dir)
  {
   if(dir == "BUY")  return clrDodgerBlue;
   if(dir == "SELL") return clrOrangeRed;
   return clrDimGray;
  }

string RegimeBadge(string regime)
  {
   if(regime == "trending")  return "[TREND]  ";
   if(regime == "ranging")   return "[RANGE]  ";
   if(regime == "volatile")  return "[VOLAT]  ";
   return "[?????]  ";
  }

color RegimeClr(string regime)
  {
   if(regime == "trending")  return clrCornflowerBlue;
   if(regime == "ranging")   return clrMediumOrchid;
   if(regime == "volatile")  return clrOrange;
   return clrDimGray;
  }

//+------------------------------------------------------------------+
void DrawDash()
  {
   g_win = ResolveWindow();
   ObjectsDeleteAll(0, PFXD);

   // ── Read scores CSV ─────────────────────────────────────────────
   int fh = FileOpen("fxbot_scores.csv", FILE_READ | FILE_TXT | FILE_ANSI);

   // Column widths (pixels, monospace 9pt ≈ 7px per char)
   int xPair  = 6;
   int xBar   = 80;
   int xScore = 165;
   int xDir   = 200;
   int xReg   = 255;
   int xStrat = 330;
   int xTime  = 490;
   int rowH   = 18;
   int yStart = 8;

   // ── Header ──────────────────────────────────────────────────────
   string hdr = "  FxBot Live Score Dashboard";
   DLabel("HDR", xPair, yStart, hdr, clrWhite, 10, "Arial Bold");

   if(fh == INVALID_HANDLE)
     {
      DLabel("W1", xPair, yStart + rowH,     "  Python bot not running — start main.py", clrGray);
      DLabel("W2", xPair, yStart + rowH * 2, "  Scores update every 15 seconds", clrDimGray);
      ChartRedraw();
      return;
     }

   string session   = "";
   string updated   = TimeToString(TimeCurrent(), TIME_MINUTES);
   bool   hdrLine   = true;
   int    row       = 0;
   string bestPair  = "", bestDir = "NONE";
   int    bestScore = 0;

   // Column headers
   int yCol = yStart + rowH + 3;
   DLabel("CH_pair",  xPair,  yCol, "PAIR    ", clrDimGray, 8, "Courier New");
   DLabel("CH_bar",   xBar,   yCol, "SCORE BAR      ", clrDimGray, 8, "Courier New");
   DLabel("CH_sc",    xScore, yCol, "SC ", clrDimGray, 8, "Courier New");
   DLabel("CH_dir",   xDir,   yCol, "DIR   ", clrDimGray, 8, "Courier New");
   DLabel("CH_reg",   xReg,   yCol, "REGIME   ", clrDimGray, 8, "Courier New");
   DLabel("CH_strat", xStrat, yCol, "STRATEGY       ", clrDimGray, 8, "Courier New");
   DLabel("CH_time",  xTime,  yCol, "TIME", clrDimGray, 8, "Courier New");

   // Separator
   DLabel("SEP0", xPair, yCol + 13,
          "────────────────────────────────────────────────────────────────────────",
          clrDimGray, 8, "Courier New");

   while(!FileIsEnding(fh))
     {
      string line = FileReadString(fh);
      if(hdrLine) { hdrLine = false; continue; }
      if(StringLen(line) < 5) continue;

      string p[];
      if(StringSplit(line, ',', p) < 7) continue;

      string pair    = p[0];
      int    score   = (int)StringToInteger(p[1]);
      string dir     = p[2];
      string strat   = p[3];
      string regime  = p[4];
      session        = p[5];
      string timeStr = p[6];

      // Display name: strip _USD suffix
      string dName = pair;
      StringReplace(dName, "_USD", "");
      StringReplace(dName, "_", "");

      int    y      = yStart + rowH * 2 + 16 + row * rowH;
      int    sc     = score;
      color  scClr  = ScoreClr(sc);
      color  dClr   = DirClr(dir);
      color  rClr   = RegimeClr(regime);

      // Pair name
      DLabel("P_"+IntegerToString(row), xPair, y,
             StringFormat("%-7s", dName), clrWhite, 9, "Courier New");

      // Score bar (coloured)
      DLabel("B_"+IntegerToString(row), xBar, y,
             ScoreBar(sc), scClr, 9, "Courier New");

      // Score number
      DLabel("S_"+IntegerToString(row), xScore, y,
             StringFormat("%3d", sc), scClr, 9, "Courier New");

      // Direction
      DLabel("D_"+IntegerToString(row), xDir, y,
             DirArrow(dir), dClr, 9, "Courier New");

      // Regime badge
      DLabel("R_"+IntegerToString(row), xReg, y,
             RegimeBadge(regime), rClr, 8, "Courier New");

      // Strategy (truncate)
      string stratShort = strat;
      if(StringLen(stratShort) > 18) stratShort = StringSubstr(stratShort, 0, 18);
      DLabel("T_"+IntegerToString(row), xStrat, y,
             StringFormat("%-18s", stratShort), clrDimGray, 8, "Courier New");

      // Time
      DLabel("U_"+IntegerToString(row), xTime, y,
             timeStr, clrDimGray, 8, "Courier New");

      // Track best
      if(sc > bestScore && dir != "NONE" && dir != "--")
        {
         bestScore = sc;
         bestPair  = dName;
         bestDir   = dir;
        }

      row++;
     }
   FileClose(fh);

   // ── Best setup + session footer ─────────────────────────────────
   int yFoot = yStart + rowH * 2 + 16 + row * rowH + 5;
   DLabel("FSEP", xPair, yFoot,
          "────────────────────────────────────────────────────────────────────────",
          clrDimGray, 8, "Courier New");
   yFoot += 12;

   string sessUpper = session;
   StringToUpper(sessUpper);

   if(bestScore >= 60)
     {
      string bestTxt = StringFormat(" BEST SETUP: %s %s  Score: %d/100  [READY]",
                                    bestPair, bestDir, bestScore);
      DLabel("BEST", xPair, yFoot, bestTxt, clrLime, 9, "Arial Bold");
     }
   else if(bestScore >= 45)
     {
      string bestTxt = StringFormat(" BUILDING: %s %s  Score: %d/100  [WATCHING]",
                                    bestPair, bestDir, bestScore);
      DLabel("BEST", xPair, yFoot, bestTxt, clrYellow, 9, "Arial Bold");
     }
   else
     {
      DLabel("BEST", xPair, yFoot,
             " No setup ready — scanning for pattern...", clrDimGray, 9, "Arial Bold");
     }

   // Session + timestamp
   string footRight = StringFormat("Session: %s   Updated: %s", sessUpper, updated);
   DLabel("SESS", 0, yFoot, footRight, clrDimGray, 8, "Courier New", CORNER_RIGHT_UPPER);

   // Update header with session info
   DLabel("HDR", xPair, yStart,
          StringFormat("  FxBot Live Dashboard   |  %s Session  |  %s UTC", sessUpper, updated),
          clrWhite, 10, "Arial Bold");

   ChartRedraw();
  }
//+------------------------------------------------------------------+
