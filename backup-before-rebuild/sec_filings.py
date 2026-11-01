
import requests
import pandas as pd
import streamlit as st

SEC_USER_AGENT = "StockIntelligenceDashboard Markwalker markwalker6870@gmail.com"

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

WATCHLIST = [
    "MP", "CIFR", "WULF", "BCAX",
    "INTC", "CEG", "VST", "CCJ"
]

IMPORTANT_FORMS = [
    "8-K", "10-K", "10-Q", "4",
    "SC 13D", "SC 13G", "13D", "13G"
]


@st.cache_data(ttl=3600)
def get_company_ciks():
    headers = {"User-Agent": SEC_USER_AGENT}

    response = requests.get(
        SEC_TICKERS_URL,
        headers=headers,
        timeout=20
    )
    response.raise_for_status()

    companies = response.json()

    return {
        item["ticker"].upper(): str(item["cik_str"]).zfill(10)
        for item in companies.values()
    }


def get_company_filings(ticker, limit=20):
    headers = {"User-Agent": SEC_USER_AGENT}

    cik_map = get_company_ciks()
    ticker = ticker.upper()

    if ticker not in cik_map:
        return pd.DataFrame()

    cik = cik_map[ticker]

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    response = requests.get(
        url,
        headers=headers,
        timeout=20
    )
    response.raise_for_status()

    data = response.json()
    recent = data.get("filings", {}).get("recent", {})

    filings = []

    count = len(recent.get("form", []))

    for i in range(count):
        form = recent["form"][i]

        if form not in IMPORTANT_FORMS:
            continue

        accession = recent["accessionNumber"][i]
        document = recent["primaryDocument"][i]

        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/{accession.replace('-', '')}/{document}"
        )

        filings.append({
            "Ticker": ticker,
            "Company": data.get("name", ticker),
            "Form": form,
            "Filing Date": recent["filingDate"][i],
            "Description": recent.get(
                "primaryDocDescription", [""] * count
            )[i],
            "URL": filing_url
        })

    return pd.DataFrame(filings).head(limit)


def get_watchlist_filings():
    all_filings = []

    for ticker in WATCHLIST:
        try:
            df = get_company_filings(ticker)

            if not df.empty:
                all_filings.append(df)

        except Exception as e:
            st.warning(f"SEC issue for {ticker}: {e}")

    if not all_filings:
        return pd.DataFrame()

    result = pd.concat(all_filings, ignore_index=True)

    return result.sort_values(
        "Filing Date",
        ascending=False
    )
