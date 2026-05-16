//+------------------------------------------------------------------+
//|  FxBotSignals.mq5  — Python FxBot Chart Visualiser v3.0        |
//|  Shows: BUY/SELL arrows, SL/TP lines, risk zone, score bar,    |
//|         ForexFactory news markers, historical signals            |
//+------------------------------------------------------------------+
#property copyright "FxBot"
#property version   "3.00"
#property strict

input int  RefreshSeconds = 5;
input int  MaxSignals     = 8;      // Historical signals to display
input bool ShowZone       = true;   // Coloured entry-to-SL zone
input bool ShowArrows     = true;   // BUY/SELL arrow objects
input bool ShowNews       = true;   // ForexFactory news markers
input int  NewsHoursAhead = 48;     // Hours of news to display ahead

//--- object prefix
#define PFX "FxBot_"

//+------------------------------------------------------------------+
int OnInit()
  {
   EventSetTimer(RefreshSeconds);
   DrawAll();
   return(INIT_SUCCEEDED);
  }

void OnTimer()     { DrawAll(); }
void OnDeinit(const int reason)
  {
   EventKillTimer();
   ObjectsDeleteAll(0, PFX);
   Comment("");
  }

//+------------------------------------------------------------------+
string NormSym(string s) { StringReplace(s,"_",""); return s; }

string ScoreBar(double score)
  {
   int filled = (int)MathRound(score / 10.0);
   if(filled > 10) filled = 10;
   string bar = "[";
   for(int i=0;i<10;i++)
      bar += (i < filled) ? "#" : "-";
   bar += "] " + DoubleToString(score,0) + "/100";
   return bar;
  }

//+------------------------------------------------------------------+
void DrawAll()
  {
   ObjectsDeleteAll(0, PFX);
   DrawSignals();
   if(ShowNews) DrawNewsMarkers();
   ChartRedraw();
  }

//+------------------------------------------------------------------+
void DrawSignals()
  {
   string curSym = NormSym(Symbol());
   int fh = FileOpen("fxbot_signals.csv", FILE_READ|FILE_TXT|FILE_ANSI);
   if(fh == INVALID_HANDLE)
     {
      ShowPanel(
         "=== FxBot Signal Viewer ===\n"
         "  Waiting for Python bot signals...\n"
         "  Run:  python main.py\n"
         "===========================",
         clrYellow);
      return;
     }

   bool   hdr        = true;
   int    drawn      = 0;
   string latestLine = "";
   string newsPanel  = "";

   while(!FileIsEnding(fh) && drawn < MaxSignals)
     {
      string line = FileReadString(fh);
      if(hdr){ hdr = false; continue; }
      if(StringLen(line) < 15) continue;

      string p[];
      if(StringSplit(line,',',p) < 10) continue;

      string pair = NormSym(p[0]);
      if(pair != curSym) continue;

      string   dir   = p[1];
      double   entry = StringToDouble(p[2]);
      double   sl    = StringToDouble(p[3]);
      double   tp1   = StringToDouble(p[4]);
      double   tp2   = StringToDouble(p[5]);
      double   tp3   = StringToDouble(p[6]);
      string   strat = p[7];
      double   score = StringToDouble(p[8]);
      datetime ts    = StringToTime(p[9]);

      bool   isBuy  = (dir == "BUY");
      bool   isNew  = (drawn == 0);       // freshest signal
      color  eClr   = isBuy ? (isNew ? clrLime : clrMediumSeaGreen)
                             : (isNew ? clrRed  : clrIndianRed);
      color  slClr  = clrTomato;
      color  tpClr  = isBuy ? clrDodgerBlue : clrDeepSkyBlue;
      string id     = pair + IntegerToString((int)ts) + IntegerToString(drawn);

      //--- Arrow ---
      if(ShowArrows)
        {
         string arrowName = PFX "ARW_" + id;
         double arrowPrice = isBuy ? (sl - 5*_Point) : (sl + 5*_Point);
         ObjectCreate(0, arrowName, OBJ_ARROW, 0, ts, arrowPrice);
         ObjectSetInteger(0, arrowName, OBJPROP_ARROWCODE,
                          isBuy ? 233 : 234);
         ObjectSetInteger(0, arrowName, OBJPROP_COLOR, eClr);
         ObjectSetInteger(0, arrowName, OBJPROP_WIDTH, isNew ? 4 : 2);
         ObjectSetInteger(0, arrowName, OBJPROP_SELECTABLE, false);
        }

      //--- Entry line ---
      MakeLine(PFX "ENT_"+id, entry, eClr, STYLE_SOLID, isNew ? 3 : 1);

      //--- Risk zone rectangle (entry <-> SL) ---
      if(ShowZone && isNew)
        {
         datetime t2 = ts + PeriodSeconds()*80;
         string rName = PFX "ZONE_"+id;
         ObjectCreate(0, rName, OBJ_RECTANGLE, 0, ts, entry, t2, sl);
         ObjectSetInteger(0, rName, OBJPROP_COLOR, isBuy ? clrDarkGreen : clrDarkRed);
         ObjectSetInteger(0, rName, OBJPROP_FILL,  true);
         ObjectSetInteger(0, rName, OBJPROP_BACK,  true);
         ObjectSetInteger(0, rName, OBJPROP_SELECTABLE, false);
        }

      //--- Stop Loss ---
      MakeLine(PFX "SL_"+id, sl, slClr, STYLE_DASH, isNew ? 2 : 1);
      if(isNew)
         MakeText(PFX "SLL_"+id, ts, sl,
                  "  X SL " + DoubleToString(sl,_Digits), slClr, 9);

      //--- Take Profits ---
      if(tp1 > 0)
        {
         MakeLine(PFX "T1_"+id, tp1, tpClr, STYLE_DOT, isNew ? 2 : 1);
         if(isNew)
            MakeText(PFX "T1L_"+id, ts, tp1,
                     "  TP1 "+DoubleToString(tp1,_Digits), tpClr, 8);
        }
      if(tp2 > 0)
        {
         MakeLine(PFX "T2_"+id, tp2, clrDeepSkyBlue, STYLE_DOT, 1);
         if(isNew)
            MakeText(PFX "T2L_"+id, ts, tp2,
                     "  TP2 "+DoubleToString(tp2,_Digits), clrDeepSkyBlue, 8);
        }
      if(tp3 > 0)
        {
         MakeLine(PFX "T3_"+id, tp3, clrAqua, STYLE_DOT, 1);
         if(isNew)
            MakeText(PFX "T3L_"+id, ts, tp3,
                     "  TP3 "+DoubleToString(tp3,_Digits), clrAqua, 8);
        }

      //--- Direction label near entry ---
      if(isNew || drawn < 3)
        {
         string arrow = isBuy ? "^ BUY " : "v SELL";
         string lbl = "  " + arrow + "  " + strat +
                      "  [" + DoubleToString(score,0) + "/100]";
         MakeText(PFX "LBL_"+id, ts, entry, lbl, eClr, isNew ? 11 : 9);
        }

      //--- Historical signal marker (small dot for older signals) ---
      if(!isNew)
        {
         string dotName = PFX "HIST_"+id;
         ObjectCreate(0, dotName, OBJ_ARROW, 0, ts, entry);
         ObjectSetInteger(0, dotName, OBJPROP_ARROWCODE, 159); // small circle
         ObjectSetInteger(0, dotName, OBJPROP_COLOR, eClr);
         ObjectSetInteger(0, dotName, OBJPROP_WIDTH, 1);
         ObjectSetInteger(0, dotName, OBJPROP_SELECTABLE, false);
        }

      if(drawn == 0)
         latestLine = dir + "|" + DoubleToString(entry,_Digits) + "|" +
                      DoubleToString(sl,_Digits) + "|" +
                      DoubleToString(tp1,_Digits) + "|" +
                      DoubleToString(tp2,_Digits) + "|" +
                      DoubleToString(tp3,_Digits) + "|" +
                      strat + "|" + DoubleToString(score,0) + "|" +
                      TimeToString(ts, TIME_MINUTES);
      drawn++;
     }
   FileClose(fh);

   //--- Build info panel ---
   if(drawn > 0)
     {
      string p2[];
      StringSplit(latestLine, '|', p2);
      string dirStr = (StringLen(p2[0])>0) ? p2[0] : "?";
      string arrow  = (dirStr == "BUY") ? "^ BUY  " : "v SELL ";
      string bar    = (StringLen(p2[7])>0) ? ScoreBar(StringToDouble(p2[7])) : "?";

      string panel =
         "=========================================\n"
         "   FxBot Signal Viewer v3.0\n"
         "=========================================\n"
         " Pair   : " + Symbol() + "\n"
         " Signal : " + arrow + "\n"
         " Entry  : " + (StringLen(p2[1])>0 ? p2[1] : "?") + "\n"
         " SL     : " + (StringLen(p2[2])>0 ? p2[2] : "?") + "\n"
         " TP1    : " + (StringLen(p2[3])>0 ? p2[3] : "?") + "\n"
         " TP2    : " + (StringLen(p2[4])>0 ? p2[4] : "?") + "\n"
         " TP3    : " + (StringLen(p2[5])>0 ? p2[5] : "?") + "\n"
         " Strat  : " + (StringLen(p2[6])>0 ? p2[6] : "?") + "\n"
         " Score  : " + bar + "\n"
         " Time   : " + (StringLen(p2[8])>0 ? p2[8] : "?") + "\n"
         " History: " + IntegerToString(drawn) + " signal(s)\n"
         "=========================================";

      ShowPanel(panel + newsPanel, clrWhite);
     }
   else
     {
      ShowPanel(
         "=========================================\n"
         "   FxBot Signal Viewer v3.0\n"
         "=========================================\n"
         " No signals for " + Symbol() + " yet.\n"
         " Bot analyses every 60 seconds.\n"
         "=========================================\n" + newsPanel,
         clrGray);
     }
  }

//+------------------------------------------------------------------+
void DrawNewsMarkers()
  {
   int fh = FileOpen("fxbot_news.csv", FILE_READ|FILE_TXT|FILE_ANSI);
   if(fh == INVALID_HANDLE) return;

   bool hdr      = true;
   int  count    = 0;
   string newsSummary = "\n-----------------------------------------\n"
                        " UPCOMING NEWS (next " +
                        IntegerToString(NewsHoursAhead) + "h):\n";

   datetime now = TimeCurrent();
   datetime cutoff = now + (datetime)(NewsHoursAhead * 3600);

   while(!FileIsEnding(fh))
     {
      string line = FileReadString(fh);
      if(hdr){ hdr = false; continue; }
      if(StringLen(line) < 5) continue;

      string p[];
      if(StringSplit(line, ',', p) < 4) continue;

      string   currency  = p[0];
      string   impact    = p[1];
      string   eventName = p[2];
      datetime ts        = StringToTime(p[3]);
      if(ts == 0) continue;
      if(ts < now - 3600 || ts > cutoff) continue; // skip past/far events

      color nClr  = (impact == "HIGH")   ? clrRed    :
                    (impact == "MEDIUM") ? clrOrange : clrGold;
      int   lWidth = (impact == "HIGH")  ? 2 : 1;

      string id = PFX "NWS_" + currency + IntegerToString((int)ts);

      //--- Vertical line at news time ---
      string vName = id + "_VL";
      ObjectCreate(0, vName, OBJ_VLINE, 0, ts, 0);
      ObjectSetInteger(0, vName, OBJPROP_COLOR,      nClr);
      ObjectSetInteger(0, vName, OBJPROP_STYLE,      STYLE_DOT);
      ObjectSetInteger(0, vName, OBJPROP_WIDTH,      lWidth);
      ObjectSetInteger(0, vName, OBJPROP_BACK,       true);
      ObjectSetInteger(0, vName, OBJPROP_SELECTABLE, false);

      //--- Text label on the line ---
      double chartHigh = ChartGetDouble(0, CHART_PRICE_MAX);
      double chartLow  = ChartGetDouble(0, CHART_PRICE_MIN);
      double labelY    = chartHigh - (chartHigh - chartLow) * 0.04;

      string impMark = (impact == "HIGH") ? "[!!!]" :
                       (impact == "MEDIUM") ? "[!] " : "[ ] ";
      string lbl = impMark + " " + currency + ": " + eventName;

      string tName = id + "_TXT";
      ObjectCreate(0, tName, OBJ_TEXT, 0, ts, labelY);
      ObjectSetString(0,  tName, OBJPROP_TEXT,       lbl);
      ObjectSetInteger(0, tName, OBJPROP_COLOR,      nClr);
      ObjectSetInteger(0, tName, OBJPROP_FONTSIZE,   8);
      ObjectSetString(0,  tName, OBJPROP_FONT,       "Arial Bold");
      ObjectSetDouble(0,  tName, OBJPROP_ANGLE,      90.0);
      ObjectSetInteger(0, tName, OBJPROP_ANCHOR,     ANCHOR_LEFT_LOWER);
      ObjectSetInteger(0, tName, OBJPROP_SELECTABLE, false);

      //--- Add to panel summary ---
      string timeStr = TimeToString(ts, TIME_DATE|TIME_MINUTES);
      newsSummary += " " + impMark + " " + currency + ": " + eventName +
                     "  " + timeStr + "\n";
      count++;
     }
   FileClose(fh);

   if(count == 0)
      newsSummary += " No high-impact events in window.\n";
   newsSummary += "-----------------------------------------";

   //--- Append news to existing Comment ---
   string existing = ChartGetString(0, CHART_COMMENT);
   if(StringLen(existing) > 0)
      Comment(existing + newsSummary);
   else
      Comment(newsSummary);
  }

//+------------------------------------------------------------------+
void ShowPanel(string txt, color clr)
  {
   Comment(txt);
  }

void MakeLine(string name, double price, color clr, ENUM_LINE_STYLE style, int width)
  {
   if(ObjectFind(0,name) >= 0) ObjectDelete(0,name);
   ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE,      style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH,      width);
   ObjectSetInteger(0, name, OBJPROP_BACK,       true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

void MakeText(string name, datetime t, double price, string txt, color clr, int sz)
  {
   if(ObjectFind(0,name) >= 0) ObjectDelete(0,name);
   ObjectCreate(0, name, OBJ_TEXT, 0, t, price);
   ObjectSetString(0,  name, OBJPROP_TEXT,       txt);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,   sz);
   ObjectSetString(0,  name, OBJPROP_FONT,       "Arial Bold");
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }
//+------------------------------------------------------------------+
