from __future__ import annotations
import numpy as np
import pandas as pd

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    x = df.copy()
    close = x["Close"]
    for n in (9, 20):
        x[f"EMA{n}"] = close.ewm(span=n, adjust=False).mean()
    for n in (50, 200):
        x[f"SMA{n}"] = close.rolling(n).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    x["RSI14"] = 100 - (100 / (1 + rs))
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    x["MACD"] = ema12 - ema26
    x["MACD_SIGNAL"] = x["MACD"].ewm(span=9, adjust=False).mean()
    x["MACD_HIST"] = x["MACD"] - x["MACD_SIGNAL"]
    typical = (x["High"] + x["Low"] + close) / 3
    vol = x["Volume"].replace(0, np.nan)
    x["VWAP"] = (typical * vol).cumsum() / vol.cumsum()
    return x

def technical_snapshot(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 2:
        return {}
    x = add_indicators(df)
    last = x.iloc[-1]
    prev = x.iloc[-2]
    return {
        "Last close": float(last["Close"]),
        "Previous close": float(prev["Close"]),
        "Change %": float((last["Close"] / prev["Close"] - 1) * 100),
        "RSI (14)": float(last["RSI14"]) if pd.notna(last["RSI14"]) else None,
        "MACD": float(last["MACD"]) if pd.notna(last["MACD"]) else None,
        "EMA 20": float(last["EMA20"]) if pd.notna(last["EMA20"]) else None,
        "SMA 50": float(last["SMA50"]) if pd.notna(last["SMA50"]) else None,
        "SMA 200": float(last["SMA200"]) if pd.notna(last["SMA200"]) else None,
    }
