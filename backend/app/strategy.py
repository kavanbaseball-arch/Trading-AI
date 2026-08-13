from __future__ import annotations

from dataclasses import dataclass

from app.config import settings


@dataclass
class Signal:
    pair_id: str
    action: str  # enter_short_spread | enter_long_spread | exit | hold | disable
    reason: str
    zscore: float
    side: str | None = None  # short_a_long_b | long_a_short_b


def crossed_zero(prev_z: float | None, z: float) -> bool:
    if prev_z is None or any(v != v for v in (prev_z, z)):  # NaN
        return abs(z) < 0.15
    return (prev_z > 0 and z <= 0) or (prev_z < 0 and z >= 0) or abs(z) < 0.10


def evaluate_signal(
    *,
    pair_id: str,
    zscore: float,
    prev_z: float | None,
    is_cointegrated: bool,
    has_position: bool,
    position_side: str | None,
) -> Signal:
    if not is_cointegrated and not has_position:
        return Signal(pair_id, "disable", "not_cointegrated", zscore)
    if has_position:
        if crossed_zero(prev_z, zscore):
            return Signal(pair_id, "exit", "mean_reverted", zscore, position_side)
        return Signal(pair_id, "hold", "waiting_for_reversion", zscore, position_side)
    if zscore > settings.z_entry:
        return Signal(
            pair_id,
            "enter_short_spread",
            "z_above_entry",
            zscore,
            "short_a_long_b",
        )
    if zscore < -settings.z_entry:
        return Signal(
            pair_id,
            "enter_long_spread",
            "z_below_entry",
            zscore,
            "long_a_short_b",
        )
    return Signal(pair_id, "hold", "inside_band", zscore)
