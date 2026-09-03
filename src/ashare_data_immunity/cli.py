"""Command-line interface for ashare-data-immunity.

Subcommands:

- ``clean``           validate/clean a bars JSON file
- ``limits``          board-aware price-limit and suspension detection
- ``audit``           quality audit (listing / coverage / continuity)
- ``snapshot``        build a sha256 manifest for a list of files
- ``snapshot-compare`` compare two manifests
- ``repair``          apply reviewed OHLC corrections with an append-only log
- ``version``         print version
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .audit import run_quality_audit
from .cleaning import clean_bars, validate_bars
from .limits import board_of, detect_limits, suspension_days
from .repair import append_repair_record, repair_bars
from .snapshot import build_snapshot, compare_snapshots


def _print_json(body: Any) -> None:
    print(json.dumps(body, ensure_ascii=False, indent=2))


def _load_bars(path: str) -> list[dict[str, Any]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"bars must be a JSON list: {path}")
    return [row for row in value if isinstance(row, dict)]


def _load_manifest(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"manifest must be a JSON object: {path}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="imm",
        description="Data immunity for A-share daily bars.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    clean = sub.add_parser("clean", help="validate/clean a bars JSON file")
    clean.add_argument("--bars", required=True)
    clean.add_argument("--drop-non-positive", action="store_true")
    clean.add_argument("--out", default=None, help="write cleaned bars JSON")

    limits = sub.add_parser("limits", help="price-limit and suspension detection")
    limits.add_argument("--bars", required=True)
    limits.add_argument("--code", required=True)
    limits.add_argument("--st", action="store_true", help="ST status (main board -> 10 percent)")

    audit = sub.add_parser("audit", help="quality audit")
    audit.add_argument("--watchlist", required=True, help="watchlist JSON (eligible_codes or members)")
    audit.add_argument("--history-root", required=True, help="directory of <code>.json bars files")
    audit.add_argument("--audit-root", required=True, help="append-only audit output directory")

    snapshot = sub.add_parser("snapshot", help="build a sha256 manifest")
    snapshot.add_argument("--name", required=True)
    snapshot.add_argument("--cutoff", required=True)
    snapshot.add_argument("--files", nargs="+", required=True)
    snapshot.add_argument("--out", required=True, help="manifest JSON output path")
    snapshot.add_argument("--root", default=None, help="strip this prefix from stored paths")

    snap_compare = sub.add_parser("snapshot-compare", help="compare two manifests")
    snap_compare.add_argument("--before", required=True)
    snap_compare.add_argument("--after", required=True)

    repair = sub.add_parser("repair", help="apply reviewed OHLC corrections (existing bars only)")
    repair.add_argument("--bars", required=True, help="bars JSON list to repair")
    repair.add_argument("--corrections", required=True, help="JSON list of {date, open, high, low, close}")
    repair.add_argument("--code", default="", help="code label recorded in the log")
    repair.add_argument("--note", default="", help="why this repair happens (recorded in the log)")
    repair.add_argument("--log", default=None, help="append-only JSONL repair log path")
    repair.add_argument("--out", default=None, help="write repaired bars JSON")

    sub.add_parser("version", help="print version")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    if args.command == "clean":
        bars = _load_bars(args.bars)
        problems = validate_bars(bars)
        cleaned, counts = clean_bars(bars, drop_non_positive=args.drop_non_positive)
        if args.out:
            Path(args.out).write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
        _print_json({"problems": problems, "counts": counts})
        return 0 if not problems else 1

    if args.command == "limits":
        bars = _load_bars(args.bars)
        board = board_of(args.code)
        _print_json(
            {
                "code": args.code,
                "board": board,
                "board_label": {
                    "main": "main board",
                    "star": "STAR market",
                    "chinext": "ChiNext",
                    "bse": "Beijing SE",
                    "unknown": "unknown",
                }.get(board, board),
                "limit_events": detect_limits(bars, args.code, is_st=args.st),
                "suspension_days": suspension_days(bars),
            }
        )
        return 0

    if args.command == "audit":
        record = run_quality_audit(
            watchlist_path=args.watchlist,
            history_root=args.history_root,
            audit_root=args.audit_root,
        )
        _print_json(record)
        return 0 if record["passed"] else 1

    if args.command == "snapshot":
        manifest = build_snapshot(
            args.files,
            name=args.name,
            cutoff=args.cutoff,
            out_path=args.out,
            root=args.root,
        )
        _print_json(manifest)
        return 0 if not manifest["missing"] else 1

    if args.command == "snapshot-compare":
        before = _load_manifest(args.before)
        after = _load_manifest(args.after)
        result = compare_snapshots(before, after)
        _print_json(result)
        return 0 if result["equal"] else 1

    if args.command == "repair":
        bars = _load_bars(args.bars)
        corrections = _load_bars(args.corrections)
        report = repair_bars(
            bars, corrections, code=args.code, note=args.note
        )
        if args.out:
            Path(args.out).write_text(
                json.dumps(report["bars"], ensure_ascii=False, indent=2), encoding="utf-8"
            )
        if args.log:
            append_repair_record(args.log, report)
        _print_json(
            {
                "schema_version": report["schema_version"],
                "code": report["code"],
                "applied_count": report["applied_count"],
                "skipped_count": report["skipped_count"],
                "skipped": report["skipped"],
                "safety": report["safety"],
            }
        )
        return 0 if report["skipped_count"] == 0 else 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
