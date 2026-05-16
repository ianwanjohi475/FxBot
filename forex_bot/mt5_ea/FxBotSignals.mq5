//+------------------------------------------------------------------+
//|  FxBotSignals.mq5                                                |
//|  Reads signals from the Python FxBot and draws them on the chart |
//|  Entry line, Stop Loss, TP1/TP2/TP3, strategy name & score       |
//+------------------------------------------------------------------+
#property copyright "FxBot"
#property version   "1.00"
#property strict

input int    RefreshSeconds = 5;    // How often to check for new signals
input int    MaxSignals     = 20;   // Maximum signals to show per chart
input bool   ShowAllPairs   = false; // Show signals for all pairs (not just this chart)

int OnInit()
  {
   EventSetTimer(RefreshSeconds);
   DrawSignals();
   Print("FxBot Signal Viewer loaded. Checking fxbot_signals.csv every ",
         RefreshSeconds, "s");
   return(INIT_SUCCEEDED);
  }

void OnTimer()    { DrawSignals(); }
void OnDeinit(const int reason)
  {
   EventKillTimer();
   ObjectsDeleteAll(0, "FxBot_");
   Comment("");
  }

//--- Strip underscore so "XAU_USD" matches "XAUUSD"
string NormSym(string s)
  {
   StringReplace(s, "_", "");
   return s;
  }

void DrawSignals()
  {
   string curSym = NormSym(Symbol());

   int fh = FileOpen("fxbot_signals.csv",
                     FILE_READ | FILE_TXT | FILE_ANSI);
   if(fh == INVALID_HANDLE)
     {
      Comment("FxBot: Waiting for signals...\n"
              "Start python main.py to generate signals.");
      return;
     }

   ObjectsDeleteAll(0, "FxBot_");

   bool   header = true;
   int    drawn  = 0;

   while(!FileIsEnding(fh) && drawn < MaxSignals)
     {
      string line = FileReadString(fh);
      if(header) { header = false; continue; }
      if(StringLen(line) < 15) continue;

      // Parse: pair,direction,entry,sl,tp1,tp2,tp3,strategy,score,timestamp
      string p[];
      if(StringSplit(line, ',', p) < 10) continue;

      string pair = NormSym(p[0]);
      if(!ShowAllPairs && pair != curSym) continue;

      string   dir      = p[1];
      double   entry    = StringToDouble(p[2]);
      double   sl       = StringToDouble(p[3]);
      double   tp1      = StringToDouble(p[4]);
      double   tp2      = StringToDouble(p[5]);
      double   tp3      = StringToDouble(p[6]);
      string   strategy = p[7];
      double   score    = StringToDouble(p[8]);
      datetime ts       = StringToTime(p[9]);   // "YYYY.MM.DD HH:MM:SS"

      color buyCol  = clrLime;
      color sellCol = clrTomato;
      color eCol    = (dir == "BUY") ? buyCol : sellCol;
      string id     = pair + IntegerToString((int)ts) + IntegerToString(drawn);

      // ---- Entry ----
      MakeLine("FxBot_E_" + id, entry, eCol, STYLE_SOLID, 2);
      MakeText("FxBot_EL_" + id, ts, entry,
               (dir=="BUY" ? "▲ " : "▼ ") + dir +
               " @ " + DoubleToString(entry, _Digits) +
               "  [" + strategy + "  Score:" + DoubleToString(score,0) + "]",
               eCol, 10);

      // ---- Stop Loss ----
      MakeLine("FxBot_SL_" + id, sl, clrRed, STYLE_DASH, 1);
      MakeText("FxBot_SLL_" + id, ts, sl,
               "SL: " + DoubleToString(sl, _Digits), clrRed, 8);

      // ---- Take Profits ----
      color tp1c = clrDodgerBlue;
      color tp2c = clrDeepSkyBlue;
      color tp3c = clrAqua;
      if(tp1 > 0)
        {
         MakeLine("FxBot_T1_" + id, tp1, tp1c, STYLE_DOT, 1);
         MakeText("FxBot_T1L_" + id, ts, tp1,
                  "TP1: " + DoubleToString(tp1, _Digits), tp1c, 8);
        }
      if(tp2 > 0)
        {
         MakeLine("FxBot_T2_" + id, tp2, tp2c, STYLE_DOT, 1);
         MakeText("FxBot_T2L_" + id, ts, tp2,
                  "TP2: " + DoubleToString(tp2, _Digits), tp2c, 8);
        }
      if(tp3 > 0)
        {
         MakeLine("FxBot_T3_" + id, tp3, tp3c, STYLE_DOT, 1);
         MakeText("FxBot_T3L_" + id, ts, tp3,
                  "TP3: " + DoubleToString(tp3, _Digits), tp3c, 8);
        }

      drawn++;
     }

   FileClose(fh);

   if(drawn > 0)
      Comment("FxBot Signal Viewer  |  " + Symbol() +
              "  |  Signals: " + IntegerToString(drawn) +
              "  |  Updated: " + TimeToString(TimeCurrent(), TIME_MINUTES));
   else
      Comment("FxBot: No signals for " + Symbol() + " yet.\n"
              "The bot is running and analysing — signals appear here when found.");
  }

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

void MakeText(string name, datetime t, double price, string txt,
              color clr, int fontSize)
  {
   if(ObjectFind(0, name) >= 0) ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_TEXT, 0, t, price);
   ObjectSetString(0, name,  OBJPROP_TEXT,      txt);
   ObjectSetInteger(0, name, OBJPROP_COLOR,     clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,  fontSize);
   ObjectSetString(0, name,  OBJPROP_FONT,      "Arial Bold");
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE,false);
  }
//+------------------------------------------------------------------+
