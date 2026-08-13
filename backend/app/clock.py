from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

# Observed NYSE holidays 2025-2027 (weekday closures).
NYSE_HOLIDAYS = {
    date(2025, 1, 1),
    date(2025, 1, 20),
    date(2025, 2, 17),
    date(2025, 4, 18),
    date(2025, 5, 26),
    date(2025, 6, 19),
    date(2025, 7, 4),
    date(2025, 9, 1),
    date(2025, 11, 27),
    date(2025, 12, 25),
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
    date(2027, 1, 1),
    date(2027, 1, 18),
    date(2027, 2, 15),
    date(2027, 3, 26),
    date(2027, 5, 31),
    date(2027, 6, 18),
    date(2027, 7, 5),
    date(2027, 9, 6),
    date(2027, 11, 25),
    date(2027, 12, 24),
}


def now_et() -> datetime:
    return datetime.now(EASTERN)


def is_trading_day(d: date | None = None) -> bool:
    d = d or now_et().date()
    if d.weekday() >= 5:
        return False
    return d not in NYSE_HOLIDAYS


def market_session() -> dict:
    ts = now_et()
    open_t = time(9, 30)
    close_t = time(16, 0)
    trading_day = is_trading_day(ts.date())
    current = ts.time()
    is_open = trading_day and open_t <= current < close_t
    if not trading_day:
        phase = "closed"
    elif current < open_t:
        phase = "premarket"
    elif current >= close_t:
        phase = "afterhours"
    else:
        phase = "open"
    return {
        "now_et": ts.isoformat(),
        "is_open": is_open,
        "phase": phase,
        "trading_day": trading_day,
    }
