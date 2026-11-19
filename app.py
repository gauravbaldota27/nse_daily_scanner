"""NSE Daily Bullish & Bearish Scanner — single-screen dashboard.

Run:  streamlit run app.py
"""

import copy
import json
from html import escape

import pandas as pd
import streamlit as st

from scanner import config
from scanner import data as data_mod
from scanner.chart import build_chart
from scanner.engine import analyse, summary_table
from scanner.signals import SETUP_LABEL, STATUS_COLOR, indicator_rows

st.set_page_config(page_title="NSE Daily Scanner", layout="wide", page_icon="📈")

st.markdown("""
<style>
  .block-container {padding-top: 3.3rem; padding-bottom: 0.2rem; max-width: 100%;}
  h1, h2, h3 {margin: 0 !important; padding: 0 !important;}
  div[data-testid="stVerticalBlock"] {gap: 0.35rem;}
  .ctab {width:100%; border-collapse:collapse; font-size:12.5px;}
  .ctab th {background:#1f2937; color:#fff; padding:4px 6px; text-align:center; white-space:nowrap;}
  .ctab td {padding:2px 6px; white-space:nowrap; border-bottom:1px solid rgba(128,128,128,.25);}
  .ctab td.ind {text-align:center; font-weight:600;}
  .ctab td.act {text-align:right; font-family:monospace;}
  .ok-bull {background:rgba(22,163,74,.18);}
  .ok-bear {background:rgba(220,38,38,.18);}
  .no {color:#9ca3af;}
  .tick {text-align:center; width:20px;}
  .badge {border-radius:8px; padding:10px 12px; color:#fff; font-weight:700; font-size:20px;
          text-align:center; letter-spacing:.5px;}
  .reason {font-size:12.5px; margin:4px 0 6px 0;}
  .plan {width:100%; font-size:13px; border-collapse:collapse;}
  .plan td {padding:3px 6px; border-bottom:1px solid rgba(128,128,128,.25);}
  .plan td.v {text-align:right; font-family:monospace; font-weight:600;}
  .chip {display:inline-block; border-radius:10px; padding:1px 8px; margin-right:4px;
         color:#fff; font-size:11.5px; font-weight:600;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------- settings ---
LABELS = {
    "rsi_min": "RSI min", "rsi_max": "RSI max", "adx_min": "ADX min", "rvol_min": "Rel. volume min",
    "body_min_pct": "Body % of range min", "ema_dist_pct": "Max % from EMA20/50",
    "sl_atr_mult": "Stop = ATR ×", "t1_atr_mult": "Target 1 = ATR ×", "t2_atr_mult": "Target 2 = ATR ×",
    "min_rr": "Min R:R (at Target 2)", "close_hhmm": "NSE close time (IST)",
}
GROUPS = [
    ("Bullish thresholds", ["bull_momentum", "bull_breakout", "bull_pullback"]),
    ("Bearish thresholds", ["bear_momentum", "bear_breakdown", "bear_pullback"]),
    ("Trade plan", ["trade"]),
    ("Indicator periods", ["params"]),
]

if "settings" not in st.session_state:
    st.session_state.settings = config.load_settings()
S = st.session_state.settings

with st.sidebar:
    st.subheader("Watchlist")
    wl_text = st.text_area("NSE symbols (comma or new line)",
                           value=", ".join(config.DEFAULT_WATCHLIST), height=140,
                           help="Plain NSE symbols, e.g. RELIANCE. '.NS' is added for Yahoo.")
    show_bb = st.checkbox("Show Bollinger Bands (20, 2)", value=False)
    bars = st.slider("Candles on chart", 60, 250, 120, 10)
    if st.button("↻ Refresh data", width="stretch"):
        st.cache_data.clear()

    st.subheader("Settings")
    for title, keys in GROUPS:
        with st.expander(title):
            for g in keys:
                if g != "params" and g != "trade":
                    st.markdown(f"**{SETUP_LABEL[g].title()}**")
                for k, v in S[g].items():
                    label = LABELS.get(k, k)
                    wkey = f"set_{g}_{k}"
                    if isinstance(v, bool):
                        continue
                    if isinstance(v, int):
                        S[g][k] = int(st.number_input(label, value=v, step=1, key=wkey))
                    else:
                        S[g][k] = float(st.number_input(label, value=float(v), step=0.1,
                                                        format="%.2f", key=wkey))
    with st.expander("Market timing"):
        S["market"]["close_hhmm"] = st.text_input(LABELS["close_hhmm"],
                                                  value=S["market"]["close_hhmm"])
    c1, c2 = st.columns(2)
    if c1.button("Save", width="stretch"):
        config.save_settings(S)
        st.toast("Settings saved to settings.json")
    if c2.button("Reset to spec", width="stretch"):
        config.reset_settings()
        st.session_state.settings = copy.deepcopy(config.DEFAULTS)
        for key in [k for k in st.session_state if str(k).startswith("set_")]:
            del st.session_state[key]
        st.rerun()

# -------------------------------------------------------------------- data ---
symbols = tuple(data_mod.parse_watchlist(wl_text))


@st.cache_data(ttl=600, show_spinner=False)
def get_prices(syms: tuple):
    return data_mod.download(list(syms))


@st.cache_data(ttl=300, show_spinner=False)
def run_scan(syms: tuple, settings_json: str, minute_bucket: str):
    settings = json.loads(settings_json)
    frames, failed = get_prices(syms)
    now = data_mod.now_ist()
    results = [analyse(sym, frames[sym], settings, now) for sym in syms if sym in frames]
    return results, failed


if not symbols:
    st.info("Add at least one NSE symbol in the sidebar.")
    st.stop()

now = data_mod.now_ist()
bucket = now.strftime("%Y-%m-%d %H:") + f"{now.minute // 5 * 5:02d}"
with st.spinner(f"Scanning {len(symbols)} stocks on daily candles…"):
    try:
        results, failed = run_scan(symbols, json.dumps(S, sort_keys=True), bucket)
    except Exception as exc:  # network / Yahoo errors
        st.error(f"Could not load data from Yahoo Finance: {exc}")
        st.stop()

if not results:
    st.error("No data returned for any symbol. Check the symbols and your internet connection.")
    st.stop()

table = summary_table(results)
by_symbol = {r.symbol: r for r in results}

# ------------------------------------------------------------------ header ---
last_dates = [r.ind.index[-1] for r in results if len(r.ind)]
asof = max(last_dates) if last_dates else None
market_open = any(r.live is not None for r in results)
counts = table["Status"].value_counts()
chips = "".join(
    f'<span class="chip" style="background:{STATUS_COLOR[s]}">{escape(s)} {counts[s]}</span>'
    for s in STATUS_COLOR if s in counts)

h1, h2 = st.columns([0.42, 0.58])
with h1:
    st.markdown("### NSE Daily Scanner — Bullish & Bearish")
    st.caption(
        f"Signals from the last completed daily candle: **{asof:%a %d %b %Y}**"
        + (" · market open: today's candle is shown on the chart but not used for confirmed signals"
           if market_open else "")
        + f" · {now:%H:%M} IST · Yahoo Finance (delayed)")
with h2:
    options = [f"{row.Symbol}  ·  {row.Status}" for row in table.itertuples()]
    sel = st.selectbox("Stock", options, index=0, label_visibility="collapsed")
    st.markdown(chips, unsafe_allow_html=True)

symbol = sel.split("  ·  ")[0]
res = by_symbol[symbol]
ev = res.ev


# ----------------------------------------------------------- html helpers ---
def mark(ok):
    return "" if ok is None else ("✅" if ok else "✖")


def conditions_html(rows):
    h = ['<table class="ctab"><tr><th></th><th>BULLISH</th><th>INDICATOR</th>'
         '<th>ACTUAL</th><th>BEARISH</th><th></th></tr>']
    for r in rows:
        bc = "ok-bull" if r["bull_ok"] else ("no" if r["bull_ok"] is not None else "")
        sc = "ok-bear" if r["bear_ok"] else ("no" if r["bear_ok"] is not None else "")
        h.append(
            f'<tr><td class="tick {bc}">{mark(r["bull_ok"])}</td>'
            f'<td class="{bc}">{escape(r["bull_req"])}</td>'
            f'<td class="ind">{escape(r["name"])}</td>'
            f'<td class="act">{escape(r["actual"])}</td>'
            f'<td class="{sc}">{escape(r["bear_req"])}</td>'
            f'<td class="tick {sc}">{mark(r["bear_ok"])}</td></tr>')
    h.append("</table>")
    return "".join(h)


def money(x):
    return f"₹{x:,.2f}"


def status_html(res):
    ev = res.ev
    col = STATUS_COLOR[ev.status]
    out = [f'<div class="badge" style="background:{col}">{escape(ev.status)}</div>',
           f'<div class="reason">{escape(res.symbol)} · {escape(ev.reason)}</div>']
    plan = ev.plan
    if plan is not None:
        sgn = 1 if plan.direction == "LONG" else -1
        rows = [
            ("Direction", plan.direction),
            ("Setup", plan.setup.title()),
            ("Entry (daily close)", money(plan.entry)),
            ("Stop loss", f"{money(plan.stop)} ({-sgn * plan.pct_to_stop:+.2f}%)"),
            ("Target 1", f"{money(plan.t1)} ({sgn * plan.pct_to_t1:+.2f}%)"),
            ("Target 2", f"{money(plan.t2)} ({sgn * plan.pct_to_t2:+.2f}%)"),
            ("Risk : Reward (at T2)", f"1 : {plan.rr:.2f}"),
            ("Setup validity", "VALID" if plan.valid else
             f"REJECTED (min 1:{S['trade']['min_rr']:g})"),
            ("Signal date", f"{plan.signal_date:%d %b %Y}"),
        ]
    else:
        last = res.ind.iloc[-1]
        rows = [("Last close", money(last["Close"])),
                ("ATR (14)", money(last["atr"]) if pd.notna(last["atr"]) else "—")]
        if ev.watch_level is not None:
            word = "above" if ev.waiting_for.startswith("bull") else "below"
            rows.append(("Needs next daily close", f"{word} {money(ev.watch_level)}"))
        rows.append(("Trade plan", "Shown when a setup is confirmed"))
        if ev.candle_date is not None:
            rows.append(("Candle evaluated", f"{ev.candle_date:%d %b %Y}"))
    out.append('<table class="plan">' + "".join(
        f'<tr><td>{escape(k)}</td><td class="v">{escape(v)}</td></tr>' for k, v in rows) + "</table>")
    return "".join(out)


def checklist_html(ev):
    if not ev.setups:
        return ""
    h = ['<table class="ctab"><tr><th>SETUP</th><th>MET</th><th>STILL MISSING</th></tr>']
    for k in ["bull_breakout", "bull_momentum", "bull_pullback",
              "bear_breakdown", "bear_momentum", "bear_pullback"]:
        sr = ev.setups[k]
        cls = ("ok-bull" if k.startswith("bull") else "ok-bear") if sr.passed else ""
        miss = "All conditions met" if sr.passed else ", ".join(sr.failing)
        h.append(f'<tr><td class="{cls}"><b>{escape(SETUP_LABEL[k])}</b></td>'
                 f'<td class="act {cls}">{sr.score}</td><td style="font-size:11.5px; white-space:normal">{escape(miss)}</td></tr>')
    h.append("</table>")
    return "".join(h)


# ------------------------------------------------------------------ layout ---
left, mid, right = st.columns([0.45, 0.33, 0.22])
with left:
    if len(res.ind) >= 2:
        st.plotly_chart(build_chart(res, S, show_bb, bars), width="stretch",
                        config={"displayModeBar": False})
with mid:
    if len(res.ind) and ev.setups:
        st.markdown(conditions_html(indicator_rows(res.ind.iloc[-1], S)), unsafe_allow_html=True)
    else:
        st.warning(ev.reason)
with right:
    st.markdown(status_html(res), unsafe_allow_html=True)

bottom_l, bottom_r = st.columns([0.64, 0.36])
with bottom_l:
    def color_status(v):
        return f"background-color:{STATUS_COLOR.get(v, '#fff')}; color:white; font-weight:600"

    show = table.copy()
    show["Candle"] = pd.to_datetime(show["Candle"]).dt.strftime("%d %b")
    fmts = {"Close": "{:,.2f}", "Chg %": "{:+.2f}", "RSI": "{:.1f}", "ADX": "{:.1f}",
            "RVOL": "{:.2f}", "Entry": "{:,.2f}", "Stop": "{:,.2f}", "T1": "{:,.2f}",
            "T2": "{:,.2f}", "R:R": "1:{:.2f}", "Watch": "{:,.2f}"}
    for c, f in fmts.items():
        show[c] = [("" if pd.isna(v) else f.format(float(v))) for v in pd.to_numeric(show[c], errors="coerce")]
    show = show.rename(columns={"R:R": "R:R (T2)", "Watch": "Watch level"})
    st.dataframe(show.style.map(color_status, subset=["Status"]),
                 height=262, hide_index=True, width="stretch")
    if failed:
        st.caption("No data for: " + ", ".join(failed))
with bottom_r:
    st.markdown(checklist_html(ev), unsafe_allow_html=True)
