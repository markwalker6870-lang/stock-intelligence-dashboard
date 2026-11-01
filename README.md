# Stock Intelligence Dashboard

A Streamlit research dashboard for MP, CIFR, WULF, BCAX, INTC, CEG, VST and CCJ.

## Run locally / in Codespaces
```bash
pip install -r requirements.txt
streamlit run app.py
```

## SEC contact identity
Before using the SEC endpoints beyond light testing, edit `SEC_HEADERS` in `data_sources.py` and replace `contact@example.com` with a monitored contact email and an identifying app name. SEC fair-access guidance requires a descriptive User-Agent.

## Data limitations
- Yahoo Finance data may be delayed, incomplete, rate-limited, adjusted or unavailable for some tickers/intervals. It is not an exchange-grade real-time quote feed.
- Daily percentage changes compare the latest two daily bars returned by Yahoo Finance, not necessarily the live intraday move.
- SEC filings are fetched from EDGAR. Form 4 XML parsing is a convenience view; inspect the original filing, footnotes, transaction codes and ownership tables before drawing conclusions.
- Congressional disclosure data is not available through one complete, standardised official API. This dashboard supports CSV import and links to official House and Senate disclosure portals; it does not invent or silently scrape third-party trades.
- Fundamental and institutional ownership fields from Yahoo Finance may be stale or missing.

## Deploy
Push the repository to GitHub, then deploy `app.py` using Streamlit Community Cloud.
