"""Default parameters and thresholds.

Every number the scanner uses lives here. The dashboard sidebar can override
any of them, and "Save as default" writes the overrides to settings.json.
"""

import copy
import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "settings.json"

DEFAULTS = {
    # ---- Indicator parameters (spec section 2) ----
    "params": {
        "rsi_len": 14,
        "adx_len": 14,          # also used for +DI / -DI
        "ema_fast": 9,
        "ema_short": 20,
        "ema_mid": 50,
        "ema_long": 200,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "bb_len": 20,
        "bb_std": 2.0,
        "vol_avg_len": 20,
        "breakout_len": 20,
        "atr_len": 14,
    },

    # ---- Bullish thresholds (spec section 3) ----
    "bull_momentum": {"rsi_min": 55, "rsi_max": 65, "adx_min": 20, "rvol_min": 1.2},
    "bull_breakout": {"rsi_min": 55, "rsi_max": 68, "adx_min": 20, "rvol_min": 1.5,
                      "body_min_pct": 50},
    "bull_pullback": {"rsi_min": 40, "rsi_max": 52, "ema_dist_pct": 2.0},

    # ---- Bearish thresholds (spec section 4) ----
    "bear_momentum": {"rsi_min": 35, "rsi_max": 45, "adx_min": 20, "rvol_min": 1.2},
    "bear_breakdown": {"rsi_min": 32, "rsi_max": 45, "adx_min": 20, "rvol_min": 1.5,
                       "body_min_pct": 50},
    "bear_pullback": {"rsi_min": 48, "rsi_max": 60, "ema_dist_pct": 2.0},

    # ---- Trade plan (spec section 6) ----
    "trade": {
        "sl_atr_mult": 1.0,
        "t1_atr_mult": 1.0,
        "t2_atr_mult": 2.0,
        "min_rr": 2.0,          # R:R is measured at Target 2
    },

    # ---- Market timing (NSE, IST) ----
    "market": {
        "close_hhmm": "15:30",  # a candle dated today is treated as incomplete before this
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        elif k in out:
            out[k] = v
    return out


def load_settings() -> dict:
    """DEFAULTS overlaid with settings.json if it exists."""
    if SETTINGS_FILE.exists():
        try:
            return _deep_merge(DEFAULTS, json.loads(SETTINGS_FILE.read_text()))
        except (ValueError, OSError):
            pass
    return copy.deepcopy(DEFAULTS)


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


def reset_settings() -> None:
    if SETTINGS_FILE.exists():
        SETTINGS_FILE.unlink()


# Starting watchlist of large NSE stocks. Edit freely in the sidebar.
# Yahoo symbols use the ".NS" suffix, which the loader adds automatically.
DEFAULT_WATCHLIST = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "BHARTIARTL", "ITC", "LT",
    "SBIN", "KOTAKBANK", "AXISBANK", "HINDUNILVR", "BAJFINANCE", "MARUTI",
    "SUNPHARMA", "M&M", "HCLTECH", "NTPC", "TITAN", "ULTRACEMCO", "POWERGRID",
    "TATASTEEL", "ASIANPAINT", "BAJAJFINSV", "ADANIENT", "ADANIPORTS", "ONGC",
    "COALINDIA", "NESTLEIND", "JSWSTEEL", "TECHM", "WIPRO", "GRASIM", "HINDALCO",
    "CIPLA", "DRREDDY", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO", "APOLLOHOSP",
    "TRENT", "SHRIRAMFIN", "BEL", "INDUSINDBK", "SBILIFE", "HDFCLIFE",
    "TATACONSUM", "JIOFIN", "ETERNAL", "TMPV", "MAXHEALTH", "INDIGO",
]
