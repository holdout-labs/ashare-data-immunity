"""Board-aware price-limit and suspension detection for A-share daily bars.

A-share price limits vary by board; main-board ST status uses the same 10%
limit as ordinary main-board stocks under the 2026 rule (effective
2026-07-06) — before that date risk-warning stocks traded at ±5%, so the
limit is **date-aware**: ``price_limit_ratio``/``detect_limits`` select the
ratio from each bar's date (dual-track with dongzhu ``price_limits.py``,
see its feedback_gap_audit_v1_2026-09-02 §5 ruling).  Detection uses
the previous day's close and the standard tick
rounding (0.01), with a small tolerance for vendor rounding conventions.

Suspension heuristic (standard): a trading day with zero volume, or with
missing OHLC but a present date, is treated as suspended.  This is a
heuristic — vendor data varies — and the tool says so.
"""

from __future__ import annotations

import math
from typing import Any

# board -> (limit ratio, description)
BOARD_RULES: dict[str, dict[str, Any]] = {
    "main": {"ratio": 0.10, "label": "main board (60xxxx / 00xxxx)"},
    "star": {"ratio": 0.20, "label": "STAR market (688 / 689)"},
    "chinext": {"ratio": 0.20, "label": "ChiNext (300 / 301)"},
    "bse": {"ratio": 0.30, "label": "Beijing SE (8xx / 4xx / 920)"},
    "unknown": {"ratio": 0.10, "label": "unrecognized prefix (assumed main)"},
}
# Main-board risk-warning (ST/*ST) stocks: ±5% before 2026-07-06, ±10% from
# that date (SSE/SZSE trading-rule change effective 2026-07-06).
ST_RATIO = 0.10
ST_RATIO_LEGACY = 0.05
ST_RATIO_EFFECTIVE = "2026-07-06"
TICK = 0.01
ROUNDING_TOLERANCE = 0.001

STAR_PREFIXES = ("688", "689")
CHINEXT_PREFIXES = ("300", "301")
BSE_PREFIXES = ("430", "830", "831", "832", "833", "834", "835", "836", "837",
                "838", "839", "870", "871", "872", "873", "920")


def board_of(code: str) -> str:
    """Classify a code into main / star / chinext / bse / unknown."""
    code = str(code or "")
    if code.startswith(STAR_PREFIXES):
        return "star"
    if code.startswith(CHINEXT_PREFIXES):
        return "chinext"
    if code.startswith(BSE_PREFIXES):
        return "bse"
    return "main"


def price_limit_ratio(
    code: str, *, is_st: bool = False, as_of: str | None = None
) -> float:
    """Return the daily price-limit ratio for a code, including ST status.

    ``as_of`` is the bar trading date (YYYY-MM-DD): it selects the
    risk-warning limit in force that day (5% before 2026-07-06, 10% from
    then); ``None`` uses the current rule (10%).  STAR/ChiNext/BSE are not
    affected by the ST rule (no ST regime difference there).
    """
    board = board_of(code)
    if is_st and board in ("main", "unknown"):
        if as_of is None or str(as_of)[:10] >= ST_RATIO_EFFECTIVE:
            return ST_RATIO
        return ST_RATIO_LEGACY
    return float(BOARD_RULES[board]["ratio"])


def _limit_price(prev_close: float, ratio: float, *, up: bool) -> float:
    if up:
        return round(prev_close * (1.0 + ratio), 2)
    return round(prev_close * (1.0 - ratio), 2)


def detect_limits(
    bars: list[dict[str, Any]],
    code: str,
    *,
    is_st: bool = False,
    tolerance: float = ROUNDING_TOLERANCE,
) -> list[dict[str, Any]]:
    """Flag bars whose close equals (within tolerance) the limit price.

    Requires the previous bar's close as the reference.  Returns one record
    per flagged bar: ``{"date", "close", "limit_up", "limit_down", "ratio",
    "limit_price"}``.  First bar has no reference and is never flagged.
    The ratio is chosen per bar date (ST rule changed 2026-07-06), so a
    series crossing that date is judged correctly on each side.
    """
    events: list[dict[str, Any]] = []
    prev_close: float | None = None
    for bar in bars or []:
        date_text = str(bar.get("date") or "")[:10]
        ratio = price_limit_ratio(code, is_st=is_st, as_of=date_text or None)
        try:
            close = float(bar["close"])
        except (TypeError, ValueError, KeyError):
            close = math.nan
        valid = math.isfinite(close) and close > 0
        if not valid or prev_close is None or prev_close <= 0:
            if valid:
                prev_close = close
            continue
        limit_up_price = _limit_price(prev_close, ratio, up=True)
        limit_down_price = _limit_price(prev_close, ratio, up=False)
        if abs(close - limit_up_price) <= tolerance:
            events.append(
                {
                    "date": date_text,
                    "close": close,
                    "limit_up": True,
                    "limit_down": False,
                    "ratio": ratio,
                    "limit_price": limit_up_price,
                }
            )
        elif abs(close - limit_down_price) <= tolerance:
            events.append(
                {
                    "date": date_text,
                    "close": close,
                    "limit_up": False,
                    "limit_down": True,
                    "ratio": ratio,
                    "limit_price": limit_down_price,
                }
            )
        prev_close = close
    return events


def suspension_days(
    bars: list[dict[str, Any]],
    *,
    zero_volume_means_suspended: bool = True,
) -> list[dict[str, Any]]:
    """Heuristic suspension detection: date present but no trade.

    A bar counts as suspended when it has a date and either (a) volume is
    zero/missing while OHLC are present, or (b) OHLC are all missing/zero.
    The heuristic is documented, not hidden — vendor conventions differ.
    """
    days: list[dict[str, Any]] = []
    for bar in bars or []:
        date_text = str(bar.get("date") or "")[:10]
        if not date_text:
            continue
        try:
            volume = float(bar.get("volume") or 0.0)
        except (TypeError, ValueError):
            volume = 0.0
        prices = []
        for field in ("open", "high", "low", "close"):
            try:
                value = float(bar.get(field) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            prices.append(value)
        no_prices = all(not math.isfinite(value) or value <= 0 for value in prices)
        zero_volume = (not math.isfinite(volume) or volume <= 0) if zero_volume_means_suspended else False
        if no_prices or zero_volume:
            days.append({"date": date_text, "reason": "no_prices" if no_prices else "zero_volume"})
    return days
