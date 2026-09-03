# ashare-data-immunity

![PyPI version](https://img.shields.io/pypi/v/ashare-data-immunity.svg)
![PyPI downloads](https://img.shields.io/pypi/dm/ashare-data-immunity.svg)
![CI](https://github.com/holdout-labs/ashare-data-immunity/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue)

## 中文说明

`ashare-data-immunity` 面向 A 股日线数据质量检查。它可以校验和清洗
OHLCV 数据，按板块识别涨跌停和停牌，检查上市状态、覆盖范围与日期连续性，
并用 SHA-256 清单记录数据快照。它只负责发现和标记数据问题，不提供选股、
荐股或交易决策。主板风险警示股票（ST、*ST）的涨跌停按**日期感知**处理：
2026-07-06（沪深交易所规则变更生效日）前为 ±5%，当日起为 ±10%，与普通主板
一致；`detect_limits`/`price_limit_ratio` 按 bar 的日期自动选择口径。
具体规则仍应以交易所最新公告为准。

**Data immunity for A-share daily bars**: cleaning (NaN / OHLCV
validation), board-aware price-limit and suspension detection, quality
audit (listing / coverage / continuity) and snapshot versioning (sha256
manifests). Python 3.11+, **zero dependencies**, Windows / Linux / macOS.

**Status:** v0.1.1 alpha, published on PyPI. The audit structure is distilled from a
production A-share pipeline; board rules follow the current exchange
conventions and should be re-checked against the exchanges' rule
documents before you rely on them.

## Why this exists

A-share daily data is not born clean. Vendors ship NaN closes, negative
opens, volume in lots or shares depending on the board, silent suspensions
that look like flat prices, and limit-up days that look like "huge moves"
unless you know the board's 10/20/30% rule. Every one of these corrupts a
factor pipeline differently, and most corrupt it *quietly*.

`ashare-data-immunity` is the immune system: it does not fetch data and it
does not trade —it makes the data you already have **honest**:

- **clean** —flag or sanitize non-finite values, non-positive prices,
  OHLC inconsistencies (high below max(open, close), low above
  min(open, close)), negative volume;
- **limits** —board-aware price-limit detection (main and main-board ST
  ±10%, STAR and ChiNext ±20%, BSE ±30%) against the previous
  close with tick rounding tolerance, plus a documented suspension
  heuristic (zero volume, or no prices on a dated row);
- **audit** —daily quality audit: are watched codes still listed, does
  history coverage meet the threshold, are there calendar gaps? All data
  sources injectable, results append-only;
- **snapshot** —sha256 manifests with cutoffs, so "which data did this
  backtest actually see" is a file you can compare and prove.

## Philosophy

**Data is an asset; immunity is a discipline.**

Most data tooling optimizes for *getting* data. This tool optimizes for
*trusting* the data you have —and it refuses to guess: board rules are
explicit tables, the suspension detector is documented as a heuristic
(vendor conventions differ), and the audit reports "universe unavailable"
instead of pretending the listing check ran. Read-only by design; every
function either returns a report or writes an append-only record. Nothing
here trades, prices, or decides.

## Quick start

```bash
# install the published package from PyPI
pip install ashare-data-immunity

# or run without installing anything:
#   PYTHONPATH=src python -m ashare_data_immunity --help

python examples/demo.py   # clean + limits + audit + snapshot on synthetic data
```

Your own data:

```bash
# 1. validate / clean a bars file
imm clean --bars bars.json                     # exit 1 when problems found
imm clean --bars bars.json --drop-non-positive --out clean.json

# 2. board-aware limits + suspensions
imm limits --bars bars.json --code 600000
imm limits --bars bars.json --code 688001 --st

# 3. daily quality audit (watchlist + history dir + append-only audit dir)
imm audit --watchlist watchlist.json \
  --history-root data/daily --audit-root data/audits

# 4. snapshot versioning
imm snapshot --name v2026-08-01 --cutoff 2026-08-01 \
  --files data/daily/*.json --root data --out manifests/v1.json
imm snapshot-compare --before manifests/v1.json --after manifests/v2.json
```

When the detector finds something wrong, repair it with provenance
(overwrite existing bars only, append-only log):

```bash
imm repair --bars bars.json \
  --corrections 'corrections.json' --code 600000 \
  --note "watchdog case: OHLC scale corruption" \
  --log repairs.jsonl --out bars_fixed.json
```

## Commands

| Command | What it does |
| --- | --- |
| `clean` | Validate bars (missing/non-finite/non-positive fields, OHLC consistency, negative volume); optionally sanitize (non-finite and non-positive prices -> `None`, volume kept >=0) and optionally drop non-positive rows |
| `limits` | Board classification, price-limit events (up/down with ratio and limit price) and suspension days for one code |
| `audit` | Listing (codes not in the injected universe), history coverage, calendar continuity; appends a JSONL record per day |
| `snapshot` | sha256 manifest of a file list with name + cutoff |
| `snapshot-compare` | added / removed / changed files between two manifests |
| `repair` | Apply reviewed OHLC corrections to existing bars (unknown dates / inconsistent OHLC are skipped and reported); optional append-only JSONL repair log and `--out` for the repaired bars |
| `version` | Print version |

## Board rules (v0.1, current from 2026-07-06)

| Board | Prefixes | Limit |
| --- | --- | --- |
| main | 60xxxx / 00xxxx | ±10% (including ST / *ST) |
| STAR | 688 / 689 | ±20% |
| ChiNext | 300 / 301 | ±20% |
| Beijing SE | 43x / 83x / 87x / 920 | ±30% |
| unknown | —| ±10% (assumed main) |

Limit detection compares `close` against `round(prev_close × (1 ± ratio), 2)`
with a default tolerance of 0.001 for vendor rounding conventions. The
first bar has no reference and is never flagged. The main-board 10% rule,
including risk-warning stocks, follows the Shanghai Stock Exchange's
[Trading Rules (2026 revision)](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml),
effective 2026-07-06. **Verify the tables against the current exchange rule
documents before production use** —the tool's job is to make the rules
explicit, not to invent them.

Suspension heuristic: a dated row with zero volume, or with no prices at
all, is a suspension day. Documented, not hidden —and toggleable
(`zero_volume_means_suspended`).

## Development

```bash
python -m pip install -e . pytest
python -m pytest
```

CI runs the full test suite on Ubuntu, Windows and macOS with Python 3.11
and 3.12. Issues are handled on weekends; pull requests are welcome.

## Related work

This tool makes no claims to novelty of its own: it is the engineering
layer under the data-quality principles that the industry is converging on
—point-in-time discipline ([Kelly et al., NBER w35247](https://www.nber.org/papers/w35247)),
look-ahead awareness ([Fonseca 2026, arXiv:2607.04958](https://econpapers.repec.org/paper/arxpapers/2607.04958.htm))
and reproducible snapshots. The pieces that *are* worth citing live in the
sibling repos of this project family; this one just keeps the data honest.

## Project family

Part of [Holdout](https://github.com/holdout-labs) — a toolchain
against self-deception in quantitative research:

- [pit-adjuster](https://github.com/holdout-labs/pit-adjuster) — PIT back-adjustment with static forward-adjustment drift detection
- [falsification-ledger](https://github.com/holdout-labs/falsification-ledger) — pre-registration and falsification ledger
- [factor-qc](https://github.com/holdout-labs/factor-qc) — fail-closed backtest quality gate
- [lesson-book](https://github.com/holdout-labs/lesson-book) — tuition memory for traders
- [lookahead-free](https://github.com/holdout-labs/lookahead-free) — verifiable look-ahead-freedom checks
- [ashare-data-immunity](https://github.com/holdout-labs/ashare-data-immunity) — data immunity for A-share daily bars

Sister org: [Metabolism Tools](https://github.com/metabolism-tools) — [`workspace-metabolism`](https://github.com/metabolism-tools/workspace-metabolism), policy-driven file lifecycle management for agentic workspaces.

## License

MIT
