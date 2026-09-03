"""Evidence-tracked bar repair (``imm repair``).

Dogfood backfill 2026-09: a one-day OHLC scale corruption (21 symbols,
×100) in a production A-share pipeline was repaired from an independent raw
source.  The repair itself was ad-hoc; this module productizes the pattern:
overwrite corrupted OHLC from a reviewed correction list, keep everything
else untouched, and leave an **append-only repair record** next to the data
so the evidence chain stays replayable (what was there, what replaced it,
when, and why).

Semantics:

- corrections overwrite **existing** bars only (matched by ``date``); a
  correction for an unknown date is skipped and reported, never silently
  appended — adding history is a different operation;
- every corrected OHLC value must be finite, positive, and internally
  consistent (``low <= open,close <= high``); anything else is skipped as
  ``invalid_ohlc`` (fail-closed, no partial writes of a bad row);
- the append-only log is the source of truth for "what did we change": each
  run appends one record with old/new OHLC per applied correction.

This module never fetches data and never decides what the correct price is;
it only applies and records reviewed corrections.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPAIR_SCHEMA_VERSION = "ashare_bar_repair.v1"
LOG_SCHEMA_VERSION = "ashare_bar_repair_log.v1"
SAFETY = {
    "production_effect": False,
    "changes_probability": False,
    "submits_to_mx_moni": False,
    "allow_real_trade": False,
    "active_live": False,
}
_OHLC = ("open", "high", "low", "close")


def _finite_positive(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def _valid_correction_ohlc(row: dict[str, Any]) -> bool:
    values = {}
    for key in _OHLC:
        if not _finite_positive(row.get(key)):
            return False
        values[key] = float(row[key])
    # internal consistency: low <= open,close <= high (tolerance for float)
    if values["low"] > values["high"]:
        return False
    if not (values["low"] <= values["open"] <= values["high"]):
        return False
    if not (values["low"] <= values["close"] <= values["high"]):
        return False
    return True


def repair_bars(
    bars: Sequence[dict[str, Any]],
    corrections: Sequence[dict[str, Any]],
    *,
    code: str = "",
    note: str = "",
) -> dict[str, Any]:
    """Apply reviewed OHLC corrections to existing bars (pure).

    Returns the repaired bar list under ``bars`` plus ``applied`` /
    ``skipped`` details.  The input bars are not mutated.
    """
    by_date = {str(bar.get("date") or "")[:10]: bar for bar in bars or []}
    repaired = [dict(bar) for bar in bars or []]
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for correction in corrections or []:
        day = str(correction.get("date") or "")[:10]
        if not day:
            skipped.append({"date": "", "reason": "date_required"})
            continue
        if not _valid_correction_ohlc(correction):
            skipped.append({"date": day, "reason": "invalid_ohlc"})
            continue
        if day not in by_date:
            skipped.append({"date": day, "reason": "date_not_found"})
            continue
        old = {key: by_date[day].get(key) for key in _OHLC}
        for bar in repaired:
            if str(bar.get("date") or "")[:10] == day:
                for key in _OHLC:
                    bar[key] = float(correction[key])
                break
        applied.append(
            {
                "date": day,
                "old": {key: old[key] for key in _OHLC},
                "new": {key: float(correction[key]) for key in _OHLC},
            }
        )
    return {
        "schema_version": REPAIR_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code": code,
        "note": note,
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "applied": applied,
        "skipped": skipped,
        "bars": repaired,
        "safety": SAFETY,
    }


def append_repair_record(log_path: str | Path, report: dict[str, Any]) -> None:
    """Append one repair record to an append-only JSONL log."""
    if report.get("schema_version") != REPAIR_SCHEMA_VERSION:
        raise ValueError("append_repair_record requires a repair_bars report")
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": LOG_SCHEMA_VERSION,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code": report.get("code", ""),
        "note": report.get("note", ""),
        "applied": report.get("applied", []),
        "skipped": report.get("skipped", []),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
