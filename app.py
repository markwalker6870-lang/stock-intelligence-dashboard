
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Stock Intelligence Dashboard",
    page_icon="📈",
    layout="wide"
)

# Refresh every 15 minutes
st_autorefresh(interval=15 * 60 * 1000, key="refresh")

st.title("📈 Stock Intelligence Dashboard")
st.caption("Live market monitoring | Automatic refresh: 15 minutes")

stocks = ["MP", "CIFR", "WULF", "BCAX", "INTC", "CEG", "VST", "CCJ"]

@st.cache_data(ttl=60)
def get_stock_data(ticker):
    stock = yf.Ticker(ticker)
    history = stock.history(period="5d")
    return history

st.subheader("Your Watchlist")

cols = st.columns(4)

for i, ticker in enumerate(stocks):
    try:
        data = get_stock_data(ticker)

        if not data.empty:
            price = data["Close"].iloc[-1]
            previous = data["Close"].iloc[-2] if len(data) > 1 else price
            change = ((price - previous) / previous) * 100

            with cols[i % 4]:
                st.metric(
                    ticker,
                    f"${price:.2f}",
                    f"{change:.2f}%"
                )
        else:
            with cols[i % 4]:
                st.warning(f"{ticker}: No data")
    except Exception as e:
        with cols[i % 4]:
            st.error(f"{ticker}: Data unavailable")

st.divider()
st.subheader("Stock Price Charts")

selected = st.selectbox("Select stock", stocks)

try:
    chart_data = get_stock_data(selected)

    if not chart_data.empty:
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=chart_data.index,
            y=chart_data["Close"],
            mode="lines",
            name=selected
        ))

        fig.update_layout(
            title=f"{selected} Price History",
            xaxis_title="Date",
            yaxis_title="Price (USD)",
            template="plotly_dark"
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No historical data available.")
except Exception as e:
    st.error(f"Unable to load chart: {e}")

st.caption("Market data provided by Yahoo Finance. Prices may be delayed.")
