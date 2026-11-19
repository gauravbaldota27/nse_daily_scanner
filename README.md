# NSE Daily Scanner: Bullish & Bearish

A single-screen dashboard that scans a watchlist of NSE stocks on daily candles. It implements the six setups in *Coding_2.docx* with their exact numbers.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

The dashboard opens in your browser. Data comes from Yahoo Finance (free and delayed). Each symbol gets a `.NS` suffix automatically.

Run the rule tests with `python -m pytest -q`.

## Share link (daily HTML)

After the NSE close, GitHub Actions rebuilds a static page of the watchlist scan. Click any row to see that stock's daily chart (the same one the app shows), its trade plan, and its checklist:

**https://gauravbaldota27.github.io/nse_daily_scanner/**

Weekdays at 16:30 IST and 17:00 IST (Yahoo’s daily bar can lag). You can also run **Actions → Daily NSE scan → Run workflow**. Thresholds stay the spec defaults.

## What's on the screen

- **Top:** a stock picker, plus a count of stocks in each status across the watchlist.
- **Left:** the daily candlestick chart with EMA 9/20/50/200, the 20-day high/low, volume and its 20-day average, and past bull/bear signals (triangles). When a setup is confirmed, the chart also shows entry, stop, T1 and T2 lines. When a setup is waiting, it shows the watch level instead.
- **Middle:** the Bullish | Indicator | Actual | Bearish table, with a tick for every condition.
- **Right:** the signal status and the automatic trade plan (entry, stop, T1, T2, % distances, R:R, validity and signal date).
- **Bottom left:** scan results for the whole watchlist, sorted strongest first.
- **Bottom right:** a checklist of all six setups for the selected stock, with each one's score and the conditions it still lacks.

Every threshold can be changed in the sidebar. **Save** writes your values to `settings.json`, and **Reset to spec** restores the document's numbers.

## Decisions where the spec was open

| Topic | Rule used |
|---|---|
| R:R vs 1:2 minimum | Measured at **Target 2**. With the default 1×ATR stop and 2×ATR T2, this is exactly 1:2, so the setup is valid. If you change the multipliers so R:R at T2 falls below the minimum, the status becomes NO TRADE. |
| Status mapping | Breakout → **STRONG BULLISH**, Momentum → **BULLISH**, Pullback → **BULLISH PULLBACK**. The bearish side mirrors this. If more than one setup fires, the strongest wins. |
| Pullback volume | **Today's** volume < 20-day average volume. |
| 20-day average volume and 20-day high/low | Calculated from the **previous** 20 sessions, so today's candle isn't part of its own baseline. |
| WAIT FOR CONFIRMATION | Either every trend/indicator condition of a setup passes but its candle-confirmation conditions don't (close vs prev high/low or 20D level, RVOL, candle colour, body %), or the setup appears only on today's still-open candle. The watch level is the price the next daily close has to beat. |
| NO TRADE | R:R rejection, fewer than 202 candles of history, or bullish and bearish firing together. |
| Incomplete candle | Before 15:30 IST, today's candle is shown greyed on the chart and is **never** used for a confirmed signal. |
| RSI / ADX / ATR / DI | Wilder smoothing, seeded as in TradingView, on 5 years of history so EMA200 is fully warmed up. |
| Bollinger Bands | The spec lists the parameters but no rule uses them, so they're an optional chart overlay (sidebar). EMA 9 appears in the table only, because no rule uses it either. |

## Files

```
app.py                 dashboard (layout, chart, tables)
scanner/config.py      every default threshold + watchlist
scanner/indicators.py  RSI, ADX/DI, EMA, MACD, ATR, BB, RVOL, 20D levels
scanner/signals.py     the six setups, status logic, trade plan
scanner/data.py        Yahoo download, incomplete-candle split
scanner/engine.py      ties it together for each stock and the watchlist
scanner/chart.py       daily candlestick chart (used by the app and the share page)
scripts/build_report.py  static HTML for GitHub Pages
tests/test_signals.py  rule tests
```

## Limits

- Yahoo data is delayed and can occasionally lag or lack a symbol. Symbols that fail are listed under the scan table. NSE symbols that change after a corporate action need updating in the watchlist.
- This is a scanning aid, not trading advice. Check every signal on your broker's chart before acting.
