"""Rule tests. Run:  python -m pytest -q"""

import copy
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scanner.config import DEFAULTS                       # noqa: E402
from scanner.data import IST, split_completed               # noqa: E402
from scanner.signals import evaluate, evaluate_setups, trade_plan  # noqa: E402

S = copy.deepcopy(DEFAULTS)
DATE = pd.Timestamp("2026-11-13")


def row(**kw):
    base = dict(Open=100.0, High=106.0, Low=99.0, Close=105.0, Volume=2_000_000.0,
                rsi=60.0, adx=25.0, plus_di=30.0, minus_di=15.0,
                ema9=104.0, ema20=102.0, ema50=98.0, ema200=90.0, ema_short_prev=101.5,
                macd=1.0, macd_signal=0.5, atr=3.0, vol_avg=1_500_000.0, rvol=2_000_000 / 1_500_000,
                high_n=104.5, low_n=95.0, prev_high=104.0, prev_low=100.0, body_pct=5 / 7 * 100)
    base.update(kw)
    return pd.Series(base, name=DATE)


def bear_row(**kw):
    base = dict(Open=100.0, High=101.0, Low=94.0, Close=95.0, Volume=2_000_000.0,
                rsi=40.0, adx=25.0, plus_di=15.0, minus_di=30.0,
                ema9=96.0, ema20=98.0, ema50=102.0, ema200=110.0, ema_short_prev=98.5,
                macd=-1.0, macd_signal=-0.5, atr=3.0, vol_avg=1_500_000.0, rvol=2_000_000 / 1_500_000,
                high_n=105.0, low_n=95.5, prev_high=100.0, prev_low=96.0, body_pct=5 / 7 * 100)
    base.update(kw)
    return pd.Series(base, name=DATE)


def frame_with(last: pd.Series, n=210) -> pd.DataFrame:
    """History of n-1 dummy rows ending in `last` (only the last row is evaluated)."""
    idx = pd.bdate_range(end=DATE, periods=n)
    df = pd.DataFrame([last.values] * n, columns=last.index, index=idx)
    return df


def test_bull_momentum_and_breakout_fire():
    su = evaluate_setups(row(), S)
    assert su["bull_momentum"].passed, su["bull_momentum"].failing
    su = evaluate_setups(row(rvol=1.6), S)
    assert su["bull_breakout"].passed, su["bull_breakout"].failing


def test_breakout_needs_rvol_1_5():
    su = evaluate_setups(row(rvol=1.4), S)
    assert su["bull_momentum"].passed
    assert not su["bull_breakout"].passed
    assert su["bull_breakout"].failing == ["RVOL ≥ 1.5"]


def test_status_mapping_breakout_is_strong():
    ev = evaluate(frame_with(row(rvol=1.6)), S)
    assert ev.status == "STRONG BULLISH"
    ev = evaluate(frame_with(row(rvol=1.3)), S)
    assert ev.status == "BULLISH"


def test_rsi_band_edges_inclusive():
    assert evaluate_setups(row(rsi=55.0), S)["bull_momentum"].passed
    assert evaluate_setups(row(rsi=65.0), S)["bull_momentum"].passed
    assert not evaluate_setups(row(rsi=65.01), S)["bull_momentum"].passed
    assert evaluate_setups(row(rsi=68.0, rvol=1.6), S)["bull_breakout"].passed


def test_bull_pullback():
    r = row(rsi=48.0, Close=102.5, Open=101.0, High=103.0, Low=100.5, prev_high=102.0,
            Volume=1_000_000.0, rvol=1_000_000 / 1_500_000)
    su = evaluate_setups(r, S)
    assert su["bull_pullback"].passed, su["bull_pullback"].failing
    ev = evaluate(frame_with(r), S)
    assert ev.status == "BULLISH PULLBACK"
    # today's volume above average -> fails
    r2 = r.copy(); r2["Volume"] = 1_600_000.0
    assert not evaluate_setups(r2, S)["bull_pullback"].passed


def test_bear_setups():
    ev = evaluate(frame_with(bear_row(rvol=1.6)), S)
    assert ev.status == "STRONG BEARISH", [ev.setups[k].failing for k in ev.setups]
    ev = evaluate(frame_with(bear_row(rvol=1.3)), S)
    assert ev.status == "BEARISH"
    r = bear_row(rsi=52.0, Close=97.5, Open=99.0, High=99.5, Low=97.0, prev_low=98.0,
                 Volume=1_000_000.0, rvol=0.67)
    assert evaluate(frame_with(r), S).status == "BEARISH PULLBACK"


def test_trade_plan_long_and_short():
    p = trade_plan(row(), "bull_momentum", S)
    assert (p.entry, p.stop, p.t1, p.t2) == (105.0, 102.0, 108.0, 111.0)
    assert abs(p.rr - 2.0) < 1e-12 and p.valid
    q = trade_plan(bear_row(), "bear_momentum", S)
    assert (q.entry, q.stop, q.t1, q.t2) == (95.0, 98.0, 92.0, 89.0)
    assert q.valid


def test_rr_rejection_gives_no_trade():
    s = copy.deepcopy(S)
    s["trade"]["t2_atr_mult"] = 1.5
    ev = evaluate(frame_with(row()), s)
    assert ev.status == "NO TRADE" and not ev.plan.valid


def test_wait_for_confirmation_when_trigger_missing():
    r = row(Close=103.5, prev_high=104.0, high_n=104.5)   # trend aligned, no close above prev high
    ev = evaluate(frame_with(r), S)
    assert ev.status == "WAIT FOR CONFIRMATION"
    assert ev.waiting_for in ("bull_breakout", "bull_momentum")


def test_neutral():
    r = row(rsi=50.0, ema20=97.0, ema50=98.0, plus_di=15.0, minus_di=16.0, adx=12.0)
    assert evaluate(frame_with(r), S).status == "NEUTRAL"


def test_not_enough_history():
    assert evaluate(frame_with(row(), n=100), S).status == "NO TRADE"


def test_live_candle_never_confirms():
    # completed candle neutral, today's open candle meets a setup -> WAIT, not BULLISH
    neutral = row(rsi=50.0, ema20=97.0, ema50=98.0, plus_di=15.0, minus_di=16.0, adx=12.0)
    ev = evaluate(frame_with(neutral), S, live_row=row())
    assert ev.status == "WAIT FOR CONFIRMATION"


def test_split_completed_handles_session_time():
    idx = pd.bdate_range(end="2026-11-16", periods=5)
    df = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 10.0}, index=idx)
    during = datetime(2026, 11, 16, 11, 0, tzinfo=IST)
    after = datetime(2026, 11, 16, 16, 0, tzinfo=IST)
    done, live = split_completed(df, "15:30", during)
    assert len(done) == 4 and live is not None
    done, live = split_completed(df, "15:30", after)
    assert len(done) == 5 and live is None


def test_indicators_are_causal():
    """Adding a future candle must not change past indicator values."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from scanner.indicators import compute_all
    rng = np.random.default_rng(0)
    n = 400
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    df = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c,
                       "Volume": rng.integers(1, 10, n) * 1e5},
                      index=pd.bdate_range(end="2026-11-13", periods=n))
    a = compute_all(df.iloc[:-1], S["params"])
    b = compute_all(df, S["params"]).iloc[:-1]
    pd.testing.assert_frame_equal(a, b)
