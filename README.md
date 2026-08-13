# Pair Trading Tester

AI-operated, market-neutral **NYSE pairs-trading** platform. The account name is **Pair Trading Tester**. A quantitative operator runs the book on a hard-coded ruleset; you can talk to it about live quotes, cointegration, and open risk.

This is a paper-trading research tool, not investment advice. Live routing is off until you set `BROKER=alpaca` with your own keys.

## What it does

For every pair in the universe the operator:

1. Tests **cointegration** (Engle-Granger + ADF on the OLS residual). Trades only if both p-values are below 0.05.
2. Estimates the hedge: `Price_A = α + β · Price_B + ε`
3. Trades the spread `Spread = Price_A − β · Price_B`, not raw prices.
4. Converts the spread to a rolling **z-score** (60-day lookback).
5. **Entry:** z > +2 short A / long B; z < −2 long A / short B. **Exit:** z crosses 0. **Stop:** |z| ≥ 3.5 or cointegration breaks.
6. Sizes **dollar-neutral**: `Shares_B = (Shares_A · Price_A) / (β · Price_B)`
7. Enforces max hold 20 trading days, per-pair and portfolio caps, no shared-leg stacking, and a spread-correlation filter across open pairs.

The LLM (optional `OPENAI_API_KEY`) can explain the book. It cannot bypass those risk limits.

## Universe notes

Retired names are kept in the grid so the operator can explain them:

| Pair | Status |
| --- | --- |
| CSCO vs JNPR | Disabled — Juniper acquired by HPE |
| SCHW vs AMTD | Disabled — TD Ameritrade acquired by Schwab |
| TMUS vs S | Disabled — Sprint merged into T-Mobile |
| MRO vs DVN | Disabled — Marathon Oil acquired by ConocoPhillips |
| DISH vs DirecTV | Disabled — not an independent listed pair |
| UNH vs ANTM | Traded as **UNH-ELV** (Elevance Health) |
| Citigroup vs WFC | Ticker **C** |

Ford vs GM is listed once. NVDA-AMD and INTC-AMD share AMD; the risk engine will not stack them.

## Run

Python 3.11+ recommended.

```powershell
cd "C:\Users\Kavan White\Downloads\pair-trading-tester"
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
copy .env.example .env
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Or from the repo root: `.\start.ps1`

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The first cycle downloads ~2 years of daily bars and can take a minute.

```powershell
cd backend
pytest
```

## Alpaca paper (real NYSE routing)

1. Create a paper account at [Alpaca](https://alpaca.markets/).
2. Put the key and secret in `.env`:

```
BROKER=alpaca
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
ALPACA_PAPER=true
ALPACA_DATA_FEED=iex
```

IEX is the typical paper feed. SIP (full NYSE) requires an Alpaca market-data subscription.

## AI chat

Works without a key using quotes + book state. For natural-language briefs:

```
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
```

Try: `quote NVDA`, `AAPL-MSFT`, `positions`.

## Tunable thresholds

In `.env`: `Z_ENTRY`, `Z_STOP`, `Z_LOOKBACK`, `COINT_PVALUE`, `MAX_HOLD_DAYS`, `MAX_NOTIONAL_PER_PAIR`, `MAX_OPEN_PAIRS`, `MAX_GROSS_EXPOSURE_PCT` (gross long+short / equity; default 1.60 so eight $10k/leg pairs can sit on a $100k book), `PAIR_SPREAD_CORR_LIMIT`.
