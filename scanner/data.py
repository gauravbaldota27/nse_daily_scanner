"""Daily NSE candles from Yahoo Finance, split into completed and in-progress candles."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd

IST = ZoneInfo("Asia/Kolkata")
HISTORY_PERIOD = "5y"   # long history so EMA200 is fully warmed up


def to_yahoo(symbol: str) -> str:
    s = symbol.strip().upper()
    if not s or s.startswith("^") or "." in s:
        return s
    return f"{s}.NS"


def parse_watchlist(text: str) -> list:
    raw = text.replace(",", "\n").replace(";", "\n").splitlines()
    seen, out = set(), []
    for item in raw:
        s = item.strip().upper()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index = df.index.normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df["Volume"] = df["Volume"].fillna(0).astype(float)
    return df


def download(symbols: list) -> tuple[dict, list]:
    """Returns ({symbol: OHLCV frame}, [failed symbols])."""
    import yfinance as yf

    tickers = {sym: to_yahoo(sym) for sym in symbols}
    raw = yf.download(list(tickers.values()), period=HISTORY_PERIOD, interval="1d",
                      group_by="ticker", auto_adjust=False, progress=False, threads=True)
    frames, failed = {}, []
    for sym, tk in tickers.items():
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                lvl0 = raw.columns.get_level_values(0)
                part = raw[tk] if tk in lvl0 else raw.xs(tk, axis=1, level=1)
            else:
                part = raw
            df = _clean(part)
            if len(df) == 0:
                raise ValueError("no rows")
            frames[sym] = df
        except Exception:
            failed.append(sym)
    return frames, failed


def now_ist() -> datetime:
    return datetime.now(IST)


def split_completed(df: pd.DataFrame, close_hhmm: str = "15:30",
                    now: datetime | None = None) -> tuple[pd.DataFrame, pd.Series | None]:
    """Split off today's candle if the NSE session has not closed yet.

    Returns (completed candles, in-progress candle or None). Confirmed signals
    must only ever be computed from the first element.
    """
    now = now or now_ist()
    if len(df) == 0:
        return df, None
    hh, mm = (int(x) for x in close_hhmm.split(":"))
    last_date = df.index[-1].date()
    if last_date == now.date() and now.time() < time(hh, mm):
        live = df.iloc[-1]
        if live["Volume"] <= 0:          # pre-open placeholder bar
            return df.iloc[:-1], None
        return df.iloc[:-1], live
    return df, None
