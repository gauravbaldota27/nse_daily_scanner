"""Daily candlestick chart shared by the Streamlit app and the static report."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .signals import BEAR_SETUPS, BULL_SETUPS, SETUP_LABEL, evaluate_setups


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
