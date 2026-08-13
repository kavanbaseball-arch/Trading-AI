from __future__ import annotations

import pandas as pd

from app.config import settings
from app.stats import current_zscore, rolling_zscore, shares_b_for_dollar_neutral, spread_series, evaluate_cointegration
from app.universe import PairSpec


def _last_valid(series: pd.Series, fallback: float | None = None) -> float | None:
    clean = series.dropna()
    if clean.empty:
        return fallback
    return float(clean.iloc[-1])


class PairAnalyzer:
    def analyze(self, pair: PairSpec, price_a: pd.Series, price_b: pd.Series, live_a: float, live_b: float) -> dict:
        lookback = settings.coint_lookback_days
        a = price_a.tail(lookback)
        b = price_b.tail(lookback)
        try:
            coint = evaluate_cointegration(a, b, settings.coint_pvalue)
        except ValueError as exc:
            return {
                "pair_id": pair.id,
                "error": str(exc),
                "is_cointegrated": False,
                "tradable": False,
            }

        # Overlay live prices as the current observation.
        idx_tz = getattr(a.index, "tz", None)
        now_utc = pd.Timestamp.now("UTC")
        live_idx = now_utc.tz_convert(idx_tz) if idx_tz is not None else now_utc.tz_convert(None)
        a_live = pd.concat([a, pd.Series({live_idx: live_a})])
        b_live = pd.concat([b, pd.Series({live_idx: live_b})])
        a_live = a_live[~a_live.index.duplicated(keep="last")]
        b_live = b_live[~b_live.index.duplicated(keep="last")]

        spread = spread_series(a_live, b_live, coint.hedge.beta, coint.hedge.alpha)
        z_series = rolling_zscore(spread, settings.z_lookback)
        z = current_zscore(spread, settings.z_lookback)
        prev_z = float(z_series.dropna().iloc[-2]) if len(z_series.dropna()) >= 2 else None

        return {
            "pair_id": pair.id,
            "sector": pair.sector,
            "symbol_a": pair.symbol_a,
            "symbol_b": pair.symbol_b,
            "name_a": pair.name_a,
            "name_b": pair.name_b,
            "price_a": live_a,
            "price_b": live_b,
            "alpha": coint.hedge.alpha,
            "beta": coint.hedge.beta,
            "r_squared": coint.hedge.r_squared,
            "adf_stat": coint.adf_stat,
            "adf_pvalue": coint.pvalue,
            "engle_granger_pvalue": coint.engle_granger_pvalue,
            "is_cointegrated": coint.is_cointegrated,
            "spread": _last_valid(spread),
            "zscore": z,
            "prev_z": prev_z,
            "spread_series": [
                {"t": ts.isoformat(), "spread": float(v)}
                for ts, v in spread.tail(90).items()
                if pd.notna(v)
            ],
            "z_series": [
                {"t": ts.isoformat(), "z": float(v)}
                for ts, v in z_series.tail(90).items()
                if pd.notna(v)
            ],
        }


def size_pair(notional: float, price_a: float, price_b: float, beta: float) -> tuple[float, float]:
    shares_a = notional / price_a
    shares_b = shares_b_for_dollar_neutral(shares_a, price_a, price_b, beta)
    return shares_a, shares_b


def spread_correlation(states: list[dict], left_id: str, right_id: str) -> float | None:
    left = next((s for s in states if s.get("pair_id") == left_id), None)
    right = next((s for s in states if s.get("pair_id") == right_id), None)
    if not left or not right:
        return None
    ls = pd.Series({row["t"]: row["spread"] for row in left.get("spread_series", [])})
    rs = pd.Series({row["t"]: row["spread"] for row in right.get("spread_series", [])})
    aligned = pd.concat([ls, rs], axis=1).dropna()
    if len(aligned) < 20:
        return None
    return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))
