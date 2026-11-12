# AI Stock Picker — first release

A transparent multi-factor stock screener added as a Streamlit multipage view at `pages/1_AI_Stock_Picker.py`.

## How to open
Run the existing Streamlit app as usual. Streamlit automatically adds **AI Stock Picker** to the app's page navigation because the page is inside `pages/`.

## Universe
The scanner starts with the existing dashboard watchlist plus RSKD, CRWV and NBIS. Edit the comma-separated ticker list in the sidebar to change the universe.

## Score model (100 points)
- Technical trend and momentum: 40
- Fundamentals: 30
- News catalyst headline filter: 15
- Dollar-volume liquidity: 15
- Volatility deductions: up to 5 points for very high realised volatility (2 points for elevated volatility)

The app displays the component scores, positive evidence, risk flags, data coverage and last historical bar date. Fundamentals use Yahoo Finance fields where available. News matching is deliberately simple and should be treated as a triage signal only.

## Risk controls
The position-sizing calculator uses a user-entered account value, risk percentage, entry and stop. Default risk is 0.5% of the entered USD account value. It excludes spread, FX conversion, fees, slippage and gaps; it does not submit orders.

## Important limitations
This is an explainable quantitative screening engine, not a trained predictive model and not a guarantee of returns. Yahoo Finance data may be delayed, incomplete or revised. Missing fields are not treated as positive evidence. A high score means investigate first, not buy. Verify filings, earnings dates, live executable prices and spreads independently before trading.

## Next engineering steps
1. Add a reliable market-data/news provider with documented real-time entitlements.
2. Add SEC-based financial statement and dilution checks.
3. Add earnings-calendar and event-risk gates.
4. Add walk-forward backtesting with transaction costs and out-of-sample validation.
5. Add an optional LLM layer for cited filing/news explanations; keep the numeric scoring deterministic and auditable.
