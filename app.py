
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


from plotly.subplots import make_subplots

st.divider()
st.header("📊 Professional Market Charts")

col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    selected = st.selectbox("Select ticker", stocks)

with col2:
    timeframe = st.selectbox(
        "Timeframe",
        ["1D", "5D", "1M", "3M", "6M", "1Y"],
        index=3
    )

with col3:
    chart_type = st.selectbox(
        "Chart type",
        ["Candlestick", "Line"]
    )

periods = {
    "1D": ("1d", "5m"),
    "5D": ("5d", "15m"),
    "1M": ("1mo", "1d"),
    "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"),
    "1Y": ("1y", "1d")
}

period, interval = periods[timeframe]

@st.cache_data(ttl=900)
def get_chart_data(ticker, period, interval):
    return yf.Ticker(ticker).history(
        period=period,
        interval=interval
    )

try:
    df = get_chart_data(selected, period, interval)

    if not df.empty:

        df = df.copy()
        df["MA20"] = df["Close"].rolling(20).mean()
        df["MA50"] = df["Close"].rolling(50).mean()

        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.04,
            row_heights=[0.75, 0.25]
        )

        if chart_type == "Candlestick":
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
                    mode="lines",
                    name="Price",
                    line=dict(color="#2962FF", width=2)
                ),
                row=1, col=1
            )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["MA20"],
                name="20 MA",
                line=dict(color="#F5A623", width=1.5)
            ),
            row=1, col=1
        )

        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["MA50"],
                name="50 MA",
                line=dict(color="#A78BFA", width=1.5)
            ),
            row=1, col=1
        )

        colors = [
            "#00C087" if c >= o else "#F23645"
            for o, c in zip(df["Open"], df["Close"])
        ]

        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df["Volume"],
                marker_color=colors,
                name="Volume",
                opacity=0.7
            ),
            row=2, col=1
        )

        fig.update_layout(
            template="plotly_dark",
            height=700,
            title=dict(
                text=f"{selected} | Market Price & Volume",
                x=0.02,
                font=dict(size=21)
            ),
            paper_bgcolor="#0E1117",
            plot_bgcolor="#0E1117",
            font=dict(
                family="Arial",
                color="#D1D4DC"
            ),
            margin=dict(l=20, r=20, t=65, b=20),
            hovermode="x unified",
            xaxis_rangeslider_visible=False,
            legend=dict(
                orientation="h",
                y=1.02,
                x=0
            )
        )

        fig.update_xaxes(
            showgrid=True,
            gridcolor="#252A35",
            showspikes=True,
            spikemode="across"
        )

        fig.update_yaxes(
            showgrid=True,
            gridcolor="#252A35"
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displayModeBar": True,
                "scrollZoom": True,
                "displaylogo": False
            }
        )

    else:
        st.warning("No chart data available for this ticker.")

except Exception as e:
    st.error(f"Chart error: {e}")
