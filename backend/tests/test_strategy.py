import numpy as np
import pandas as pd

from app.stats import shares_b_for_dollar_neutral, evaluate_cointegration
from app.strategy import evaluate_signal


def _cointegrated_pair(n=400, seed=7):
    rng = np.random.default_rng(seed)
    x = 80 + np.cumsum(rng.normal(0, 0.6, n))
    y = 12 + 1.4 * x + rng.normal(0, 0.8, n)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.Series(y, index=idx), pd.Series(x, index=idx)


def test_cointegrated_series_passes():
    a, b = _cointegrated_pair()
    result = evaluate_cointegration(a, b, 0.05)
    assert result.is_cointegrated
    assert 1.2 < result.hedge.beta < 1.6


def test_independent_walks_fail():
    rng = np.random.default_rng(3)
    n = 400
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    a = pd.Series(100 + np.cumsum(rng.normal(0, 1, n)), index=idx)
    b = pd.Series(100 + np.cumsum(rng.normal(0, 1, n)), index=idx)
    result = evaluate_cointegration(a, b, 0.05)
    assert result.is_cointegrated is False


def test_dollar_neutral_formula():
    shares_b = shares_b_for_dollar_neutral(shares_a=10, price_a=100, price_b=50, beta=2)
    assert abs(shares_b - 10) < 1e-9


def test_entry_and_exit_signals():
    enter = evaluate_signal(
        pair_id="AAPL-MSFT",
        zscore=2.3,
        prev_z=1.8,
        is_cointegrated=True,
        has_position=False,
        position_side=None,
    )
    assert enter.action == "enter_short_spread"
    exit_sig = evaluate_signal(
        pair_id="AAPL-MSFT",
        zscore=-0.05,
        prev_z=0.4,
        is_cointegrated=True,
        has_position=True,
        position_side="short_a_long_b",
    )
    assert exit_sig.action == "exit"
    skip = evaluate_signal(
        pair_id="AAPL-MSFT",
        zscore=2.4,
        prev_z=2.1,
        is_cointegrated=False,
        has_position=False,
        position_side=None,
    )
    assert skip.action == "disable"
