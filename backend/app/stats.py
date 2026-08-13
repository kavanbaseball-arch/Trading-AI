from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, coint


@dataclass
class HedgeResult:
    alpha: float
    beta: float
    residual_std: float
    r_squared: float


@dataclass
class CointegrationResult:
    pvalue: float
    adf_stat: float
    engle_granger_pvalue: float
    is_cointegrated: bool
    hedge: HedgeResult


def ols_hedge(price_a: pd.Series, price_b: pd.Series) -> HedgeResult:
    aligned = pd.concat([price_a, price_b], axis=1).dropna()
    aligned.columns = ["a", "b"]
    if len(aligned) < 30:
        raise ValueError("Need at least 30 overlapping observations for hedge ratio")
    x = sm.add_constant(aligned["b"])
    model = sm.OLS(aligned["a"], x).fit()
    return HedgeResult(
        alpha=float(model.params["const"]),
        beta=float(model.params["b"]),
        residual_std=float(np.std(model.resid, ddof=1)),
        r_squared=float(model.rsquared),
    )


def spread_series(price_a: pd.Series, price_b: pd.Series, beta: float, alpha: float = 0.0) -> pd.Series:
    aligned = pd.concat([price_a, price_b], axis=1).dropna()
    aligned.columns = ["a", "b"]
    return aligned["a"] - alpha - beta * aligned["b"]


def rolling_zscore(spread: pd.Series, lookback: int = 60) -> pd.Series:
    mean = spread.rolling(lookback, min_periods=max(10, lookback // 3)).mean()
    std = spread.rolling(lookback, min_periods=max(10, lookback // 3)).std(ddof=1)
    z = (spread - mean) / std.replace(0, np.nan)
    return z


def adf_pvalue(series: pd.Series) -> tuple[float, float]:
    clean = series.dropna()
    if len(clean) < 30:
        return float("nan"), 1.0
    stat, pvalue, *_ = adfuller(clean, maxlag=1, autolag="AIC")
    return float(stat), float(pvalue)


def engle_granger(price_a: pd.Series, price_b: pd.Series) -> float:
    aligned = pd.concat([price_a, price_b], axis=1).dropna()
    if len(aligned) < 30:
        return 1.0
    _score, pvalue, _crit = coint(aligned.iloc[:, 0], aligned.iloc[:, 1])
    return float(pvalue)


def evaluate_cointegration(
    price_a: pd.Series,
    price_b: pd.Series,
    pvalue_threshold: float = 0.05,
) -> CointegrationResult:
    hedge = ols_hedge(price_a, price_b)
    spread = spread_series(price_a, price_b, hedge.beta, hedge.alpha)
    adf_stat, adf_p = adf_pvalue(spread)
    eg_p = engle_granger(price_a, price_b)
    # Require both residual stationarity and Engle-Granger confirmation.
    is_coint = (adf_p < pvalue_threshold) and (eg_p < pvalue_threshold)
    return CointegrationResult(
        pvalue=adf_p,
        adf_stat=adf_stat,
        engle_granger_pvalue=eg_p,
        is_cointegrated=is_coint,
        hedge=hedge,
    )


def current_zscore(spread: pd.Series, lookback: int = 60) -> float:
    z = rolling_zscore(spread, lookback).dropna()
    if z.empty:
        return float("nan")
    return float(z.iloc[-1])


def shares_b_for_dollar_neutral(
    shares_a: float,
    price_a: float,
    price_b: float,
    beta: float,
) -> float:
    """Dollar-neutral hedge: Shares_B = (Shares_A * Price_A) / (β * Price_B)."""
    if price_b <= 0 or beta == 0:
        raise ValueError("Invalid price_b or beta")
    return (shares_a * price_a) / (beta * price_b)
