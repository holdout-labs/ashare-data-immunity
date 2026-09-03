"""Tests for evidence-tracked bar repair (2026-09 dogfood backfill)."""

from __future__ import annotations

import json

import pytest

from ashare_data_immunity.repair import append_repair_record, repair_bars


def _bar(day: str, close: float) -> dict:
    return {
        "date": day,
        "open": round(close * 0.99, 4),
        "high": round(close * 1.01, 4),
        "low": round(close * 0.98, 4),
        "close": close,
        "volume": 1000.0,
        "amount": close * 100000.0,
    }


def test_repair_overwrites_existing_bar_only() -> None:
    bars = [_bar("2026-09-01", 402.0), _bar("2026-09-02", 4.03)]  # 09-01 x100 corruption
    report = repair_bars(
        bars,
        [{"date": "2026-09-01", "open": 3.95, "high": 4.04, "low": 3.91, "close": 4.02}],
        code="002218",
        note="watchdog case: scale corruption",
    )
    assert report["applied_count"] == 1
    assert report["skipped_count"] == 0
    repaired = report["bars"]
    assert repaired[0]["close"] == 4.02
    assert repaired[0]["volume"] == 1000.0  # 非 OHLC 字段原样保留
    assert repaired[1]["close"] == 4.03
    assert bars[0]["close"] == 402.0  # 输入未被就地修改
    assert report["applied"][0]["old"]["close"] == 402.0


def test_repair_skips_unknown_date_and_invalid_ohlc() -> None:
    bars = [_bar("2026-09-01", 4.02)]
    report = repair_bars(
        bars,
        [
            {"date": "2026-09-05", "open": 1, "high": 2, "low": 1, "close": 1.5},
            {"date": "2026-09-01", "open": 5, "high": 4, "low": 1, "close": 2},  # low>high 序
        ],
    )
    assert report["applied_count"] == 0
    assert report["skipped_count"] == 2
    reasons = {s["reason"] for s in report["skipped"]}
    assert reasons == {"date_not_found", "invalid_ohlc"}


def test_repair_log_is_append_only() -> None:
    from pathlib import Path
    import tempfile

    bars = [_bar("2026-09-01", 402.0)]
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "repair.jsonl"
        first = repair_bars(
            bars,
            [{"date": "2026-09-01", "open": 3.95, "high": 4.04, "low": 3.91, "close": 4.02}],
        )
        append_repair_record(log, first)
        append_repair_record(log, first)
        lines = log.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        record = json.loads(lines[0])
        assert record["schema_version"] == "ashare_bar_repair_log.v1"
        assert record["applied"][0]["old"]["close"] == 402.0
        assert record["applied"][0]["new"]["close"] == 4.02


def test_repair_refuses_wrong_schema_record() -> None:
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "repair.jsonl"
        with pytest.raises(ValueError, match="repair_bars report"):
            append_repair_record(log, {"schema_version": "other"})
