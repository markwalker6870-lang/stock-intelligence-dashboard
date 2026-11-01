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
    """Fetch and clean company news from Yahoo Finance, Google News and Bing News."""
    import re
    import xml.etree.ElementTree as ET
    from urllib.parse import quote, urlsplit, urlunsplit, parse_qsl, urlencode

    symbol = ticker.upper().strip()
    query = quote(f'"{symbol}" stock')
    items = []
    sources_checked = []
    errors = []
    seen_urls = set()

    # These are data/product pages, not news reporting.
    excluded_url_terms = (
        "/options", "/option-chain", "/chart/", "/quote/",
        "/history", "/key-statistics", "/holders", "/profile",
    )
    excluded_title_patterns = (
        r"\b(stock price|price, news, quote|interactive stock chart|"
        r"stock options chain|option chain|historical data)\b",
    )

    def clean_url(value):
        if not value:
            return ""
        try:
            parts = urlsplit(value.strip())
            if parts.scheme not in ("http", "https") or not parts.netloc:
                return ""
            # Remove tracking parameters so syndicated copies collapse to one URL.
            tracking = {"utm_source", "utm_medium", "utm_campaign", "guccounter", "ocid"}
            query_items = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                           if k.lower() not in tracking and not k.lower().startswith("utm_")]
            return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"),
                               urlencode(query_items), ""))
        except Exception:
            return ""

    def add_item(title, url, publisher, published, source):
        title = re.sub(r"\s+", " ", str(title or "")).strip()
        url = clean_url(url)
        if not title or not url:
            return
        if any(term in url.lower() for term in excluded_url_terms):
            return
        if any(re.search(pattern, title, flags=re.I) for pattern in excluded_title_patterns):
            return
        key = url.lower()
        if key in seen_urls:
            return
        seen_urls.add(key)
        items.append({
            "title": title, "url": url,
            "publisher": str(publisher or source),
            "published": published or "", "source": source,
        })

    # Yahoo Finance response structure differs across yfinance releases.
    sources_checked.append("Yahoo Finance")
    try:
        raw_items = yf.Ticker(symbol).news or []
        for raw in raw_items[:20]:
            content = raw.get("content") or raw
            canonical = content.get("canonicalUrl") or {}
            provider = content.get("provider") or {}
            add_item(
                content.get("title") or raw.get("title"),
                canonical.get("url") or raw.get("link"),
                provider.get("displayName") or raw.get("publisher") or "Yahoo Finance",
                content.get("pubDate") or raw.get("providerPublishTime") or "",
                "Yahoo Finance",
            )
    except Exception as exc:
        errors.append(f"Yahoo Finance: {type(exc).__name__}: {str(exc)[:160]}")

    # Always supplement Yahoo with RSS so the watchlist is not dependent on one feed.
    rss_sources = [
        ("Google News RSS",
         f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"),
        ("Bing News RSS",
         f"https://www.bing.com/news/search?q={query}&format=RSS"),
    ]
    for source_name, feed_url in rss_sources:
        sources_checked.append(source_name)
        try:
            response = requests.get(
                feed_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; StockIntelligenceDashboard/1.0)"},
                timeout=12,
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
            entries = root.findall("./channel/item")
            before = len(items)
            for entry in entries[:20]:
                add_item(
                    entry.findtext("title"),
                    entry.findtext("link"),
                    entry.findtext("source") or source_name,
                    entry.findtext("pubDate") or "",
                    source_name,
                )
            if len(items) == before:
                errors.append(f"{source_name}: no new readable articles")
        except Exception as exc:
            errors.append(f"{source_name}: {type(exc).__name__}: {str(exc)[:160]}")

    # Newest first; leave undated entries at the bottom.
    if items:
        dated = []
        for item in items:
            try:
                stamp = pd.to_datetime(item["published"], errors="coerce", utc=True)
                # Yahoo providerPublishTime is Unix seconds, not nanoseconds.
                if isinstance(item["published"], (int, float)) and item["published"] > 10**9:
                    stamp = pd.to_datetime(item["published"], unit="s", errors="coerce", utc=True)
                dated.append(stamp)
            except Exception:
                dated.append(pd.NaT)
        for item, stamp in zip(items, dated):
            item["_sort_date"] = stamp
        items.sort(key=lambda x: x["_sort_date"] if pd.notna(x["_sort_date"]) else pd.Timestamp.min.tz_localize("UTC"),
                   reverse=True)
        for item in items:
            item.pop("_sort_date", None)

    status = "Articles found" if items else "No relevant articles found"
    diagnostic = " | ".join(errors) if errors else (
        "News feeds returned articles; duplicates and non-news quote/options pages were filtered."
        if items else "All configured sources returned no usable news."
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
