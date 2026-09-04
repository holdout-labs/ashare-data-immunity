"""ashare-data-immunity: data immunity for A-share daily bars.

Cleaning (NaN/OHLCV), board-aware price-limit and suspension detection,
quality audit (listing / coverage / continuity, with injectable data
sources) and snapshot versioning (sha256 manifests).  Read-only by design:
nothing here trades, prices, or decides —it keeps the data you feed it
honest.
"""

from .audit import (
    continuity_problems,
    history_coverage,
    listing_problems,
    run_quality_audit,
)
from .cleaning import clean_bars, validate_bars
from .limits import board_of, detect_limits, price_limit_ratio, suspension_days
from .snapshot import build_snapshot, compare_snapshots

__version__ = "0.1.4"

__all__ = [
    "board_of",
    "build_snapshot",
    "clean_bars",
    "compare_snapshots",
    "continuity_problems",
    "detect_limits",
    "history_coverage",
    "listing_problems",
    "price_limit_ratio",
    "run_quality_audit",
    "suspension_days",
    "validate_bars",
]

