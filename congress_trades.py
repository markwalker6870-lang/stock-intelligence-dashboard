"""
Congressional trading disclosures.

Congressional disclosures are not published through a single reliable,
standardised real-time API. This module deliberately does not fabricate
transactions or scrape an unstable third-party feed.

It supports importing a CSV you obtain from official House/Senate disclosure
records or a licensed data provider. Expected columns:
Ticker, Member, Chamber, Transaction Date, Filed Date, Transaction Type,
Amount Range, Source URL
"""
from __future__ import annotations
import pandas as pd

REQUIRED_COLUMNS = [
    "Ticker", "Member", "Chamber", "Transaction Date", "Filed Date",
    "Transaction Type", "Amount Range", "Source URL"
]

def load_congress_trades(uploaded_file) -> pd.DataFrame:
    if uploaded_file is None:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    df = pd.read_csv(uploaded_file)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("CSV is missing columns: " + ", ".join(missing))
    df = df[REQUIRED_COLUMNS].copy()
    df["Ticker"] = df["Ticker"].astype(str).str.upper().str.strip()
    df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors="coerce")
    df["Filed Date"] = pd.to_datetime(df["Filed Date"], errors="coerce")
    return df.sort_values(["Filed Date", "Transaction Date"], ascending=False)
