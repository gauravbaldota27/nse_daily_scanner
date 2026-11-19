"""Glue: raw candles -> indicators -> evaluation, for one stock or a watchlist."""

from dataclasses import dataclass

import pandas as pd

from .data import split_completed
from .indicators import compute_all
from .signals import SETUP_LABEL, Evaluation, evaluate

STATUS_ORDER = ["STRONG BULLISH", "STRONG BEARISH", "BULLISH", "BEARISH",
                "BULLISH PULLBACK", "BEARISH PULLBACK", "WAIT FOR CONFIRMATION",
                "NO TRADE", "NEUTRAL"]


@dataclass
class StockResult:
    symbol: str
    ind: pd.DataFrame            # completed candles with indicators
    live: pd.Series | None       # in-progress candle with indicators, if market open
    ev: Evaluation


def analyse(symbol: str, df: pd.DataFrame, settings: dict, now=None) -> StockResult:
    _, live_raw = split_completed(df, settings["market"]["close_hhmm"], now)
    full = compute_all(df, settings["params"])
    if live_raw is not None:
        ind, live = full.iloc[:-1], full.iloc[-1]
    else:
        ind, live = full, None
    return StockResult(symbol, ind, live, evaluate(ind, settings, live))


def summary_row(res: StockResult) -> dict:
    ev, ind = res.ev, res.ind
    last = ind.iloc[-1] if len(ind) else None
    prev_close = ind["Close"].iloc[-2] if len(ind) > 1 else None
    plan = ev.plan
    setup = (plan.setup if plan else
             SETUP_LABEL.get(ev.waiting_for, "") + (" (waiting)" if ev.waiting_for else ""))
    return {
        "Symbol": res.symbol,
        "Status": ev.status,
        "Setup": setup,
        "Close": None if last is None else last["Close"],
        "Chg %": None if last is None or prev_close is None else (last["Close"] / prev_close - 1) * 100,
        "RSI": None if last is None else last.get("rsi"),
        "ADX": None if last is None else last.get("adx"),
        "RVOL": None if last is None else last.get("rvol"),
        "Entry": plan.entry if plan else None,
        "Stop": plan.stop if plan else None,
        "T1": plan.t1 if plan else None,
        "T2": plan.t2 if plan else None,
        "R:R": plan.rr if plan else None,
        "Watch": ev.watch_level,
        "Candle": ev.candle_date,
    }


def summary_table(results: list) -> pd.DataFrame:
    rows = [summary_row(r) for r in results]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["_o"] = df["Status"].map({s: i for i, s in enumerate(STATUS_ORDER)})
    return df.sort_values(["_o", "Symbol"]).drop(columns="_o").reset_index(drop=True)
