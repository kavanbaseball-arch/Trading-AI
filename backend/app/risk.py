from __future__ import annotations

from app.config import settings
from app.universe import PairSpec


class RiskEngine:
    def __init__(self) -> None:
        self.max_notional = settings.max_notional_per_pair
        self.max_open = settings.max_open_pairs
        self.max_gross_pct = settings.max_gross_exposure_pct
        self.corr_limit = settings.pair_spread_corr_limit
        self.max_hold_days = settings.max_hold_days
        self.z_stop = settings.z_stop

    def can_open(
        self,
        pair: PairSpec,
        *,
        open_pair_ids: list[str],
        equity: float,
        gross_exposure: float,
        overlapping_tickers: set[str],
        stacked_corr: float | None,
    ) -> tuple[bool, str]:
        if pair.id in open_pair_ids:
            return False, "already_open"
        if len(open_pair_ids) >= self.max_open:
            return False, f"max_open_pairs_{self.max_open}"
        if equity <= 0:
            return False, "no_equity"
        projected = gross_exposure + 2 * self.max_notional
        if projected > equity * self.max_gross_pct:
            return False, "portfolio_gross_cap"
        if pair.symbol_a in overlapping_tickers or pair.symbol_b in overlapping_tickers:
            return False, "shared_leg_risk"
        if stacked_corr is not None and abs(stacked_corr) > self.corr_limit:
            return False, "pair_spread_correlation"
        return True, "ok"

    def should_force_exit(
        self,
        *,
        holding_days: int,
        zscore: float,
        still_cointegrated: bool,
    ) -> tuple[bool, str | None]:
        if not still_cointegrated:
            return True, "cointegration_broke"
        if holding_days >= self.max_hold_days:
            return True, "max_hold"
        if abs(zscore) >= self.z_stop:
            return True, "stop_z"
        return False, None
