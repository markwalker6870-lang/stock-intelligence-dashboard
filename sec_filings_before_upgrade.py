from __future__ import annotations
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import streamlit as st
from data_sources import SEC_HEADERS, WATCHLIST

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
IMPORTANT_FORMS = {"8-K", "10-K", "10-Q", "4", "SC 13D", "SC 13G", "13D", "13G"}

@st.cache_data(ttl=86400, show_spinner=False)
def get_company_ciks() -> dict:
    r = requests.get(SEC_TICKERS_URL, headers=SEC_HEADERS, timeout=25)
    r.raise_for_status()
    payload = r.json()
    return {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in payload.values()}

@st.cache_data(ttl=1800, show_spinner=False)
def get_company_filings(ticker: str, limit: int = 40) -> pd.DataFrame:
    cik = get_company_ciks().get(ticker.upper())
    if not cik:
        return pd.DataFrame()
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    r = requests.get(url, headers=SEC_HEADERS, timeout=25)
    r.raise_for_status()
    data = r.json()
    recent = data.get("filings", {}).get("recent", {})
    rows = []
    forms = recent.get("form", [])
    for i, form in enumerate(forms):
        if form not in IMPORTANT_FORMS:
            continue
        accession = recent["accessionNumber"][i]
        primary = recent["primaryDocument"][i]
        accession_clean = accession.replace("-", "")
        doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_clean}/{primary}"
        rows.append({
            "Ticker": ticker.upper(), "Company": data.get("name", ticker),
            "Form": form, "Filing Date": recent["filingDate"][i],
            "Report Date": recent.get("reportDate", [""] * len(forms))[i],
            "Description": recent.get("primaryDocDescription", [""] * len(forms))[i],
            "Accession": accession, "URL": doc_url, "CIK": cik
        })
        if len(rows) >= limit:
            break
    return pd.DataFrame(rows)

def parse_form4_xml(url: str, ticker: str = "") -> list[dict]:
    r = requests.get(url, headers=SEC_HEADERS, timeout=25)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    def txt(node, path):
        el = node.find(path)
        return el.text.strip() if el is not None and el.text else ""
    owner = root.find(".//reportingOwner")
    owner_name = txt(owner, ".//rptOwnerName") if owner is not None else "Not stated"
    rows = []
    for tx in root.findall(".//nonDerivativeTransaction"):
        code = txt(tx, ".//transactionCoding/transactionCode")
        shares = txt(tx, ".//transactionAmounts/transactionShares/value")
        price = txt(tx, ".//transactionAmounts/transactionPricePerShare/value")
        date = txt(tx, ".//transactionDate/value")
        acquired = txt(tx, ".//transactionAmounts/transactionAcquiredDisposedCode/value")
        try:
            qty = float(shares) if shares else None
            px = float(price) if price else None
        except ValueError:
            qty, px = None, None
        rows.append({
            "Ticker": ticker, "Insider": owner_name, "Transaction Date": date,
            "Code": code, "Side": "Purchase" if acquired == "A" else "Sale" if acquired == "D" else "Other",
            "Shares": qty, "Price": px,
            "Estimated Value": qty * px if qty is not None and px is not None else None,
            "Source": url
        })
    return rows

@st.cache_data(ttl=1800, show_spinner=False)
def get_watchlist_filings() -> pd.DataFrame:
    frames = []
    for ticker in WATCHLIST:
        try:
            df = get_company_filings(ticker)
            if not df.empty:
                frames.append(df)
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["Filing Date"] = pd.to_datetime(out["Filing Date"], errors="coerce")
    return out.sort_values(["Filing Date", "Ticker"], ascending=[False, True]).reset_index(drop=True)

@st.cache_data(ttl=1800, show_spinner=False)
def get_watchlist_form4_transactions() -> pd.DataFrame:
    filings = get_watchlist_filings()
    if filings.empty:
        return pd.DataFrame()
    rows = []
    form4s = filings[filings["Form"] == "4"].head(60)
    for _, filing in form4s.iterrows():
        try:
            rows.extend(parse_form4_xml(filing["URL"], filing["Ticker"]))
        except Exception:
            continue
    df = pd.DataFrame(rows)
    if not df.empty:
        df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors="coerce")
        df = df.sort_values(["Transaction Date", "Ticker"], ascending=[False, True])
    return df
