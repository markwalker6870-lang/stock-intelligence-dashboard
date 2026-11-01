from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh

from data_sources import (
    WATCHLIST, fetch_history, fetch_quote, fetch_company_info,
    fetch_news_diagnostics, fetch_holders
)
from analysis import add_indicators, technical_snapshot
from sec_filings import (
    get_watchlist_filings,
    get_watchlist_form4_transactions,
    analyze_filing_document,
)
from congress_trades import load_congress_trades

st.set_page_config(page_title="Stock Intelligence Terminal", page_icon="📈", layout="wide")
st_autorefresh(interval=15 * 60 * 1000, key="market_refresh")

st.markdown("""
<style>
.block-container {padding-top: 1.4rem; max-width: 1600px;}
[data-testid="stMetric"] {background:#151C29; border:1px solid #263247; padding:14px; border-radius:10px;}
h1,h2,h3 {letter-spacing:-.3px;}
</style>
""", unsafe_allow_html=True)

st.title("Stock Intelligence Terminal")
st.caption("Institutional-style research workspace • Prices and public disclosures may be delayed")

with st.sidebar:
    st.header("Workspace")
    ticker = st.selectbox("Active company", WATCHLIST, index=0)
    chart_style = st.radio("Chart experience", ["TradingView-style", "Bloomberg-style"], horizontal=False)
    st.divider()
    st.caption("Watchlist")
    st.write(" · ".join(WATCHLIST))
    if st.button("Clear cached data and refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

tabs = st.tabs(["Market Overview", "Advanced Charts", "SEC Filings", "Insider Activity", "Fundamentals & Ownership", "News & Research", "Congressional Trades"])

with tabs[0]:
    st.subheader("Watchlist monitor")
    quotes = []
    for symbol in WATCHLIST:
        try:
            quotes.append(fetch_quote(symbol))
        except Exception:
            quotes.append({"ticker": symbol, "price": None, "change_pct": None, "volume": None, "asof": None})
    qdf = pd.DataFrame(quotes)
    cols = st.columns(4)
    for i, row in qdf.iterrows():
        with cols[i % 4]:
            price = f"${row['price']:,.2f}" if pd.notna(row["price"]) else "Unavailable"
            delta = f"{row['change_pct']:+.2f}%" if pd.notna(row["change_pct"]) else None
            st.metric(row["ticker"], price, delta)
    st.caption("Change compares the two latest daily bars returned by the data provider; it is not guaranteed to be a live real-time quote.")
    st.subheader("Latest available market data")
    st.dataframe(qdf.rename(columns={"ticker":"Ticker","price":"Last price (USD)","change_pct":"Daily change %","volume":"Volume","asof":"Bar timestamp"}), use_container_width=True, hide_index=True)


with tabs[1]:
    st.subheader("Advanced Trading Charts")
    st.caption("Technical analysis workspace • Yahoo Finance market data")

    chart_ticker = st.selectbox(
        "Select stock for chart",
        WATCHLIST,
        index=WATCHLIST.index(ticker) if ticker in WATCHLIST else 0,
        key="advanced_chart_ticker"
    )

    period_map = {
        "1D": ("1d", "5m"),
        "5D": ("5d", "15m"),
        "1M": ("1mo", "1d"),
        "3M": ("3mo", "1d"),
        "6M": ("6mo", "1d"),
        "1Y": ("1y", "1d"),
        "5Y": ("5y", "1wk"),
    }

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        timeframe = st.selectbox("Timeframe", list(period_map.keys()), index=5, key="advanced_timeframe")
    with c2:
        display = st.selectbox("Chart type", ["Candlestick", "Line"], key="advanced_display")
    with c3:
        indicators = st.multiselect(
            "Technical overlays",
            ["EMA 9", "EMA 20", "SMA 50", "SMA 200", "VWAP"],
            default=["EMA 20", "SMA 50"],
            key="advanced_overlays"
        )

    period, interval = period_map[timeframe]
    raw = fetch_history(chart_ticker, period, interval)
    df = add_indicators(raw) if not raw.empty else raw

    if df.empty:
        st.warning("No chart data returned by the provider.")
    else:
        fig = make_subplots(
            rows=4,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.035,
            row_heights=[0.53, 0.16, 0.15, 0.16],
            subplot_titles=("Price action", "Volume", "RSI (14)", "MACD (12, 26, 9)")
        )

        if display == "Candlestick":
            fig.add_trace(
                go.Candlestick(
                    x=df.index,
                    open=df["Open"],
                    high=df["High"],
                    low=df["Low"],
                    close=df["Close"],
                    name="Price",
                    increasing_line_color="#00C087",
                    decreasing_line_color="#F23645"
                ),
                row=1, col=1
            )
        else:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df["Close"],
                    name="Close",
                    line=dict(color="#579DFF", width=2)
                ),
                row=1, col=1
            )

        overlay_map = {
            "EMA 9": "EMA9",
            "EMA 20": "EMA20",
            "SMA 50": "SMA50",
            "SMA 200": "SMA200",
            "VWAP": "VWAP"
        }

        overlay_colors = {
            "EMA 9": "#FFD166",
            "EMA 20": "#00C2FF",
            "SMA 50": "#B58CFF",
            "SMA 200": "#FF9F43",
            "VWAP": "#F5D76E"
        }

        for label in indicators:
            column = overlay_map[label]
            if column in df and df[column].notna().any():
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df[column],
                        name=label,
                        line=dict(color=overlay_colors[label], width=1.4)
                    ),
                    row=1, col=1
                )

        volume_colors = [
            "#00C087" if close >= open_ else "#F23645"
            for open_, close in zip(df["Open"], df["Close"])
        ]

        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df["Volume"],
                name="Volume",
                marker_color=volume_colors,
                opacity=0.7
            ),
            row=2, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["RSI14"],
                name="RSI",
                line=dict(color="#B58CFF", width=1.6)
            ),
            row=3, col=1
        )

        fig.add_hline(y=70, line_dash="dot", line_color="#F23645", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#00C087", row=3, col=1)

        macd_colors = [
            "#00C087" if value >= 0 else "#F23645"
            for value in df["MACD_HIST"].fillna(0)
        ]

        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df["MACD_HIST"],
                name="MACD histogram",
                marker_color=macd_colors,
                opacity=0.65
            ),
            row=4, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["MACD"],
                name="MACD",
                line=dict(color="#579DFF", width=1.5)
            ),
            row=4, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["MACD_SIGNAL"],
                name="Signal",
                line=dict(color="#FFB74D", width=1.5)
            ),
            row=4, col=1
        )

        fig.add_hline(y=0, line_dash="dot", line_color="#777777", row=4, col=1)

        fig.update_layout(
            template="plotly_dark",
            height=1000,
            hovermode="x unified",
            paper_bgcolor="#0B0F17",
            plot_bgcolor="#0B0F17",
            margin=dict(l=15, r=15, t=55, b=20),
            legend=dict(orientation="h", y=1.02, x=0),
            title=f"{chart_ticker} • {timeframe} • Advanced Technical Analysis",
            xaxis_rangeslider_visible=False,
            uirevision=f"{chart_ticker}-{timeframe}-{display}"
        )

        fig.update_yaxes(title_text="Price (USD)", row=1, col=1)
        fig.update_yaxes(title_text="Volume", row=2, col=1)
        fig.update_yaxes(title_text="RSI", range=[0, 100], row=3, col=1)
        fig.update_yaxes(title_text="MACD", row=4, col=1)

        fig.update_xaxes(showgrid=True, gridcolor="#202938")
        fig.update_yaxes(showgrid=True, gridcolor="#202938")

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "scrollZoom": False,
                "displaylogo": False,
                "responsive": True,
                "displayModeBar": True
            }
        )

        snap = technical_snapshot(raw)
        if snap:
            st.subheader(f"{chart_ticker} • Technical snapshot")
            mcols = st.columns(4)
            for i, (key, value) in enumerate(snap.items()):
                val = f"{value:,.2f}" if isinstance(value, (int, float)) and value is not None else "—"
                mcols[i % 4].metric(key, val)



with tabs[2]:
    st.subheader("SEC Filing Intelligence Centre")
    st.caption(
        "Research public disclosures from SEC EDGAR. Automated screening "
        "identifies terms to investigate; it does not determine whether "
        "a filing is good or bad."
    )

    if st.button("Refresh SEC filings", key="sec_refresh"):
        st.cache_data.clear()
        st.rerun()

    try:
        filings = get_watchlist_filings()

        if filings.empty:
            st.info("No matching filings returned. Try refreshing later.")
        else:
            f1, f2, f3 = st.columns(3)

            with f1:
                sec_ticker = st.selectbox(
                    "Company",
                    ["All"] + WATCHLIST,
                    key="sec_company"
                )

            with f2:
                available_forms = sorted(
                    filings["Form"].dropna().unique()
                )
                forms = st.multiselect(
                    "Filing type",
                    available_forms,
                    default=available_forms,
                    key="sec_forms"
                )

            with f3:
                days_filter = st.selectbox(
                    "Filing date",
                    ["All available", "Last 30 days",
                     "Last 90 days", "Last 12 months"],
                    key="sec_date_filter"
                )

            view = filings.copy()

            if sec_ticker != "All":
                view = view[view["Ticker"] == sec_ticker]

            view = view[view["Form"].isin(forms)]

            if days_filter != "All available":
                days = {
                    "Last 30 days": 30,
                    "Last 90 days": 90,
                    "Last 12 months": 365
                }[days_filter]

                cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=days)
                view = view[view["Filing Date"] >= cutoff]

            view = view.sort_values(
                ["Filing Date", "Ticker"],
                ascending=[False, True]
            )

            m1, m2, m3 = st.columns(3)
            m1.metric("Matching filings", len(view))
            m2.metric("Companies represented", view["Ticker"].nunique())
            m3.metric("Filing types", view["Form"].nunique())

            st.divider()
            st.markdown("#### Filing history")

            display_columns = [
                "Filing Date", "Ticker", "Company", "Form",
                "Report Date", "Description", "URL"
            ]

            st.dataframe(
                view[display_columns],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "URL": st.column_config.LinkColumn(
                        "SEC document",
                        display_text="Open filing"
                    )
                }
            )

            st.divider()
            st.markdown("#### Investigate a filing")

            if not view.empty:
                options = view.reset_index(drop=True)

                def filing_label(row):
                    date = row["Filing Date"]
                    date_text = (
                        date.strftime("%Y-%m-%d")
                        if pd.notna(date) else "Date unavailable"
                    )
                    return (
                        f'{row["Ticker"]} | {row["Form"]} | '
                        f'{date_text} | {row["Description"] or "Filing"}'
                    )

                selected_index = st.selectbox(
                    "Choose a filing to screen",
                    range(len(options)),
                    format_func=lambda i: filing_label(options.iloc[i]),
                    key="sec_selected_filing"
                )

                selected = options.iloc[selected_index]

                st.markdown(
                    f'**{selected["Company"]} — {selected["Form"]}**'
                )
                st.markdown(
                    f'[Open original SEC filing]({selected["URL"]})'
                )

                if st.button(
                    "Screen selected filing",
                    key="screen_selected_sec_filing"
                ):
                    with st.spinner(
                        "Downloading and screening the SEC document..."
                    ):
                        result = analyze_filing_document(
                            selected["URL"],
                            selected["Form"]
                        )
                    st.session_state["sec_screen_result"] = {
                        "url": selected["URL"],
                        "result": result
                    }

                saved = st.session_state.get("sec_screen_result")

                if saved and saved.get("url") == selected["URL"]:
                    result = saved["result"]

                    st.markdown("#### Screening result")
                    st.caption(
                        f'Status: {result.get("status", "Unknown")} • '
                        f'Words scanned: {result.get("word_count", 0):,}'
                    )

                    st.write(result.get("summary", ""))

                    flags = result.get("risk_flags", [])

                    if flags:
                        st.warning(
                            "Potential risk-related wording found. "
                            "Read the context in the original filing."
                        )
                        st.dataframe(
                            pd.DataFrame(flags),
                            use_container_width=True,
                            hide_index=True
                        )

                        evidence = result.get("evidence", [])

                        if evidence:
                            st.markdown("#### Matching text excerpts")
                            for item in evidence:
                                with st.expander(
                                    f'{item["Category"]}: '
                                    f'{item["Matched term"]}'
                                ):
                                    st.write(item["Context"])
                    elif result.get("status") == "Screened":
                        st.success(
                            "No configured risk keywords were detected. "
                            "This does not mean the filing is risk-free."
                        )
                    else:
                        st.info(
                            result.get(
                                "limitation",
                                "The document could not be screened."
                            )
                        )

                    st.caption(
                        "Screening limitation: " +
                        result.get("limitation", "")
                    )

            else:
                st.info("No filings match your selected filters.")

    except Exception as e:
        st.error(f"SEC retrieval issue: {e}")

with tabs[3]:
    st.subheader("Form 4 insider transactions")
    st.caption("Transaction codes and ownership details must be checked in the source filing. Not every Form 4 is an open-market buy or sale.")
    try:
        tx = get_watchlist_form4_transactions()
        if tx.empty:
            st.info("No Form 4 transactions could be parsed at this time.")
        else:
            c1,c2 = st.columns(2)
            with c1: tx_ticker = st.selectbox("Company",["All"]+WATCHLIST,key="tx_ticker")
            with c2: side = st.multiselect("Reported disposition",sorted(tx["Acquired / Disposed"].dropna().unique()),default=sorted(tx["Acquired / Disposed"].dropna().unique()))
            view = tx.copy()
            if tx_ticker != "All": view = view[view["Ticker"] == tx_ticker]
            view = view[view["Acquired / Disposed"].isin(side)].sort_values("Transaction Date",ascending=False)
            view = view.rename(columns={"Acquired / Disposed": "Disposition"})
            st.dataframe(
                view,
                use_container_width=True,
                hide_index=True,
                height=500,
                column_config={
                    "Source": st.column_config.LinkColumn(
                        "Source filing",
                        display_text="Open Form 4"
                    ),
                    "Disposition": st.column_config.TextColumn("Disposition"),
                    "Shares": st.column_config.NumberColumn("Shares", format="%,.0f"),
                    "Price": st.column_config.NumberColumn("Price", format="$%.2f"),
                    "Estimated Value": st.column_config.NumberColumn("Estimated Value", format="$%,.0f"),
                }
            )
            st.caption("Code P generally denotes an open-market/private purchase; S generally denotes an open-market/private sale. Other codes can represent awards, exercises, gifts or tax withholding. Verify footnotes and ownership tables in the original filing.")
    except Exception as e:
        st.error(f"Form 4 parsing issue: {e}")

with tabs[4]:
    st.subheader("Fundamentals & ownership — watchlist comparison")
    st.caption("Compare all watchlist companies together. Provider fields can be missing, delayed or inconsistent between issuers.")
    fundamental_rows = []
    for symbol in WATCHLIST:
        try:
            item = fetch_company_info(symbol) or {}
            fundamental_rows.append({
                "Ticker": symbol,
                "Company": item.get("longName") or symbol,
                "Sector": item.get("sector") or "—",
                "Industry": item.get("industry") or "—",
                "Market cap (USD)": item.get("marketCap"),
                "Trailing P/E": item.get("trailingPE"),
                "Forward P/E": item.get("forwardPE"),
                "Profit margin": item.get("profitMargins"),
                "Debt / equity": item.get("debtToEquity"),
                "Return on equity": item.get("returnOnEquity"),
            })
        except Exception as exc:
            fundamental_rows.append({"Ticker": symbol, "Company": symbol, "Data status": str(exc)[:120]})
    fundamentals = pd.DataFrame(fundamental_rows)
    if not fundamentals.empty:
        st.dataframe(
            fundamentals,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Market cap (USD)": st.column_config.NumberColumn(format="$%.0f"),
                "Trailing P/E": st.column_config.NumberColumn(format="%.2f"),
                "Forward P/E": st.column_config.NumberColumn(format="%.2f"),
                "Profit margin": st.column_config.NumberColumn(format="%.1%"),
                "Debt / equity": st.column_config.NumberColumn(format="%.2f"),
                "Return on equity": st.column_config.NumberColumn(format="%.1%"),
            },
        )
    st.divider()
    st.markdown("#### Ownership details")
    holder_symbols = st.multiselect(
        "Companies to inspect",
        WATCHLIST,
        default=[ticker],
        key="fundamentals_holder_symbols",
    )
    for symbol in holder_symbols:
        st.markdown(f"**{symbol} — ownership**")
        holders = fetch_holders(symbol)
        h1, h2, h3 = st.tabs([
            f"{symbol} institutional", f"{symbol} major holders", f"{symbol} insider data"
        ])
        with h1:
            if holders["institutional"].empty:
                st.info("Institutional-holder data is not available from the current provider.")
            else:
                st.dataframe(holders["institutional"], use_container_width=True, hide_index=True)
        with h2:
            if holders["major"].empty:
                st.info("Major-holder data is not available from the current provider.")
            else:
                st.dataframe(holders["major"], use_container_width=True, hide_index=True)
        with h3:
            if holders["insiders"].empty:
                st.info("Provider insider-transaction data is not available.")
            else:
                st.dataframe(holders["insiders"], use_container_width=True, hide_index=True)

with tabs[5]:
    st.subheader("News & research — watchlist")
    news_symbols = st.multiselect(
        "Companies",
        WATCHLIST,
        default=WATCHLIST,
        key="news_watchlist_symbols",
    )
    if st.button("Refresh news feeds", key="refresh_news_feeds"):
        st.cache_data.clear()
        st.rerun()
    if not news_symbols:
        st.info("Select at least one company to view its news.")
    else:
        all_news = []
        source_status = []
        for symbol in news_symbols:
            result = fetch_news_diagnostics(symbol)
            source_status.append({
                "Ticker": symbol,
                "Articles": len(result.get("items", [])),
                "Sources checked": ", ".join(result.get("sources_checked", [])) or "None",
                "Status": result.get("status", "Unknown"),
                "Details": result.get("diagnostic", ""),
            })
            for item in result.get("items", []):
                all_news.append({**item, "Ticker": symbol})
        if all_news:
            news_df = pd.DataFrame(all_news).drop_duplicates(subset=["url"])
            if "published" in news_df:
                news_df["_sort_date"] = pd.to_datetime(news_df["published"], errors="coerce", utc=True)
                news_df = news_df.sort_values("_sort_date", ascending=False, na_position="last")
            for _, item in news_df.iterrows():
                title = str(item.get("title") or "Untitled article")
                url = str(item.get("url") or "")
                publisher = str(item.get("publisher") or "News source")
                published = str(item.get("published") or "")
                ticker_label = str(item.get("Ticker") or "")
                if url:
                    st.markdown(f"- **{ticker_label}** · [{title}]({url}) — *{publisher}* · {published}")
        else:
            st.warning("No articles were retrieved from the configured news sources.")
        with st.expander("News feed diagnostics"):
            st.dataframe(pd.DataFrame(source_status), use_container_width=True, hide_index=True)
    st.divider()
    st.markdown("**Research checklist**")
    st.write("- Read the latest 10-Q/10-K and any material 8-K.")
    st.write("- Compare reported results with guidance and cash-flow trends.")
    st.write("- Check dilution, debt maturities, liquidity and share-based compensation.")
    st.write("- Treat technical indicators as descriptive signals, not forecasts.")

with tabs[6]:
    st.subheader("Congressional trading disclosures — watchlist")
    st.warning(
        "Congressional disclosures are delayed and reported in value ranges. "
        "There is no single complete, standardised official real-time feed. "
        "Transactions below are shown only when supplied in an imported dataset."
    )
    st.markdown(
        "Official sources: [U.S. House financial disclosures](https://disclosures-clerk.house.gov/FinancialDisclosure) · "
        "[U.S. Senate eFD](https://efdsearch.senate.gov/search/)"
    )
    upload = st.file_uploader(
        "Import a congressional disclosure CSV",
        type=["csv"],
        help="Expected columns: Ticker, Member, Chamber, Transaction Date, Filed Date, Transaction Type, Amount Range, Source URL.",
    )
    try:
        congress = load_congress_trades(upload)
        if not congress.empty:
            congress_symbols = sorted(congress["Ticker"].dropna().unique().tolist())
            selected_congress_symbols = st.multiselect(
                "Filter by watchlist ticker",
                ["All"] + congress_symbols,
                default=["All"],
                key="congress_ticker_filter",
            )
            if selected_congress_symbols and "All" not in selected_congress_symbols:
                congress = congress[congress["Ticker"].isin(selected_congress_symbols)]
            st.metric("Disclosures in view", len(congress))
            st.dataframe(
                congress,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Source URL": st.column_config.LinkColumn("Disclosure", display_text="Open source")
                },
            )
        else:
            st.info(
                "No congressional transactions are loaded yet. Import a CSV from an official "
                "disclosure source or a data provider. We do not invent trades or scrape an "
                "unverified feed."
            )
    except Exception as e:
        st.error(f"Congressional CSV issue: {e}")

st.divider()
st.caption("Data quality note: Yahoo Finance data is not an exchange-grade real-time feed. SEC filings are primary-source disclosures. Congressional trades require source-by-source verification. This dashboard is for research, not financial advice.")
