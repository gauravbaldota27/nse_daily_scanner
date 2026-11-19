"""Setup conditions, signal status and trade plan.

All rules are evaluated on ONE daily candle (a row from indicators.compute_all).
The caller decides which candle: the last *completed* candle for confirmed
signals, and the in-progress candle only for "WAIT FOR CONFIRMATION".

Status mapping (agreed):
  BULLISH BREAKOUT  -> STRONG BULLISH     BEARISH BREAKDOWN -> STRONG BEARISH
  BULLISH MOMENTUM  -> BULLISH            BEARISH MOMENTUM  -> BEARISH
  BULLISH PULLBACK  -> BULLISH PULLBACK   BEARISH PULLBACK  -> BEARISH PULLBACK
  If several setups fire on one side, the strongest wins (breakout > momentum > pullback).
  A setup whose R:R (measured at Target 2) is below the minimum becomes NO TRADE.
  WAIT FOR CONFIRMATION: every trend/indicator condition of a setup is met but
  its candle-confirmation conditions are not, or the setup is met only on
  today's still-open candle.
  NEUTRAL: nothing above.
  NO TRADE: R:R rejection, not enough history, or bullish and bearish together.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

BULL_SETUPS = ["bull_breakout", "bull_momentum", "bull_pullback"]   # strongest first
BEAR_SETUPS = ["bear_breakdown", "bear_momentum", "bear_pullback"]

SETUP_LABEL = {
    "bull_momentum": "BULLISH MOMENTUM",
    "bull_breakout": "BULLISH BREAKOUT",
    "bull_pullback": "BULLISH PULLBACK",
    "bear_momentum": "BEARISH MOMENTUM",
    "bear_breakdown": "BEARISH BREAKDOWN",
    "bear_pullback": "BEARISH PULLBACK",
}

SETUP_STATUS = {
    "bull_breakout": "STRONG BULLISH",
    "bull_momentum": "BULLISH",
    "bull_pullback": "BULLISH PULLBACK",
    "bear_breakdown": "STRONG BEARISH",
    "bear_momentum": "BEARISH",
    "bear_pullback": "BEARISH PULLBACK",
}

STATUS_COLOR = {
    "STRONG BULLISH": "#0b8a3e",
    "BULLISH": "#16a34a",
    "BULLISH PULLBACK": "#4ade80",
    "STRONG BEARISH": "#b91c1c",
    "BEARISH": "#dc2626",
    "BEARISH PULLBACK": "#f87171",
    "WAIT FOR CONFIRMATION": "#eab308",
    "NEUTRAL": "#9ca3af",
    "NO TRADE": "#6b7280",
}


@dataclass
class Cond:
    label: str
    ok: bool
    trigger: bool = False   # candle-confirmation condition (used for WAIT)


@dataclass
class SetupResult:
    key: str
    conds: list

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.conds)

    @property
    def score(self) -> str:
        return f"{sum(c.ok for c in self.conds)}/{len(self.conds)}"

    @property
    def failing(self) -> list:
        return [c.label for c in self.conds if not c.ok]

    @property
    def awaiting_trigger(self) -> bool:
        """All non-trigger conditions pass, at least one trigger fails."""
        base = [c for c in self.conds if not c.trigger]
        trig = [c for c in self.conds if c.trigger]
        return all(c.ok for c in base) and not all(c.ok for c in trig)


@dataclass
class TradePlan:
    direction: str            # "LONG" / "SHORT"
    setup: str
    entry: float
    stop: float
    t1: float
    t2: float
    rr: float                 # reward:risk at Target 2
    pct_to_stop: float
    pct_to_t1: float
    pct_to_t2: float
    valid: bool
    signal_date: pd.Timestamp


@dataclass
class Evaluation:
    status: str
    reason: str
    setups: dict = field(default_factory=dict)       # key -> SetupResult
    fired: list = field(default_factory=list)        # setup keys that passed
    waiting_for: str | None = None
    watch_level: float | None = None
    plan: TradePlan | None = None
    candle_date: pd.Timestamp | None = None


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def _ge(a, b):
    a, b = _f(a), _f(b)
    return bool(not np.isnan(a) and not np.isnan(b) and a >= b)


def _gt(a, b):
    a, b = _f(a), _f(b)
    return bool(not np.isnan(a) and not np.isnan(b) and a > b)


def _between(x, lo, hi):
    x = _f(x)
    return bool(not np.isnan(x) and lo <= x <= hi)


def _near(price, level, pct):
    price, level = _f(price), _f(level)
    if np.isnan(price) or np.isnan(level) or level == 0:
        return False
    return abs(price - level) / level * 100 <= pct


def evaluate_setups(r: pd.Series, s: dict) -> dict:
    """Evaluate all six setups on one candle. Returns key -> SetupResult."""
    p = s["params"]
    e_s, e_m, e_l = r[f"ema{p['ema_short']}"], r[f"ema{p['ema_mid']}"], r[f"ema{p['ema_long']}"]
    c, o = r["Close"], r["Open"]
    n = p["breakout_len"]
    out = {}

    t = s["bull_momentum"]
    out["bull_momentum"] = SetupResult("bull_momentum", [
        Cond(f"RSI {t['rsi_min']}–{t['rsi_max']}", _between(r["rsi"], t["rsi_min"], t["rsi_max"])),
        Cond(f"ADX ≥ {t['adx_min']}", _ge(r["adx"], t["adx_min"])),
        Cond("+DI > −DI", _gt(r["plus_di"], r["minus_di"])),
        Cond("EMA20 > EMA50", _gt(e_s, e_m)),
        Cond("EMA50 > EMA200", _gt(e_m, e_l)),
        Cond("EMA20 rising", _gt(e_s, r["ema_short_prev"])),
        Cond("Close > EMA20", _gt(c, e_s)),
        Cond("MACD > Signal", _gt(r["macd"], r["macd_signal"])),
        Cond(f"RVOL ≥ {t['rvol_min']}", _ge(r["rvol"], t["rvol_min"]), trigger=True),
        Cond("Close > prev day high", _gt(c, r["prev_high"]), trigger=True),
    ])

    t = s["bull_breakout"]
    out["bull_breakout"] = SetupResult("bull_breakout", [
        Cond(f"RSI {t['rsi_min']}–{t['rsi_max']}", _between(r["rsi"], t["rsi_min"], t["rsi_max"])),
        Cond(f"ADX ≥ {t['adx_min']}", _ge(r["adx"], t["adx_min"])),
        Cond("+DI > −DI", _gt(r["plus_di"], r["minus_di"])),
        Cond("EMA20 > EMA50", _gt(e_s, e_m)),
        Cond("MACD > Signal", _gt(r["macd"], r["macd_signal"])),
        Cond(f"Close > {n}D high", _gt(c, r["high_n"]), trigger=True),
        Cond(f"RVOL ≥ {t['rvol_min']}", _ge(r["rvol"], t["rvol_min"]), trigger=True),
        Cond("Close > Open", _gt(c, o), trigger=True),
        Cond(f"Body ≥ {t['body_min_pct']}% of range", _ge(r["body_pct"], t["body_min_pct"]), trigger=True),
    ])

    t = s["bull_pullback"]
    out["bull_pullback"] = SetupResult("bull_pullback", [
        Cond("Close > EMA200", _gt(c, e_l)),
        Cond("EMA50 > EMA200", _gt(e_m, e_l)),
        Cond("EMA20 > EMA50", _gt(e_s, e_m)),
        Cond(f"RSI {t['rsi_min']}–{t['rsi_max']}", _between(r["rsi"], t["rsi_min"], t["rsi_max"])),
        Cond(f"Close within {t['ema_dist_pct']}% of EMA20/50",
             _near(c, e_s, t["ema_dist_pct"]) or _near(c, e_m, t["ema_dist_pct"])),
        Cond("Volume < 20D avg", _gt(r["vol_avg"], r["Volume"])),
        Cond("Close > prev day high", _gt(c, r["prev_high"]), trigger=True),
        Cond("Close > Open", _gt(c, o), trigger=True),
    ])

    t = s["bear_momentum"]
    out["bear_momentum"] = SetupResult("bear_momentum", [
        Cond(f"RSI {t['rsi_min']}–{t['rsi_max']}", _between(r["rsi"], t["rsi_min"], t["rsi_max"])),
        Cond(f"ADX ≥ {t['adx_min']}", _ge(r["adx"], t["adx_min"])),
        Cond("−DI > +DI", _gt(r["minus_di"], r["plus_di"])),
        Cond("EMA20 < EMA50", _gt(e_m, e_s)),
        Cond("EMA50 < EMA200", _gt(e_l, e_m)),
        Cond("EMA20 falling", _gt(r["ema_short_prev"], e_s)),
        Cond("Close < EMA20", _gt(e_s, c)),
        Cond("MACD < Signal", _gt(r["macd_signal"], r["macd"])),
        Cond(f"RVOL ≥ {t['rvol_min']}", _ge(r["rvol"], t["rvol_min"]), trigger=True),
        Cond("Close < prev day low", _gt(r["prev_low"], c), trigger=True),
    ])

    t = s["bear_breakdown"]
    out["bear_breakdown"] = SetupResult("bear_breakdown", [
        Cond(f"RSI {t['rsi_min']}–{t['rsi_max']}", _between(r["rsi"], t["rsi_min"], t["rsi_max"])),
        Cond(f"ADX ≥ {t['adx_min']}", _ge(r["adx"], t["adx_min"])),
        Cond("−DI > +DI", _gt(r["minus_di"], r["plus_di"])),
        Cond("EMA20 < EMA50", _gt(e_m, e_s)),
        Cond("MACD < Signal", _gt(r["macd_signal"], r["macd"])),
        Cond(f"Close < {n}D low", _gt(r["low_n"], c), trigger=True),
        Cond(f"RVOL ≥ {t['rvol_min']}", _ge(r["rvol"], t["rvol_min"]), trigger=True),
        Cond("Close < Open", _gt(o, c), trigger=True),
        Cond(f"Body ≥ {t['body_min_pct']}% of range", _ge(r["body_pct"], t["body_min_pct"]), trigger=True),
    ])

    t = s["bear_pullback"]
    out["bear_pullback"] = SetupResult("bear_pullback", [
        Cond("Close < EMA200", _gt(e_l, c)),
        Cond("EMA50 < EMA200", _gt(e_l, e_m)),
        Cond("EMA20 < EMA50", _gt(e_m, e_s)),
        Cond(f"RSI {t['rsi_min']}–{t['rsi_max']}", _between(r["rsi"], t["rsi_min"], t["rsi_max"])),
        Cond(f"Close within {t['ema_dist_pct']}% of EMA20/50",
             _near(c, e_s, t["ema_dist_pct"]) or _near(c, e_m, t["ema_dist_pct"])),
        Cond("Volume < 20D avg", _gt(r["vol_avg"], r["Volume"])),
        Cond("Close < prev day low", _gt(r["prev_low"], c), trigger=True),
        Cond("Close < Open", _gt(o, c), trigger=True),
    ])
    return out


def trade_plan(r: pd.Series, setup_key: str, s: dict) -> TradePlan:
    t = s["trade"]
    entry, a = _f(r["Close"]), _f(r["atr"])
    long = setup_key.startswith("bull")
    sign = 1 if long else -1
    stop = entry - sign * t["sl_atr_mult"] * a
    t1 = entry + sign * t["t1_atr_mult"] * a
    t2 = entry + sign * t["t2_atr_mult"] * a
    risk = abs(entry - stop)
    rr = abs(t2 - entry) / risk if risk > 0 else 0.0
    return TradePlan(
        direction="LONG" if long else "SHORT",
        setup=SETUP_LABEL[setup_key],
        entry=entry, stop=stop, t1=t1, t2=t2, rr=rr,
        pct_to_stop=abs(stop - entry) / entry * 100,
        pct_to_t1=abs(t1 - entry) / entry * 100,
        pct_to_t2=abs(t2 - entry) / entry * 100,
        valid=rr >= t["min_rr"] - 1e-9,
        signal_date=r.name,
    )


def _watch_level(df_completed: pd.DataFrame, setup_key: str, s: dict) -> float:
    """Price the NEXT daily close must beat to confirm a setup that is waiting."""
    last = df_completed.iloc[-1]
    n = s["params"]["breakout_len"]
    if setup_key == "bull_breakout":
        return float(df_completed["High"].iloc[-n:].max())
    if setup_key == "bear_breakdown":
        return float(df_completed["Low"].iloc[-n:].min())
    if setup_key.startswith("bull"):
        return float(last["High"])
    return float(last["Low"])


def evaluate(df_completed: pd.DataFrame, s: dict, live_row: pd.Series | None = None) -> Evaluation:
    """Full evaluation for one stock.

    df_completed: indicator frame containing ONLY completed daily candles.
    live_row: indicator row for today's in-progress candle, if the market is open.
    """
    p = s["params"]
    if len(df_completed) < p["ema_long"] + 2:
        return Evaluation("NO TRADE", f"Not enough history ({len(df_completed)} candles, "
                                      f"need {p['ema_long'] + 2})")
    r = df_completed.iloc[-1]
    needed = ["rsi", "adx", "plus_di", "minus_di", f"ema{p['ema_long']}", "macd_signal",
              "atr", "rvol", "high_n", "low_n"]
    if any(pd.isna(r.get(k)) for k in needed):
        return Evaluation("NO TRADE", "Indicators not ready (missing data)", candle_date=r.name)

    setups = evaluate_setups(r, s)
    bull = [k for k in BULL_SETUPS if setups[k].passed]
    bear = [k for k in BEAR_SETUPS if setups[k].passed]
    ev = Evaluation("NEUTRAL", "No setup conditions met", setups=setups,
                    fired=bull + bear, candle_date=r.name)

    if bull and bear:
        ev.status, ev.reason = "NO TRADE", "Bullish and bearish setups both fired"
        return ev

    if bull or bear:
        key = (bull or bear)[0]
        ev.plan = trade_plan(r, key, s)
        if ev.plan.valid:
            ev.status = SETUP_STATUS[key]
            ev.reason = f"{SETUP_LABEL[key]} confirmed on the {r.name:%d %b %Y} daily close"
        else:
            ev.status = "NO TRADE"
            ev.reason = (f"{SETUP_LABEL[key]} fired but R:R 1:{ev.plan.rr:.2f} is below "
                         f"1:{s['trade']['min_rr']:g}")
        return ev

    # Nothing confirmed. Is today's open candle showing a setup?
    if live_row is not None:
        live = evaluate_setups(live_row, s)
        live_hits = [k for k in BULL_SETUPS + BEAR_SETUPS if live[k].passed]
        if live_hits:
            k = live_hits[0]
            ev.status = "WAIT FOR CONFIRMATION"
            ev.waiting_for = k
            ev.reason = f"{SETUP_LABEL[k]} showing on today's open candle; confirm at the close"
            ev.watch_level = _watch_level(df_completed, k, s)
            return ev

    # Trend and indicators aligned, candle not yet confirming.
    waiting = [k for k in BULL_SETUPS + BEAR_SETUPS if setups[k].awaiting_trigger]
    if waiting:
        k = waiting[0]
        ev.status = "WAIT FOR CONFIRMATION"
        ev.waiting_for = k
        ev.watch_level = _watch_level(df_completed, k, s)
        missing = ", ".join(setups[k].failing)
        ev.reason = f"{SETUP_LABEL[k]} aligned; waiting for: {missing}"
    return ev


def indicator_rows(r: pd.Series, s: dict) -> list:
    """Rows for the side-by-side Bullish | Indicator | Bearish table (spec sections 1 and 5).

    RSI / ADX / RVOL bands shown here are the Momentum thresholds, as in the spec's main table.
    """
    p = s["params"]
    bm, sm = s["bull_momentum"], s["bear_momentum"]
    tr = s["trade"]
    es, em, el, ef = (r[f"ema{p[k]}"] for k in ("ema_short", "ema_mid", "ema_long", "ema_fast"))
    c, n = r["Close"], p["breakout_len"]

    def row(name, actual, bull_req, bull_ok, bear_req, bear_ok):
        return {"name": name, "actual": actual, "bull_req": bull_req, "bull_ok": bull_ok,
                "bear_req": bear_req, "bear_ok": bear_ok}

    def fmt(x, d=2):
        return "—" if pd.isna(x) else f"{x:,.{d}f}"

    return [
        row(f"RSI ({p['rsi_len']})", fmt(r["rsi"], 1),
            f"{bm['rsi_min']}–{bm['rsi_max']}", _between(r["rsi"], bm["rsi_min"], bm["rsi_max"]),
            f"{sm['rsi_min']}–{sm['rsi_max']}", _between(r["rsi"], sm["rsi_min"], sm["rsi_max"])),
        row(f"ADX ({p['adx_len']})", fmt(r["adx"], 1),
            f"≥ {bm['adx_min']}", _ge(r["adx"], bm["adx_min"]),
            f"≥ {sm['adx_min']}", _ge(r["adx"], sm["adx_min"])),
        row(f"+DI ({p['adx_len']})", fmt(r["plus_di"], 1), "> −DI", _gt(r["plus_di"], r["minus_di"]),
            "< −DI", _gt(r["minus_di"], r["plus_di"])),
        row(f"−DI ({p['adx_len']})", fmt(r["minus_di"], 1), "< +DI", _gt(r["plus_di"], r["minus_di"]),
            "> +DI", _gt(r["minus_di"], r["plus_di"])),
        row(f"EMA {p['ema_fast']}", fmt(ef), f"> EMA{p['ema_short']}", _gt(ef, es),
            f"< EMA{p['ema_short']}", _gt(es, ef)),
        row(f"EMA {p['ema_short']}", fmt(es), f"> EMA{p['ema_mid']}", _gt(es, em),
            f"< EMA{p['ema_mid']}", _gt(em, es)),
        row(f"EMA {p['ema_mid']}", fmt(em), f"> EMA{p['ema_long']}", _gt(em, el),
            f"< EMA{p['ema_long']}", _gt(el, em)),
        row(f"EMA {p['ema_long']}", fmt(el), f"Close > EMA{p['ema_long']}", _gt(c, el),
            f"Close < EMA{p['ema_long']}", _gt(el, c)),
        row("Close", fmt(c), f"Close > EMA{p['ema_short']}", _gt(c, es),
            f"Close < EMA{p['ema_short']}", _gt(es, c)),
        row("MACD / Signal",
            f"{fmt(r['macd'])} / {fmt(r['macd_signal'])}",
            "> Signal", _gt(r["macd"], r["macd_signal"]),
            "< Signal", _gt(r["macd_signal"], r["macd"])),
        row("Rel. Volume", fmt(r["rvol"]) + "×",
            f"≥ {bm['rvol_min']}×", _ge(r["rvol"], bm["rvol_min"]),
            f"≥ {sm['rvol_min']}×", _ge(r["rvol"], sm["rvol_min"])),
        row(f"{n}D High", fmt(r["high_n"]), "Close above", _gt(c, r["high_n"]),
            "—", None),
        row(f"{n}D Low", fmt(r["low_n"]), "—", None,
            "Close below", _gt(r["low_n"], c)),
        row("Candle C−O", f"{c - r['Open']:+,.2f}", "Bullish", _gt(c, r["Open"]),
            "Bearish", _gt(r["Open"], c)),
        row(f"ATR ({p['atr_len']})", fmt(r["atr"]),
            f"SL = Entry − {tr['sl_atr_mult']:g}×", None,
            f"SL = Entry + {tr['sl_atr_mult']:g}×", None),
    ]
