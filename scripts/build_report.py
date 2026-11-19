"""Build a static HTML scan of the default watchlist for GitHub Pages.

Uses the same engine and DEFAULTS as the Streamlit app. Thresholds are not
changed here.
"""

from __future__ import annotations

import json
import sys
import time
from html import escape
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scanner import config, data as data_mod  # noqa: E402
from scanner.engine import analyse, summary_table  # noqa: E402
from scanner.signals import SETUP_LABEL, STATUS_COLOR, indicator_rows  # noqa: E402

OUT = ROOT / "site" / "index.html"


def _fmt(v, spec):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return spec.format(float(v))


def _money(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    return f"₹{float(x):,.2f}"


def _download_with_retry(symbols, attempts=4):
    last_err = None
    for i in range(attempts):
        try:
            frames, failed = data_mod.download(symbols)
            if frames:
                return frames, failed
            last_err = RuntimeError("Yahoo returned no rows")
        except Exception as exc:  # network / Yahoo
            last_err = exc
        time.sleep(8 * (i + 1))
    raise last_err


def _details(res, settings):
    ev = res.ev
    last = res.ind.iloc[-1] if len(res.ind) else None
    plan = ev.plan
    plan_rows = []
    if plan is not None:
        sgn = 1 if plan.direction == "LONG" else -1
        plan_rows = [
            ("Direction", plan.direction),
            ("Setup", plan.setup.title()),
            ("Entry (daily close)", _money(plan.entry)),
            ("Stop loss", f"{_money(plan.stop)} ({-sgn * plan.pct_to_stop:+.2f}%)"),
            ("Target 1", f"{_money(plan.t1)} ({sgn * plan.pct_to_t1:+.2f}%)"),
            ("Target 2", f"{_money(plan.t2)} ({sgn * plan.pct_to_t2:+.2f}%)"),
            ("Risk : Reward (at T2)", f"1 : {plan.rr:.2f}"),
            ("Setup validity", "VALID" if plan.valid else
             f"REJECTED (min 1:{settings['trade']['min_rr']:g})"),
            ("Signal date", f"{plan.signal_date:%d %b %Y}"),
        ]
    elif last is not None:
        plan_rows = [("Last close", _money(last["Close"])),
                     ("ATR (14)", _money(last["atr"]) if pd.notna(last["atr"]) else "—")]
        if ev.watch_level is not None and ev.waiting_for:
            word = "above" if ev.waiting_for.startswith("bull") else "below"
            plan_rows.append(("Needs next daily close", f"{word} {_money(ev.watch_level)}"))
        if ev.candle_date is not None:
            plan_rows.append(("Candle evaluated", f"{ev.candle_date:%d %b %Y}"))

    conds = []
    if last is not None and ev.setups:
        for r in indicator_rows(last, settings):
            conds.append(r)

    checklist = []
    for k in ["bull_breakout", "bull_momentum", "bull_pullback",
              "bear_breakdown", "bear_momentum", "bear_pullback"]:
        sr = ev.setups.get(k)
        if sr is None:
            continue
        checklist.append({
            "key": k,
            "label": SETUP_LABEL[k],
            "score": sr.score,
            "passed": sr.passed,
            "missing": "All conditions met" if sr.passed else ", ".join(sr.failing),
        })

    return {
        "symbol": res.symbol,
        "status": ev.status,
        "reason": ev.reason,
        "plan_rows": plan_rows,
        "conds": conds,
        "checklist": checklist,
    }


def _table_rows(table: pd.DataFrame) -> list:
    rows = []
    for rec in table.to_dict(orient="records"):
        candle = rec.get("Candle")
        if candle is not None and not pd.isna(candle):
            candle_s = pd.Timestamp(candle).strftime("%d %b")
        else:
            candle_s = ""
        rows.append({
            "Symbol": rec["Symbol"],
            "Status": rec["Status"],
            "Setup": rec["Setup"] or "",
            "Close": _fmt(rec["Close"], "{:,.2f}"),
            "Chg %": _fmt(rec["Chg %"], "{:+.2f}"),
            "RSI": _fmt(rec["RSI"], "{:.1f}"),
            "ADX": _fmt(rec["ADX"], "{:.1f}"),
            "RVOL": _fmt(rec["RVOL"], "{:.2f}"),
            "Entry": _fmt(rec["Entry"], "{:,.2f}"),
            "Stop": _fmt(rec["Stop"], "{:,.2f}"),
            "T1": _fmt(rec["T1"], "{:,.2f}"),
            "T2": _fmt(rec["T2"], "{:,.2f}"),
            "RR": _fmt(rec["R:R"], "1:{:.2f}"),
            "Watch": _fmt(rec["Watch"], "{:,.2f}"),
            "Candle": candle_s,
        })
    return rows


def _json(payload: dict) -> str:
    def default(o):
        if hasattr(o, "item"):
            return o.item()
        if pd.isna(o):
            return None
        raise TypeError(type(o))
    return json.dumps(payload, default=default)


def render(payload: dict) -> str:
    data = _json(payload)
    colors = json.dumps(STATUS_COLOR)
    chips = "".join(
        f'<span class="chip" style="background:{STATUS_COLOR[s]}">{escape(s)} {payload["counts"].get(s, 0)}</span>'
        for s in STATUS_COLOR if payload["counts"].get(s)
    )
    asof = payload["asof"] or "—"
    failed = payload["failed"]
    failed_html = f'<p class="muted">No Yahoo data for: {escape(", ".join(failed))}</p>' if failed else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NSE Daily Scanner</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
         margin: 0; background: #f3f4f6; color: #111827; }}
  header {{ padding: 18px 20px 10px; background: #fff; border-bottom: 1px solid #e5e7eb; }}
  h1 {{ margin: 0; font-size: 22px; }}
  .sub {{ color: #6b7280; font-size: 13px; margin-top: 4px; }}
  .chips {{ margin-top: 10px; }}
  .chip {{ display: inline-block; border-radius: 10px; padding: 2px 8px; margin: 0 6px 6px 0;
           color: #fff; font-size: 12px; font-weight: 600; }}
  main {{ display: grid; grid-template-columns: 1.4fr 0.9fr; gap: 12px; padding: 12px; }}
  @media (max-width: 960px) {{ main {{ grid-template-columns: 1fr; }} }}
  .card {{ background: #fff; border-radius: 10px; padding: 10px; overflow: auto;
           box-shadow: 0 1px 2px rgba(0,0,0,.06); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  th {{ background: #1f2937; color: #fff; padding: 6px 8px; text-align: left; white-space: nowrap; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #e5e7eb; white-space: nowrap; }}
  tbody tr {{ cursor: pointer; }}
  tbody tr:hover {{ background: #f9fafb; }}
  tbody tr.sel {{ outline: 2px solid #2563eb; outline-offset: -2px; }}
  .status {{ color: #fff; font-weight: 700; border-radius: 6px; padding: 2px 6px; }}
  .badge {{ border-radius: 8px; padding: 10px 12px; color: #fff; font-weight: 700;
            font-size: 18px; text-align: center; }}
  .reason {{ font-size: 13px; margin: 8px 0; color: #374151; }}
  .ctab td.ind {{ text-align: center; font-weight: 600; }}
  .ctab td.act {{ text-align: right; font-family: ui-monospace, monospace; }}
  .ok-bull {{ background: rgba(22,163,74,.18); }}
  .ok-bear {{ background: rgba(220,38,38,.18); }}
  .no {{ color: #9ca3af; }}
  .muted {{ color: #6b7280; font-size: 12px; }}
  .plan td {{ padding: 3px 6px; }}
  .plan td.v {{ text-align: right; font-family: ui-monospace, monospace; font-weight: 600; }}
  footer {{ padding: 8px 20px 20px; color: #6b7280; font-size: 12px; }}
</style>
</head>
<body>
<header>
  <h1>NSE Daily Scanner — Bullish &amp; Bearish</h1>
  <div class="sub">Signals from the last completed daily candle: <b>{escape(asof)}</b>
    · built {escape(payload["generated"])} IST · Yahoo Finance (delayed)
    · refreshes weekdays after 16:30 IST</div>
  <div class="chips">{chips}</div>
</header>
<main>
  <section class="card">
    <table id="scan">
      <thead>
        <tr>
          <th>Symbol</th><th>Status</th><th>Setup</th><th>Close</th><th>Chg %</th>
          <th>RSI</th><th>ADX</th><th>RVOL</th><th>Entry</th><th>Stop</th>
          <th>T1</th><th>T2</th><th>R:R (T2)</th><th>Watch</th><th>Candle</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
    {failed_html}
  </section>
  <section class="card" id="detail">
    <div class="muted">Click a symbol for the trade plan and checklist.</div>
  </section>
</main>
<footer>
  Scanning aid, not trading advice. Check every signal on your broker chart before acting.
  Thresholds match Coding 2.docx. Click a row to see why a setup passed or is waiting.
</footer>
<script>
const DATA = {data};
const COLORS = {colors};

function tick(ok) {{
  if (ok === true) return "✅";
  if (ok === false) return "✖";
  return "";
}}

function renderTable() {{
  const tb = document.querySelector("#scan tbody");
  tb.innerHTML = DATA.rows.map((r, i) => `
    <tr data-i="${{i}}" onclick="show(${{i}})">
      <td><b>${{r.Symbol}}</b></td>
      <td><span class="status" style="background:${{COLORS[r.Status] || "#9ca3af"}}">${{r.Status}}</span></td>
      <td>${{r.Setup}}</td>
      <td>${{r.Close}}</td><td>${{r["Chg %"]}}</td>
      <td>${{r.RSI}}</td><td>${{r.ADX}}</td><td>${{r.RVOL}}</td>
      <td>${{r.Entry}}</td><td>${{r.Stop}}</td><td>${{r.T1}}</td><td>${{r.T2}}</td>
      <td>${{r.RR}}</td><td>${{r.Watch}}</td><td>${{r.Candle}}</td>
    </tr>`).join("");
}}

function show(i) {{
  document.querySelectorAll("#scan tbody tr").forEach((tr, j) => tr.classList.toggle("sel", j === i));
  const r = DATA.rows[i];
  const d = DATA.details[r.Symbol];
  const conds = (d.conds || []).map(c => `
    <tr>
      <td class="tick ${{c.bull_ok ? "ok-bull" : (c.bull_ok === false ? "no" : "")}}">${{tick(c.bull_ok)}}</td>
      <td class="${{c.bull_ok ? "ok-bull" : (c.bull_ok === false ? "no" : "")}}">${{c.bull_req}}</td>
      <td class="ind">${{c.name}}</td>
      <td class="act">${{c.actual}}</td>
      <td class="${{c.bear_ok ? "ok-bear" : (c.bear_ok === false ? "no" : "")}}">${{c.bear_req}}</td>
      <td class="tick ${{c.bear_ok ? "ok-bear" : (c.bear_ok === false ? "no" : "")}}">${{tick(c.bear_ok)}}</td>
    </tr>`).join("");
  const plan = (d.plan_rows || []).map(([k, v]) => `<tr><td>${{k}}</td><td class="v">${{v}}</td></tr>`).join("");
  const list = (d.checklist || []).map(s => `
    <tr>
      <td class="${{s.passed ? (s.key.startsWith("bull") ? "ok-bull" : "ok-bear") : ""}}"><b>${{s.label}}</b></td>
      <td class="act">${{s.score}}</td>
      <td style="white-space:normal; font-size:12px">${{s.missing}}</td>
    </tr>`).join("");
  document.getElementById("detail").innerHTML = `
    <div class="badge" style="background:${{COLORS[d.status]}}">${{d.status}}</div>
    <div class="reason"><b>${{d.symbol}}</b> · ${{d.reason}}</div>
    <table class="plan">${{plan}}</table>
    <h3 style="font-size:13px;margin:12px 0 6px">Conditions</h3>
    <table class="ctab">
      <tr><th></th><th>BULLISH</th><th>INDICATOR</th><th>ACTUAL</th><th>BEARISH</th><th></th></tr>
      ${{conds}}
    </table>
    <h3 style="font-size:13px;margin:12px 0 6px">Six setups</h3>
    <table class="ctab">
      <tr><th>SETUP</th><th>MET</th><th>STILL MISSING</th></tr>
      ${{list}}
    </table>`;
}}

renderTable();
if (DATA.rows.length) show(0);
</script>
</body>
</html>
"""


def main():
    settings = config.load_settings()
    symbols = list(config.DEFAULT_WATCHLIST)
    now = data_mod.now_ist()
    frames, failed = _download_with_retry(symbols)
    results = [analyse(sym, frames[sym], settings, now) for sym in symbols if sym in frames]
    if not results:
        raise SystemExit("No data returned for any symbol.")
    table = summary_table(results)
    last_dates = [r.ind.index[-1] for r in results if len(r.ind)]
    asof = max(last_dates).strftime("%a %d %b %Y") if last_dates else None
    counts = {k: int(v) for k, v in table["Status"].value_counts().to_dict().items()}
    payload = {
        "generated": now.strftime("%a %d %b %Y %H:%M"),
        "asof": asof,
        "counts": counts,
        "failed": failed,
        "rows": _table_rows(table),
        "details": {r.symbol: _details(r, settings) for r in results},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(payload), encoding="utf-8")
    print(f"Wrote {OUT} ({len(results)} stocks, failed={failed})")


if __name__ == "__main__":
    main()
