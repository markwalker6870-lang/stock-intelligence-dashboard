from __future__ import annotations
import math
import numpy as np
import pandas as pd
import streamlit as st
from data_sources import WATCHLIST, fetch_history, fetch_company_info, fetch_news
from analysis import add_indicators

st.set_page_config(page_title="AI Stock Picker", page_icon="🧠", layout="wide")
st.title("AI Stock Picker")
st.caption("Explainable multi-factor scanner • Shortlist candidates, never automatic buy signals")

UNIVERSE = sorted(set(WATCHLIST + ["RSKD", "CRWV", "NBIS"]))
POS = {"guidance raised": 3, "raises outlook": 3, "beats estimates": 3, "record revenue": 2,
       "contract": 2, "partnership": 1, "approval": 2, "cash flow positive": 2,
       "strong demand": 2, "backlog": 1, "analyst upgrade": 1}
NEG = {"guidance cut": -4, "cuts outlook": -4, "misses estimates": -3, "offering": -3,
       "dilution": -3, "going concern": -5, "investigation": -3, "lawsuit": -2,
       "downgrade": -2, "weak demand": -2, "default": -5}

def num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def technical_score(hist):
    if hist.empty or len(hist) < 60:
        return 0, ["Insufficient history"], {}
    x = add_indicators(hist.copy())
    z = x.iloc[-1]
    p = num(z.get("Close"))
    if not p:
        return 0, ["Price unavailable"], {}
    score, why = 0, []
    for col, pts, label in [("EMA20", 8, "Above 20-day EMA"), ("SMA50", 8, "Above 50-day SMA"),
                            ("SMA200", 8, "Above 200-day SMA")]:
        v = num(z.get(col))
        if v and p > v:
            score += pts; why.append(label)
    s50, s200 = num(z.get("SMA50")), num(z.get("SMA200"))
    if s50 and s200 and s50 > s200:
        score += 5; why.append("50-day trend above 200-day trend")
    macd, sig = num(z.get("MACD")), num(z.get("MACD_SIGNAL"))
    if macd is not None and sig is not None and macd > sig:
        score += 5; why.append("MACD bullish")
    rsi = num(z.get("RSI14"))
    if rsi is not None:
        if 50 <= rsi <= 68:
            score += 6; why.append(f"Constructive RSI ({rsi:.0f})")
        elif 40 <= rsi < 50:
            score += 3; why.append(f"Recovering RSI ({rsi:.0f})")
        elif rsi > 75:
            score -= 4; why.append(f"RSI stretched ({rsi:.0f})")
    r20 = p / num(x["Close"].iloc[-21]) - 1 if len(x) >= 21 and num(x["Close"].iloc[-21]) else 0
    r60 = p / num(x["Close"].iloc[-61]) - 1 if len(x) >= 61 and num(x["Close"].iloc[-61]) else 0
    if r20 > .08: score += 4; why.append("Strong 1-month momentum")
    elif r20 < -.08: score -= 3; why.append("Weak 1-month momentum")
    if r60 > .15: score += 4; why.append("Strong 3-month momentum")
    elif r60 < -.15: score -= 3; why.append("Weak 3-month momentum")
    return max(0, min(40, score)), why, {"Price": p, "RSI": rsi, "20D return %": r20*100,
        "60D return %": r60*100, "EMA20": num(z.get("EMA20")), "SMA50": s50, "SMA200": s200}

def fundamental_score(info):
    score, good, risk = 0, [], []
    rg, pm = num(info.get("revenueGrowth")), num(info.get("profitMargins"))
    op, de, cr = num(info.get("operatingMargins")), num(info.get("debtToEquity")), num(info.get("currentRatio"))
    if rg is not None:
        if rg >= .25: score += 8; good.append(f"Revenue growth {rg:.0%}")
        elif rg >= .10: score += 5; good.append(f"Revenue growth {rg:.0%}")
        elif rg < 0: risk.append(f"Revenue declining ({rg:.0%})")
    if pm is not None:
        if pm > .10: score += 6; good.append("Healthy positive net margin")
        elif pm > 0: score += 4; good.append("Positive net margin")
        elif pm < 0: risk.append("Currently unprofitable")
    if op is not None and op > 0: score += 4; good.append("Positive operating margin")
    if de is not None:
        if de < 50: score += 5; good.append("Low reported debt/equity")
        elif de > 200: risk.append("High debt/equity")
    if cr is not None:
        if cr >= 1.5: score += 5; good.append("Healthy current ratio")
        elif cr < 1: risk.append("Current ratio below 1")
    return min(30, score), good, risk

def news_score(news):
    score, good, risk = 7.5, [], []
    for item in (news or [])[:12]:
        title = (item.get("title") or "").lower()
        for term, pts in POS.items():
            if term in title:
                score += pts; good.append(item.get("title", "")[:130]); break
        for term, pts in NEG.items():
            if term in title:
                score += pts; risk.append(item.get("title", "")[:130]); break
    return max(0, min(15, score)), good[:4], risk[:4]

def scan(ticker):
    out = {"Ticker": ticker, "Score": 0, "Technical": 0, "Fundamental": 0, "News": 0,
           "Liquidity": 0, "Price": None, "As of": "Unavailable", "Positives": [], "Risks": [],
           "Coverage": "0/5", "Metrics": {}}
    try:
        h = fetch_history(ticker, "1y", "1d")
        info = fetch_company_info(ticker) or {}
        news = fetch_news(ticker) or []
        ts, tw, metrics = technical_score(h)
        fs, fw, fr = fundamental_score(info)
        ns, nw, nr = news_score(news)
        price = num(h["Close"].iloc[-1]) if not h.empty else None
        avgvol = num(h["Volume"].tail(20).mean()) if not h.empty else None
        dollarvol = price * avgvol if price and avgvol else 0
        liq = 15 if dollarvol >= 50e6 else 11 if dollarvol >= 10e6 else 7 if dollarvol >= 1e6 else 2
        risk = fr + nr
        total = ts + fs + ns + liq
        if len(h) >= 21:
            vol = h["Close"].pct_change().tail(20).std() * np.sqrt(252)
            if pd.notna(vol) and vol > 1: total -= 5; risk.append(f"Extreme volatility ({vol:.0%} annualised)")
            elif pd.notna(vol) and vol > .65: total -= 2; risk.append(f"High volatility ({vol:.0%} annualised)")
        coverage = sum([not h.empty and len(h) >= 60, bool(info.get("marketCap")),
                        info.get("revenueGrowth") is not None, info.get("profitMargins") is not None, bool(news)])
        out.update({"Score": round(max(0, min(100, total)), 1), "Technical": ts, "Fundamental": fs,
            "News": ns, "Liquidity": liq, "Price": price, "As of": str(h.index[-1]) if not h.empty else "Unavailable",
            "Positives": tw + fw + nw, "Risks": risk, "Coverage": f"{coverage}/5",
            "Metrics": metrics, "Company": info.get("longName", ticker)})
    except Exception as e:
        out["Risks"] = [f"Data error: {str(e)[:120]}"]
    return out

st.warning("Scoring is transparent and rule-based in this first release. Headline matching is a rough catalyst filter, not true AI sentiment. Yahoo Finance data can be delayed, missing or revised.")
with st.sidebar:
    st.header("Scanner controls")
    raw = st.text_area("Ticker universe", ", ".join(UNIVERSE), height=110)
    tickers = list(dict.fromkeys(t.strip().upper() for t in raw.split(",") if t.strip()))
    run = st.button("Run full scan", type="primary", use_container_width=True)
    st.divider()
    st.subheader("Moderate-risk sizing")
    account = st.number_input("Account value (USD)", min_value=0.0, value=1000.0, step=100.0)
    risk_pct = st.slider("Max account risk per trade (%)", .1, 1.0, .5, .1)
    entry = st.number_input("Planned entry (USD)", min_value=0.0, value=0.0, step=.1)
    stop = st.number_input("Stop price (USD)", min_value=0.0, value=0.0, step=.1)

if run or "picker_results" not in st.session_state:
    bar = st.progress(0)
    status = st.empty()
    rows = []
    for i, symbol in enumerate(tickers):
        status.write(f"Scanning {symbol} ({i+1}/{len(tickers)})")
        rows.append(scan(symbol))
        bar.progress((i+1)/max(1, len(tickers)))
    st.session_state["picker_results"] = rows
    status.empty(); bar.empty()

rows = st.session_state.get("picker_results", [])
if rows:
    ranked = pd.DataFrame(rows).sort_values("Score", ascending=False)
    st.subheader("Ranked opportunities")
    st.dataframe(ranked[["Ticker", "Score", "Technical", "Fundamental", "News", "Liquidity",
                         "Price", "As of", "Coverage"]], use_container_width=True, hide_index=True,
        column_config={"Score": st.column_config.ProgressColumn("Score / 100", min_value=0, max_value=100),
                       "Price": st.column_config.NumberColumn("Last historical price (USD)", format="$%.2f")})
    top = ranked.iloc[0]
    a,b,c = st.columns(3)
    a.metric("Top-ranked", top["Ticker"]); b.metric("Score", f'{top["Score"]}/100'); c.metric("Data coverage", top["Coverage"])
    st.caption("A top score means investigate first, not buy now. Confirm a fresh executable quote, entry trigger, stop and reward/risk in Revolut.")
    st.subheader("Evidence and risk review")
    for _, row in ranked.iterrows():
        with st.expander(f'{row["Ticker"]} — {row["Score"]}/100 | {row.get("Company", row["Ticker"])}', expanded=row["Ticker"] == top["Ticker"]):
            l,r = st.columns(2)
            with l:
                st.markdown("**Positive evidence**")
                for item in row["Positives"][:10]: st.write("• " + item)
                if not row["Positives"]: st.write("No strong positive signals detected.")
            with r:
                st.markdown("**Risks / missing evidence**")
                for item in row["Risks"][:10]: st.write("• " + item)
                if not row["Risks"]: st.write("No configured risk flags; this does not prove low risk.")
            if row["Metrics"]: st.json(row["Metrics"])
            st.caption(f'Last historical bar: {row["As of"]}. Check live price and spread before trading.')
    st.subheader("Position sizing calculator")
    if account > 0 and entry > stop > 0:
        risk_cash = account * risk_pct / 100
        shares = math.floor(risk_cash / (entry-stop))
        st.metric("Maximum shares by stop risk", shares)
        st.write(f"Planned loss at stop: US\${shares*(entry-stop):,.2f}, before spread, fees and slippage. Position value: US\${shares*entry:,.2f}.")
    else:
        st.caption("Enter an entry and a stop below entry to calculate a risk-based share quantity.")
    st.caption("Research tool only. It does not execute trades, guarantee fills or predict returns.")
else:
    st.info("Enter valid tickers and run the scan.")
