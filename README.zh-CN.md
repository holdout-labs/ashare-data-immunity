# ashare-data-immunity

![PyPI version](https://img.shields.io/pypi/v/ashare-data-immunity.svg)
![PyPI downloads](https://img.shields.io/pypi/dm/ashare-data-immunity.svg)
![CI](https://github.com/holdout-labs/ashare-data-immunity/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue)

## 中文说明

`ashare-data-immunity` 面向 A 股日线数据质量检查。它可以校验和清洗
OHLCV 数据，按板块识别涨跌停和停牌，检查上市状态、覆盖范围与日期连续性，
并用 SHA-256 清单记录数据快照。它只负责发现和标记数据问题，不提供选股、
荐股或交易决策。主板风险警示股票（ST、*ST）的涨跌停按当前 10% 规则处理，
具体规则仍应以交易所最新公告为准。

**A 股日线数据的免疫**：清洗（NaN / OHLCV 校验）、按板块识别涨跌停和停牌
检测、质量审计（上市状态 / 覆盖范围 / 连续性）以及快照版本管理（sha256
清单）。Python 3.11+，**零依赖**，支持 Windows / Linux / macOS。

**状态：** v0.1.1 alpha，已发布至 PyPI。审计结构提炼自生产环境中的 A 股数据
管道；板块规则遵循交易所现行惯例，在依赖这些规则之前，应重新对照交易所的
规则文件进行核实。

## 为什么存在

A 股日线数据并非生来干净。数据商交付的数据里可能有 NaN 收盘价、负开盘价、
因板块而异以"手"或"股"为单位的成交量、看起来像横盘的隐性停牌，以及——除非
你了解所在板块 10% / 20% / 30% 的涨跌幅规则——看起来像"巨大波动"的涨停日。
这些问题中的每一个都会以不同的方式污染因子流水线（factor pipeline），而且
大多数是*悄无声息*地污染。

`ashare-data-immunity` 就是这套免疫系统：它不抓取数据，也不进行交易——它只是
让你已有的数据变得**诚实**：

- **clean（清洗）** ——标记或净化非有限值、非正价格、OHLC 不一致（最高价低于
  max(开盘价, 收盘价)、最低价高于 min(开盘价, 收盘价)）、负成交量；
- **limits（涨跌停）** ——按板块识别涨跌停（主板及主板 ST ±10%，科创板
  （STAR）与创业板（ChiNext）±20%，北交所（BSE）±30%），与前一收盘价比较，
  并带最小报价单位（tick）舍入容差；另有文档化的停牌启发式规则（零成交量，
  或带日期的行上无任何价格）；
- **audit（审计）** ——每日质量审计：被监控的代码是否仍在上市状态，历史覆盖
  是否达到阈值，是否存在日历缺口？所有数据源均可注入，结果只追加
  （append-only）；
- **snapshot（快照）** ——带截止日期（cutoff）的 sha256 清单，于是"这次回测
  实际看到了哪些数据"成为一份你可以比较和证明的文件。

## 理念

**数据是资产；免疫是一种纪律。**

大多数数据工具致力于*获取*数据。这个工具致力于*信任*你已有的数据——并且它
拒绝猜测：板块规则是显式表格，停牌检测器被明确文档化为启发式规则（各数据商
的约定不同），审计在无法执行上市状态检查时会报告"universe unavailable（股票
池不可用）"，而不是假装检查已经运行。按设计只读（read-only）；每个函数要么
返回一份报告，要么写入一条只追加的记录。这里没有任何东西会交易、定价或决策。

## 快速开始

```bash
# install the published package from PyPI
pip install ashare-data-immunity

# or run without installing anything:
#   PYTHONPATH=src python -m ashare_data_immunity --help

python examples/demo.py   # clean + limits + audit + snapshot on synthetic data
```

使用你自己的数据：

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

## 命令

| 命令 | 作用 |
| --- | --- |
| `clean` | 校验 K 线数据（缺失 / 非有限 / 非正字段、OHLC 一致性、负成交量）；可选地净化（非有限和非正价格 -> `None`，成交量保持 >=0），并可选择丢弃非正行 |
| `limits` | 板块分类、单只代码的涨跌停事件（涨 / 跌，含涨跌幅与涨跌停价）及停牌日 |
| `audit` | 上市状态（不在注入股票池中的代码）、历史覆盖、日历连续性；每天追加一条 JSONL 记录 |
| `snapshot` | 文件列表的 sha256 清单，带名称（name）与截止日期（cutoff） |
| `snapshot-compare` | 两份清单之间的新增 / 删除 / 变更文件 |
| `version` | 打印版本号 |

## 板块规则（v0.1，自 2026-07-06 起现行）

| 板块 | 代码前缀 | 涨跌幅限制 |
| --- | --- | --- |
| 主板 | 60xxxx / 00xxxx | ±10%（含 ST / *ST） |
| 科创板（STAR） | 688 / 689 | ±20% |
| 创业板（ChiNext） | 300 / 301 | ±20% |
| 北交所（BSE） | 43x / 83x / 87x / 920 | ±30% |
| 未知 | —| ±10%（按主板假设） |

涨跌停检测将 `close` 与 `round(prev_close × (1 ± ratio), 2)` 进行比较，默认
容差为 0.001，以兼容各数据商的舍入惯例。第一根 K 线没有参照，永远不会被标记。
主板的 10% 规则（含风险警示股票）遵循上海证券交易所的
[《交易规则（2026 年修订）》](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml)，
自 2026-07-06 起生效。**在生产环境使用前，请依据交易所现行规则文件核对上述
表格**——这个工具的职责是让规则显式化，而不是凭空发明规则。

停牌启发式规则：带有日期、但成交量为零（或完全没有价格）的行视为停牌日。
这是公开文档化的规则，而非隐藏逻辑——并且可以切换
（`zero_volume_means_suspended`）。

## 开发

```bash
python -m pip install -e . pytest
python -m pytest
```

CI 在 Ubuntu、Windows 和 macOS 上使用 Python 3.11 和 3.12 运行完整测试套件。
Issues 在周末处理；欢迎提交 pull request。

## 相关工作

这个工具并不声称自身有什么新颖之处：它是行业正在趋同的数据质量原则之下的
工程层——时点纪律（point-in-time discipline）
（[Kelly et al., NBER w35247](https://www.nber.org/papers/w35247)）、前瞻意识
（look-ahead awareness）（[Fonseca 2026, arXiv:2607.04958](https://econpapers.repec.org/paper/arxpapers/2607.04958.htm)）
以及可复现的快照。真正值得引用的部分位于这个项目家族的同级仓库中；本仓库
只是让数据保持诚实。

## 项目家族

属于 [Holdout](https://github.com/holdout-labs) 的一部分——一个对抗量化研究
中的自我欺骗的工具链：

- [pit-adjuster](https://github.com/holdout-labs/pit-adjuster) ——时点（PIT）后复权（back-adjustment），带静态前复权漂移检测
- [falsification-ledger](https://github.com/holdout-labs/falsification-ledger) ——预注册与证伪台账
- [factor-qc](https://github.com/holdout-labs/factor-qc) ——失败即关闭（fail-closed）的回测质量门禁
- [lesson-book](https://github.com/holdout-labs/lesson-book) ——交易者的学费记忆
- [lookahead-free](https://github.com/holdout-labs/lookahead-free) ——可验证的无前瞻（look-ahead-free）检查
- [ashare-data-immunity](https://github.com/holdout-labs/ashare-data-immunity) ——A 股日线数据的免疫

姊妹组织：[Metabolism Tools](https://github.com/metabolism-tools) ——
[`workspace-metabolism`](https://github.com/metabolism-tools/workspace-metabolism)，
面向智能体工作区（agentic workspaces）的、由策略驱动的文件生命周期管理。

## 许可证

MIT
