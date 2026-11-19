"""NSE Daily Bullish & Bearish Scanner — single-screen dashboard.

Run:  streamlit run app.py
"""

import copy
import json
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from scanner import config
from scanner import data as data_mod
from scanner.engine import analyse, summary_table
from scanner.signals import (BEAR_SETUPS, BULL_SETUPS, SETUP_LABEL, STATUS_COLOR,
                             evaluate_setups, indicator_rows)

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


# ------------------------------------------------------------------- chart ---
def build_chart(res, settings, show_bb, bars):
    p = settings["params"]
    ind = res.ind.iloc[-bars:]
    x = list(ind.index.strftime("%d %b %y"))
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.8, 0.2],
                        vertical_spacing=0.02)
    fig.add_trace(go.Candlestick(x=x, open=ind["Open"], high=ind["High"], low=ind["Low"],
                                 close=ind["Close"], name="Daily",
                                 increasing_line_color="#16a34a", decreasing_line_color="#dc2626",
                                 showlegend=False), 1, 1)
    xs = x
    if res.live is not None:
        lx = ["Today (open)"]
        xs = x + lx
        lv = res.live
        fig.add_trace(go.Candlestick(x=lx, open=[lv["Open"]], high=[lv["High"]], low=[lv["Low"]],
                                     close=[lv["Close"]], name="Today (incomplete)",
                                     increasing_line_color="#9ca3af",
                                     decreasing_line_color="#9ca3af", showlegend=False), 1, 1)

    ema_colors = {p["ema_fast"]: "#a855f7", p["ema_short"]: "#f59e0b",
                  p["ema_mid"]: "#3b82f6", p["ema_long"]: "#64748b"}
    for n, col in ema_colors.items():
        fig.add_trace(go.Scatter(x=x, y=ind[f"ema{n}"], name=f"EMA{n}", mode="lines",
                                 line=dict(color=col, width=1.4)), 1, 1)
    nb = p["breakout_len"]
    fig.add_trace(go.Scatter(x=x, y=ind["high_n"], name=f"{nb}D high", mode="lines",
                             line=dict(color="#16a34a", width=1, dash="dot", shape="hv")), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=ind["low_n"], name=f"{nb}D low", mode="lines",
                             line=dict(color="#dc2626", width=1, dash="dot", shape="hv")), 1, 1)
    if show_bb:
        for k in ("bb_upper", "bb_lower"):
            fig.add_trace(go.Scatter(x=x, y=ind[k], name="BB", mode="lines", showlegend=k == "bb_upper",
                                     line=dict(color="#94a3b8", width=0.8, dash="dash")), 1, 1)

    # past signals in the visible window
    bx, by, bt, sx, sy, stt = [], [], [], [], [], []
    for d, row in ind.iterrows():
        su = evaluate_setups(row, settings)
        bull = [SETUP_LABEL[k] for k in BULL_SETUPS if su[k].passed]
        bear = [SETUP_LABEL[k] for k in BEAR_SETUPS if su[k].passed]
        if bull:
            bx.append(d.strftime("%d %b %y")); by.append(row["Low"] * 0.985); bt.append(", ".join(bull))
        if bear:
            sx.append(d.strftime("%d %b %y")); sy.append(row["High"] * 1.015); stt.append(", ".join(bear))
    if bx:
        fig.add_trace(go.Scatter(x=bx, y=by, mode="markers", name="Bull signal", text=bt,
                                 hovertemplate="%{text}<extra></extra>",
                                 marker=dict(symbol="triangle-up", size=10, color="#16a34a")), 1, 1)
    if sx:
        fig.add_trace(go.Scatter(x=sx, y=sy, mode="markers", name="Bear signal", text=stt,
                                 hovertemplate="%{text}<extra></extra>",
                                 marker=dict(symbol="triangle-down", size=10, color="#dc2626")), 1, 1)

    plan = res.ev.plan
    if plan is not None:
        for lvl, name, col, dash in [(plan.entry, "Entry", "#2563eb", "solid"),
                                     (plan.stop, "SL", "#dc2626", "dash"),
                                     (plan.t1, "T1", "#16a34a", "dash"),
                                     (plan.t2, "T2", "#15803d", "dash")]:
            fig.add_hline(y=lvl, line=dict(color=col, width=1, dash=dash), row=1, col=1,
                          annotation_text=f"{name} {lvl:,.2f}", annotation_position="right",
                          annotation_font_size=10)
    elif res.ev.watch_level is not None:
        fig.add_hline(y=res.ev.watch_level, line=dict(color="#eab308", width=1.2, dash="dash"),
                      row=1, col=1, annotation_text=f"Watch {res.ev.watch_level:,.2f}",
                      annotation_position="right", annotation_font_size=10)

    vcol = ["#16a34a" if c >= o else "#dc2626" for o, c in zip(ind["Open"], ind["Close"])]
    fig.add_trace(go.Bar(x=x, y=ind["Volume"], marker_color=vcol, name="Volume",
                         showlegend=False, opacity=0.6), 2, 1)
    fig.add_trace(go.Scatter(x=x, y=ind["vol_avg"], name=f"Vol avg {p['vol_avg_len']}",
                             mode="lines", line=dict(color="#f59e0b", width=1),
                             showlegend=False), 2, 1)
    if res.live is not None:
        fig.add_trace(go.Bar(x=["Today (open)"], y=[res.live["Volume"]], marker_color="#9ca3af",
                             showlegend=False), 2, 1)

    fig.update_layout(height=455, margin=dict(l=4, r=70, t=24, b=4),
                      xaxis_rangeslider_visible=False,
                      legend=dict(orientation="h", y=1.04, x=0, font=dict(size=10)),
                      hovermode="x unified", template="plotly_white")
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=xs, nticks=10,
                     tickfont=dict(size=10))
    fig.update_yaxes(tickfont=dict(size=10), side="left")
    return fig


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
