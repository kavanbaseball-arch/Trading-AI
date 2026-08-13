from __future__ import annotations

import json
import time
from io import StringIO

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

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/csv,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _closes_from_yahoo_frame(data: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        closes = data["Close"].copy()
    else:
        closes = data[["Close"]].copy()
        closes.columns = symbols[:1]
    return closes.dropna(how="all")


def series_from_yahoo_chart(payload: dict, symbol: str) -> pd.Series:
    result = (payload or {}).get("chart", {}).get("result") or []
    if not result:
        raise RuntimeError("yahoo chart empty result")
    block = result[0]
    stamps = block.get("timestamp") or []
    indicators = block.get("indicators") or {}
    adj = (indicators.get("adjclose") or [{}])[0].get("adjclose")
    raw = (indicators.get("quote") or [{}])[0].get("close")
    closes = adj or raw
    if not stamps or not closes:
        raise RuntimeError("yahoo chart missing closes")
    idx = pd.to_datetime(stamps, unit="s", utc=True).tz_convert(None)
    series = pd.Series(closes, index=idx, name=symbol, dtype="float64").dropna()
    if series.empty:
        raise RuntimeError("yahoo chart all-NaN closes")
    return series


def series_from_stooq_csv(text: str, symbol: str) -> pd.Series:
    if "<html" in text[:200].lower() or "verify your browser" in text.lower():
        raise RuntimeError("stooq returned a browser-challenge page")
    df = pd.read_csv(StringIO(text))
    if df.empty:
        raise RuntimeError("stooq csv empty")
    renamed = {c.strip().lower(): c for c in df.columns}
    date_col = renamed.get("date") or renamed.get("data")
    close_col = renamed.get("close") or renamed.get("zamkniecie") or renamed.get("zamknięcie")
    if not date_col or not close_col:
        raise RuntimeError(f"stooq unexpected columns {list(df.columns)}")
    dates = pd.to_datetime(df[date_col], errors="coerce")
    closes = pd.to_numeric(df[close_col], errors="coerce")
    series = pd.Series(closes.values, index=dates, name=symbol).dropna()
    series = series[~series.index.isna()].sort_index()
    if series.empty:
        raise RuntimeError("stooq parsed empty series")
    return series.tail(280)


class MarketData:
    """Daily history + last prices. Yahoo with backoff, Stooq fallback, Alpaca if keyed."""

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

    def _cache_paths(self) -> tuple:
        return self.cache_dir / "daily_closes.pkl", self.cache_dir / "daily_meta.json"

    def _read_cache(self) -> pd.DataFrame:
        cache_path, meta_path = self._cache_paths()
        if not cache_path.exists():
            return pd.DataFrame()
        try:
            hist = pd.read_pickle(cache_path)
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if time.time() - meta.get("ts", 0) > 6 * 3600:
                    return hist  # still usable as a base; caller refreshes missing/stale cols
            return hist
        except Exception:
            return pd.DataFrame()

    def _write_cache(self, hist: pd.DataFrame) -> None:
        cache_path, meta_path = self._cache_paths()
        hist.to_pickle(cache_path)
        meta_path.write_text(
            json.dumps({"ts": time.time(), "symbols": list(hist.columns)}),
            encoding="utf-8",
        )

    def _http_get(self, url: str) -> str:
        if httpx is None:
            raise RuntimeError("httpx is required")
        resp = httpx.get(url, timeout=20.0, headers=BROWSER_HEADERS, follow_redirects=True)
        resp.raise_for_status()
        return resp.text

    def _yahoo_chart(self, symbol: str, range_spec: str = "1y") -> pd.Series:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            f"?range={range_spec}&interval=1d&includeAdjustedClose=true"
        )
        payload = json.loads(self._http_get(url))
        return series_from_yahoo_chart(payload, symbol)

    def _yahoo_one(self, symbol: str, period: str) -> pd.Series:
        data = yf.download(
            symbol,
            period=period,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        closes = _closes_from_yahoo_frame(data, [symbol])
        if closes.empty:
            raise RuntimeError("empty or rate-limited")
        series = closes.iloc[:, 0].dropna()
        series.name = symbol
        if series.empty:
            raise RuntimeError("empty close series")
        return series

    def _stooq_one(self, symbol: str) -> pd.Series:
        url = f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d"
        text = self._http_get(url) if httpx is not None else pd.read_csv(url).to_csv(index=False)
        return series_from_stooq_csv(text, symbol)

    def _fetch_one(self, symbol: str, period: str = "1y") -> pd.Series:
        errors: list[str] = []
        try:
            return self._yahoo_chart(symbol, "1y" if period == "1y" else "2y")
        except Exception as exc:
            errors.append(f"chart:{exc}")
        try:
            return self._yahoo_one(symbol, period)
        except Exception as exc:
            errors.append(f"yfinance:{exc}")
        try:
            return self._stooq_one(symbol)
        except Exception as exc:
            errors.append(f"stooq:{exc}")
        raise RuntimeError(f"No history for {symbol} ({'; '.join(errors)})")

    def load_history(self, symbols: list[str] | None = None, period: str = "1y") -> pd.DataFrame:
        symbols = symbols or all_symbols()
        cached = self._read_cache()
        have = set(cached.columns) if not cached.empty else set()
        missing = [s for s in symbols if s not in have]
        if missing:
            print(f"[info] fetching {len(missing)} symbols ({len(have)} already cached)", flush=True)
        frames = [cached] if not cached.empty else []
        for i, symbol in enumerate(missing, start=1):
            print(f"[info] history {symbol} {i}/{len(missing)}", flush=True)
            try:
                series = self._fetch_one(symbol, period)
                frames.append(series.to_frame())
                merged = pd.concat(frames, axis=1)
                merged = merged.loc[:, ~merged.columns.duplicated()].dropna(how="all")
                self._write_cache(merged)
                frames = [merged]
            except Exception as exc:
                print(f"[warn] skipping {symbol}: {exc}", flush=True)
            time.sleep(0.25)
        if not frames:
            raise RuntimeError("No daily history from Yahoo or Stooq")
        closes = frames[0]
        closes = closes.loc[:, ~closes.columns.duplicated()].dropna(how="all")
        self._history = closes
        return closes

    def history_for(self, symbol: str) -> pd.Series:
        if self._history is None:
            self.load_history()
        assert self._history is not None
        if symbol in self._history.columns:
            return self._history[symbol].dropna()
        series = self._fetch_one(symbol)
        self._history[symbol] = series
        self._write_cache(self._history)
        return series.dropna()

    def last_prices(self, symbols: list[str] | None = None) -> dict[str, float]:
        symbols = symbols or all_symbols()
        prices: dict[str, float] = {}
        if self._history is None:
            try:
                self.load_history(symbols)
            except Exception as exc:
                print(f"[warn] history preload failed: {exc}", flush=True)
        if self._history is not None:
            last_row = self._history.ffill().iloc[-1]
            for sym in symbols:
                if sym in last_row.index and pd.notna(last_row[sym]):
                    prices[sym] = float(last_row[sym])
        if self._alpaca and StockLatestTradeRequest:
            missing = [s for s in symbols if s not in prices]
            if missing:
                try:
                    req = StockLatestTradeRequest(symbol_or_symbols=missing, feed=settings.alpaca_data_feed)
                    trades = self._alpaca.get_stock_latest_trade(req)
                    for sym, trade in trades.items():
                        prices[sym] = float(trade.price)
                except Exception:
                    pass
        still = [s for s in symbols if s not in prices]
        for sym in still:
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
        try:
            hist = self.history_for(symbol.upper())
        except Exception:
            hist = pd.Series(dtype=float)
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
            "source": "alpaca" if self._alpaca else "yahoo/stooq",
        }
