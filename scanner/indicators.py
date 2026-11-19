"""Daily indicators, calculated the way TradingView does.

EMA and Wilder's moving average (RMA) are seeded with a simple average of the
first N values, as TradingView's ta.ema / ta.rma are. RSI, ADX, +DI, -DI and
ATR all use Wilder smoothing.

Input: a DataFrame indexed by date with columns Open, High, Low, Close, Volume.
"""

import numpy as np
import pandas as pd


def _seeded_smooth(values: pd.Series, length: int, alpha: float) -> pd.Series:
    """Recursive average seeded with the SMA of the first `length` valid values."""
    x = values.to_numpy(dtype=float)
    out = np.full(len(x), np.nan)
    valid = np.flatnonzero(~np.isnan(x))
    if len(valid) < length:
        return pd.Series(out, index=values.index)
    start = valid[0]
    # first index where `length` consecutive valid values are available
    seed_end = start + length - 1
    if np.isnan(x[start:seed_end + 1]).any():
        # gaps inside the warm-up window: fall back to the first clean window
        run = 0
        seed_end = None
        for i in range(start, len(x)):
            run = run + 1 if not np.isnan(x[i]) else 0
            if run == length:
                seed_end = i
                break
        if seed_end is None:
            return pd.Series(out, index=values.index)
    out[seed_end] = x[seed_end - length + 1:seed_end + 1].mean()
    prev = out[seed_end]
    for i in range(seed_end + 1, len(x)):
        if np.isnan(x[i]):
            out[i] = prev
            continue
        prev = alpha * x[i] + (1 - alpha) * prev
        out[i] = prev
    return pd.Series(out, index=values.index)


def ema(series: pd.Series, length: int) -> pd.Series:
    return _seeded_smooth(series, length, 2.0 / (length + 1))


def rma(series: pd.Series, length: int) -> pd.Series:
    """Wilder's moving average."""
    return _seeded_smooth(series, length, 1.0 / length)


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    change = close.diff()
    gain = rma(change.clip(lower=0), length)
    loss = rma((-change).clip(lower=0), length)
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    out[(loss == 0) & gain.notna()] = 100.0
    out[(gain == 0) & (loss == 0)] = 50.0
    return out


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    tr.iloc[0] = df["High"].iloc[0] - df["Low"].iloc[0]
    return tr


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    return rma(true_range(df), length)


def dmi(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    """Returns +DI, -DI and ADX (TradingView ta.dmi)."""
    up = df["High"].diff()
    down = -df["Low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    plus_dm.iloc[0] = np.nan
    minus_dm.iloc[0] = np.nan
    tr = true_range(df).copy()
    tr.iloc[0] = np.nan
    tr_s = rma(tr, length)
    plus_di = 100 * rma(plus_dm, length) / tr_s
    minus_di = 100 * rma(minus_dm, length) / tr_s
    denom = plus_di + minus_di
    dx = 100 * (plus_di - minus_di).abs() / denom.replace(0, np.nan)
    adx = rma(dx, length)
    return pd.DataFrame({"plus_di": plus_di, "minus_di": minus_di, "adx": adx})


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


def bollinger(close: pd.Series, length: int = 20, mult: float = 2.0) -> pd.DataFrame:
    mid = close.rolling(length).mean()
    sd = close.rolling(length).std(ddof=0)   # population SD, as TradingView
    return pd.DataFrame({"bb_mid": mid, "bb_upper": mid + mult * sd, "bb_lower": mid - mult * sd})


def compute_all(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Add every indicator column the scanner needs. `p` is settings['params']."""
    out = df.copy()
    c = out["Close"]

    out["rsi"] = rsi(c, p["rsi_len"])
    out = out.join(dmi(out, p["adx_len"]))
    for key in ("ema_fast", "ema_short", "ema_mid", "ema_long"):
        out[f"ema{p[key]}"] = ema(c, p[key])
    out = out.join(macd(c, p["macd_fast"], p["macd_slow"], p["macd_signal"]))
    out = out.join(bollinger(c, p["bb_len"], p["bb_std"]))
    out["atr"] = atr(out, p["atr_len"])

    # Volume average of the previous N sessions (today excluded), so today's
    # volume is compared against a baseline it is not part of.
    out["vol_avg"] = out["Volume"].shift(1).rolling(p["vol_avg_len"]).mean()
    out["rvol"] = out["Volume"] / out["vol_avg"]

    # Highest high / lowest low of the previous N sessions (today excluded).
    n = p["breakout_len"]
    out["high_n"] = out["High"].shift(1).rolling(n).max()
    out["low_n"] = out["Low"].shift(1).rolling(n).min()

    out["prev_high"] = out["High"].shift(1)
    out["prev_low"] = out["Low"].shift(1)
    out["ema_short_prev"] = out[f"ema{p['ema_short']}"].shift(1)

    rng = out["High"] - out["Low"]
    out["body_pct"] = np.where(rng > 0, (out["Close"] - out["Open"]).abs() / rng * 100, 0.0)
    return out
