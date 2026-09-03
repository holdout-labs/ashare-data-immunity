# Changelog

## [0.1.3] - 2026-09-03
- feat: `imm repair` — evidence-tracked bar repair: reviewed OHLC corrections overwrite existing bars only (unknown date / invalid OHLC skipped and reported), append-only JSONL repair log. Dogfood backfill of the 2026-09 scale-corruption incident.

## [0.1.2] - 2026-09-02
- feat: date-aware ST ratio — main-board ST/*ST ±5% before 2026-07-06, ±10% from then, chosen per bar date (dual-track ruling).

## [0.1.1] - 2026-08-18
- Initial public release: A-share daily-bar cleaning, board-aware limits, suspensions, audits, SHA-256 snapshots.
