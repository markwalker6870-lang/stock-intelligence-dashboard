from __future__ import annotations
import time
import requests
import pandas as pd
import yfinance as yf
import streamlit as st

WATCHLIST = ["MP", "CIFR", "WULF", "BCAX", "INTC", "CEG", "VST", "CCJ"]
SEC_HEADERS = {
    "User-Agent": "StockIntelligenceDashboard Mark Walker markwalker6870@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("America/New_York")
    return df.dropna(subset=["Close"])

@st.cache_data(ttl=180, show_spinner=False)
def fetch_quote(ticker: str) -> dict:
    df = fetch_history(ticker, "5d", "1d")
    if df.empty:
        return {"ticker": ticker, "price": None, "change_pct": None, "volume": None, "asof": None}
    last = df.iloc[-1]
    prior = df.iloc[-2] if len(df) > 1 else last
    prev_close = float(prior["Close"]) if pd.notna(prior["Close"]) else None
    price = float(last["Close"])
    change = ((price / prev_close) - 1) * 100 if prev_close else None
    return {
        "ticker": ticker, "price": price, "change_pct": change,
        "volume": int(last["Volume"]) if pd.notna(last["Volume"]) else None,
        "asof": str(df.index[-1])
    }

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_company_info(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).get_info()
        fields = ["longName", "sector", "industry", "marketCap", "trailingPE",
                  "forwardPE", "priceToBook", "enterpriseToEbitda", "totalRevenue",
                  "profitMargins", "debtToEquity", "returnOnEquity", "website",
                  "revenueGrowth", "operatingMargins", "currentRatio"]
        return {k: info.get(k) for k in fields}
    except Exception:
        return {}

@st.cache_data(ttl=900, show_spinner=False)
def fetch_news(ticker: str) -> list:
    """Get Yahoo Finance news, with Google News RSS as a fallback."""
    out = []
    try:
        items = yf.Ticker(ticker).news or []
        for item in items[:15]:
            content = item.get("content", item)
            title = content.get("title") or item.get("title")
            if not title:
                continue
            url = content.get("canonicalUrl", {}).get("url") or item.get("link") or ""
            provider = content.get("provider", {}).get("displayName") or item.get("publisher") or "Yahoo Finance"
            if url:
                out.append({"title": title, "url": url, "publisher": provider, "published": ""})
    except Exception:
        pass

    if out:
        return out

    try:
        import xml.etree.ElementTree as ET
        from urllib.parse import quote
        query = quote(f"{ticker} stock")
        response = requests.get(
            f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
            headers={"User-Agent": "Mozilla/5.0 StockIntelligenceDashboard/1.0"},
            timeout=12,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        for item in root.findall("./channel/item")[:15]:
            title = item.findtext("title") or ""
            url = item.findtext("link") or ""
            publisher = item.findtext("source") or "Google News"
            published = item.findtext("pubDate") or ""
            if title and url:
                out.append({"title": title, "url": url, "publisher": publisher, "published": published})
    except Exception:
        pass
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_holders(ticker: str) -> dict:
    try:
        obj = yf.Ticker(ticker)
        major = obj.major_holders
        inst = obj.institutional_holders
        insiders = obj.insider_transactions
        return {
            "major": major if major is not None else pd.DataFrame(),
            "institutional": inst if inst is not None else pd.DataFrame(),
            "insiders": insiders if insiders is not None else pd.DataFrame()
        }
    except Exception:
        return {"major": pd.DataFrame(), "institutional": pd.DataFrame(), "insiders": pd.DataFrame()}
