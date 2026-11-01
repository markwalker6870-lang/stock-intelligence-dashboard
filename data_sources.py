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
                  "profitMargins", "debtToEquity", "returnOnEquity", "website"]
        return {k: info.get(k) for k in fields}
    except Exception:
        return {}

@st.cache_data(ttl=900, show_spinner=False)
def fetch_news_diagnostics(ticker: str) -> dict:
    """Fetch company news from Yahoo, Google News RSS, then Bing News RSS."""
    import xml.etree.ElementTree as ET
    from urllib.parse import quote

    items = []
    sources_checked = []
    errors = []
    query = quote(f"{ticker} stock")
    
    # Yahoo Finance is attempted first; its response format varies by yfinance version.
    sources_checked.append("Yahoo Finance")
    try:
        raw_items = yf.Ticker(ticker).news or []
        for raw in raw_items[:15]:
            content = raw.get("content", raw)
            title = content.get("title") or raw.get("title")
            url = content.get("canonicalUrl", {}).get("url") or raw.get("link") or ""
            provider = content.get("provider", {}).get("displayName") or raw.get("publisher") or "Yahoo Finance"
            if title and url:
                items.append({
                    "title": title, "url": url, "publisher": provider,
                    "published": content.get("pubDate") or raw.get("providerPublishTime") or "",
                    "source": "Yahoo Finance",
                })
    except Exception as exc:
        errors.append(f"Yahoo Finance: {type(exc).__name__}: {str(exc)[:180]}")

    if items:
        return {
            "items": items[:20], "sources_checked": sources_checked,
            "status": "Articles found", "diagnostic": "Yahoo Finance returned articles."
        }

    rss_sources = [
        (
            "Google News RSS",
            f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
        ),
        (
            "Bing News RSS",
            f"https://www.bing.com/news/search?q={query}&format=RSS",
        ),
    ]
    for source_name, url in rss_sources:
        sources_checked.append(source_name)
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; StockIntelligenceDashboard/1.0)"},
                timeout=15,
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
            parsed = []
            for entry in root.findall("./channel/item")[:15]:
                title = entry.findtext("title") or ""
                link = entry.findtext("link") or ""
                publisher = entry.findtext("source") or source_name
                published = entry.findtext("pubDate") or ""
                if title and link:
                    parsed.append({
                        "title": title, "url": link, "publisher": publisher,
                        "published": published, "source": source_name,
                    })
            if parsed:
                items.extend(parsed)
                break
            errors.append(f"{source_name}: feed responded but contained no readable articles")
        except Exception as exc:
            errors.append(f"{source_name}: {type(exc).__name__}: {str(exc)[:180]}")

    status = "Articles found" if items else "All sources unavailable or empty"
    diagnostic = " | ".join(errors) if errors else (
        "At least one configured source returned articles." if items
        else "Sources returned no articles and no detailed error."
    )
    return {
        "items": items[:30],
        "sources_checked": sources_checked,
        "status": status,
        "diagnostic": diagnostic,
    }


def fetch_news(ticker: str) -> list:
    """Backward-compatible simple news-list interface."""
    return fetch_news_diagnostics(ticker).get("items", [])

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
