from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from app.config import settings
from app.universe import all_symbols

try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestTradeRequest
except Exception:  # pragma: no cover
    StockHistoricalDataClient = None
    StockLatestTradeRequest = None


class MarketData:
    """Daily history + last prices. Alpaca live trades when keys exist, else Yahoo."""

    def __init__(self) -> None:
        self.cache_dir = settings.data_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._history: pd.DataFrame | None = None
        self._last_prices: dict[str, float] = {}
        self._alpaca = None
        if settings.alpaca_api_key and settings.alpaca_api_secret and StockHistoricalDataClient:
            self._alpaca = StockHistoricalDataClient(
                settings.alpaca_api_key,
                settings.alpaca_api_secret,
            )

    def load_history(self, symbols: list[str] | None = None, period: str = "1y") -> pd.DataFrame:
        symbols = symbols or all_symbols()
        cache_path = self.cache_dir / "daily_closes.pkl"
        meta_path = self.cache_dir / "daily_meta.json"
        now = time.time()
        if cache_path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if now - meta.get("ts", 0) < 6 * 3600 and set(symbols).issubset(set(meta.get("symbols", []))):
                hist = pd.read_pickle(cache_path)
                self._history = hist
                return hist

        frames: list[pd.DataFrame] = []
        batch_size = 10
        for i in range(0, len(symbols), batch_size):
            chunk = symbols[i : i + batch_size]
            print(f"[info] downloading history {i + 1}-{i + len(chunk)}/{len(symbols)}", flush=True)
            data = yf.download(
                chunk,
                period=period,
                auto_adjust=True,
                progress=False,
                threads=False,
                group_by="column",
            )
            if data is None or data.empty:
                continue
            if isinstance(data.columns, pd.MultiIndex):
                closes = data["Close"].copy()
            else:
                closes = data[["Close"]].copy()
                closes.columns = chunk[:1]
            frames.append(closes)
            time.sleep(0.3)
        if not frames:
            raise RuntimeError("Yahoo returned no daily history")
        closes = pd.concat(frames, axis=1).dropna(how="all")
        closes.to_pickle(cache_path)
        meta_path.write_text(
            json.dumps({"ts": now, "symbols": list(closes.columns)}),
            encoding="utf-8",
        )
        self._history = closes
        return closes

    def history_for(self, symbol: str) -> pd.Series:
        if self._history is None:
            self.load_history()
        assert self._history is not None
        if symbol not in self._history.columns:
            one = yf.download(symbol, period="2y", auto_adjust=True, progress=False)
            series = one["Close"].dropna()
            series.name = symbol
            return series
        return self._history[symbol].dropna()

    def last_prices(self, symbols: list[str] | None = None) -> dict[str, float]:
        symbols = symbols or all_symbols()
        prices: dict[str, float] = {}
        if self._alpaca and StockLatestTradeRequest:
            try:
                req = StockLatestTradeRequest(symbol_or_symbols=symbols, feed=settings.alpaca_data_feed)
                trades = self._alpaca.get_stock_latest_trade(req)
                for sym, trade in trades.items():
                    prices[sym] = float(trade.price)
            except Exception:
                prices = {}
        missing = [s for s in symbols if s not in prices]
        if missing:
            try:
                data = yf.download(
                    missing,
                    period="5d",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                )
                if isinstance(data.columns, pd.MultiIndex):
                    last_row = data["Close"].ffill().iloc[-1]
                    for sym, val in last_row.items():
                        if pd.notna(val):
                            prices[str(sym)] = float(val)
                elif not data.empty:
                    prices[missing[0]] = float(data["Close"].ffill().iloc[-1])
            except Exception:
                pass
            if self._history is None:
                try:
                    self.load_history()
                except Exception:
                    pass
            for sym in missing:
                if sym in prices:
                    continue
                try:
                    hist = self.history_for(sym)
                    if not hist.empty:
                        prices[sym] = float(hist.iloc[-1])
                except Exception:
                    continue
        self._last_prices = prices
        return prices

    def quote(self, symbol: str) -> dict:
        prices = self.last_prices([symbol.upper()])
        hist = self.history_for(symbol.upper())
        last = prices.get(symbol.upper())
        prev = float(hist.iloc[-2]) if len(hist) >= 2 else last
        change = None
        change_pct = None
        if last is not None and prev:
            change = last - prev
            change_pct = change / prev
        return {
            "symbol": symbol.upper(),
            "last": last,
            "prev_close": prev,
            "change": change,
            "change_pct": change_pct,
            "source": "alpaca" if self._alpaca else "yahoo",
        }
