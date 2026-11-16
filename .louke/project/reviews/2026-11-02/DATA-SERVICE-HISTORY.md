# 数据服务完整设计（发行版：现状审计与目标架构）

> 目标：为 Quantide 发行版提供**可插拔数据源**、**高性能本地存储**、**统一行情契约**、
> **仅模拟交易**的执行链路，并支持**集合竞价收盘价买入**。
> 本设计基于对现有代码的实测（Pro 机器，2026-10-22），所有数据源结论均已验证。
>
> 本文同时是一次**只读审计**：`现状`描述当前代码已经做什么，`目标`描述推荐的
> 可靠替换架构。目标架构中的候选抓取、验证、来源纪元和原子提升尚未实现；本次只更新
> 文档，不实现代码、提交或部署。

---

## 0. 现状盘点（实测结论）

| 项 | 现状 | 证据 |
|---|---|---|
| 因子库 | **不存在**。`quantide/factors/` 只有 `alpha.py`（因子计算）+ `catalog.py`（清单）+ `alphatest.py`（单因子检验），是**策略内部用的因子函数**，不是独立的因子库服务 | `ls quantide/factors/` |
| 本地存储 | Parquet + polars，按 `partition_key_year` 年分区，单文件 `part-0.parquet` | `quantide/data/stores/base.py` |
| 日线数据量 | 3,914,025 行（5678 只 × 724 交易日，2023-10-23 起） | Pro 实测 |
| 指数行情 | `IndexBarsStore` 已实现，且同步链路已落地；覆盖数据以本地实际分区为准 | `quantide/data/stores/index_bars.py` / `DataSyncService` |
| 指数成分 | `IndexWeightStore` + Tushare PIT 逐期同步已实现；覆盖范围取决于本地快照 | `quantide/data/stores/index_weight.py` / `DataSyncService` |
| 行情端口 | `MarketDataPort` 协议 + `QuoteSnapshot` 数据类**已定义好**（symbol/price/open/high/low/volume/amount/ts） | `quantide/core/ports/market_data.py` |
| 行情实现 | `MarketDataHub` 是唯一实时行情端口；发布者通过 `quotes.all` 提供快照 | `quantide/service/market_data_hub.py` |
| 模拟撮合 | `PaperBroker._try_match` 消费 `lastPrice/high/low/volume` → **行情字段需求已明确** | `quantide/service/sim_broker.py:772` |
| 同步任务 | `DataSyncService` 已统一编排日历、证券列表、日线、市值、指数、成分和分钟阶段；部分旧向导路径仍是 legacy 直拉 | `quantide/service/data_sync.py` |
| 存储性能基线 | 面板读 80 天全市场（31 万行）**0.002s**；单资产 120 天 **0.003s** | Pro 实测 |

---

## 1. 分层架构（目标）

```
┌─────────────────────────────────────────────────────────────┐
│ L4 应用层：回测 / 参数优化 / Paper / 归因 / 因子台账            │
├─────────────────────────────────────────────────────────────┤
│ L3 领域服务层（新增）                                          │
│   · DataService      统一数据门面（回测/优化器只认它）            │
│   · MarketDataHub    统一行情契约（用户接入的唯一入口）            │
│   · ExecutionClock   交易日历 + 集合竞价时序（决定何时算信号/下单）  │
├─────────────────────────────────────────────────────────────┤
│ L2 存储层（本地，只读快照 + 列存）                              │
│   · DailyBarsStore   个股日线（年分区 + 列裁剪 + 统计信息）          │
│   · IndexBarsStore   指数日线（复用）                           │
│   · IndexWeightStore 指数成分快照 PIT（新增，按月分区）             │
│   · DailyBasicStore  市值/换手（已有）                           │
│   · StockList        证券主数据（已有）                          │
│   · LimitPriceStore  涨跌停价（新增：撮合必需，当前只在内存）        │
├─────────────────────────────────────────────────────────────┤
│ L1 数据源层（按数据集/周期可替换；不是全局主备）                    │
│   · TushareFetcher   日线/复权/市值/ST/涨跌停/指数/指数成分          │
│   · BaoStockFetcher  历史 30 分钟（目标范围内）                     │
│   · TencentFetcher   快照/近期 K 线/指数日线补充                     │
├─────────────────────────────────────────────────────────────┤
│ L0 实时层（用户自备）                                          │
│   · 发布者（HTTP/WS/SDK） → MarketDataHub（唯一实时入口）           │
│   · 官方/示例发布者：TencentPublisher、AkSharePublisher             │
└─────────────────────────────────────────────────────────────┘
```

**关键原则**
1. **回测/优化器只依赖 L2/L3，不直接碰 L1** → 换数据源不影响策略与回测语义。
2. **实时行情只有一条通路**（L0 → L3 MarketDataHub → PaperBroker）→ Paper 消费的数据格式**固定统一**。
3. **只支持模拟交易**：删除/禁用 live 交易路径（券商网关），保留 gateway 仅作"未来可选"。

### 1.1 现状与目标的边界

| 范围 | 现状（代码审计） | 目标（推荐设计） |
|---|---|---|
| 历史数据路由 | `MultiSourceDataFetcher` 按数据集列出有限的 fetcher 顺序；调用时返回第一个非空结果。 | 只选择声明具备该数据集/周期/区间能力的候选，并把候选先写入 staging。 |
| 自动切换 | **没有可依赖的自动切换**。当前“首个非空”逻辑没有完整质量判定、重叠比对或原子提升，不能作为生产级切换策略。 | 验证通过后按数据集策略提升候选；实时与历史互不形成全局 fallback。 |
| 同步 | `DataSyncService` 已是持久化、可恢复、互斥的统一阶段编排器。 | 继续只有一个同步编排器，并将候选验证、比对、提升纳入其阶段。 |
| 实时行情 | `MarketDataHub` 订阅 `quotes.all` 并维护唯一快照/事件视图；`livequote` 已退役，仅保留兼容别名。 | 所有实时发布者只能进入 `MarketDataHub`，Paper/风控/UI 只读 Hub。 |
| 事实记录 | 本地 store 主要保存规范化数据，来源、来源纪元和验证证据不是一等的读模型。 | 每个已提升数据集都有 provenance、source epoch、验证报告和可回退 manifest。 |

这里的“没有自动切换”是有意的安全结论：当前的顺序尝试是 best-effort fetch fallback，
不是经过验证的 source promotion。任何空响应、网络异常或字段缺失都不能仅凭“下一个
provider 返回了数据”改变已经发布的数据集。

---

## 2. 成分股信息：怎么取、怎么存

### 2.1 取（已实测，含一个关键坑）

Tushare `index_weight`：**按月快照 = 天然 PIT ✅**。相邻快照成分变动实测"新进 201 / 剔除 1"，
用 `trade_date <= 决策日` 取最近一期 → **无前视**。

**⚠️ 关键坑：区间查询有 7000 行硬上限**（滚动窗口），实测：

```
index_weight("000300.SH", 20150101~20261022) → 7000 行 = 24 期，最早 2024-10-31
分段查询也无效（分两段都还是 7000 行，各自覆盖最近 24 期）
```

**✅ 破解办法：逐期按 `trade_date` 精确查询**（不受上限约束）：

```
index_weight("000300.SH", trade_date="20240131") → 300 行 ✅
index_weight("000300.SH", trade_date="20230131") → 300 行 ✅
index_weight("000300.SH", start_date="20150101", end_date="20151231") → 3600 行(12期) ✅
```

**实测各指数 PIT 历史深度**（逐期探测 2010~2026，每年 3 个采样点）：

| 指数 | 代码 | 每年成分数 | PIT 快照可得范围 | 备注 |
|---|---|---|---|---|
| 沪深300 | `000300.SH` | 300 | **2010 ~ 2026** ✅ | 全历史可用 |
| 中证500 | `000905.SH` | 500 | **2010 ~ 2026** ✅ | 全历史可用 |
| 创业板指 | `399006.SZ` | 100 | **2010 ~ 2026** ✅ | 全历史可用 |
| 中证A100 | `000903.SH` | 100 | **2010 ~ 2026** ✅ | 全历史可用 |
| 上证50 | `000016.SH` | 50 | **2010 ~ 2026** ✅ | 全历史可用 |
| 中证1000 | `000852.SH` | 1000 | **2015 ~ 2026** | 指数 2015 才发布 |
| 中证2000 | `932000.CSI` | 2000 | **2023 ~ 2026** | 指数 2023 才发布 |

→ **同步策略**：按"月份"逐期拉（不是按区间拉）→ 每个快照日 1 次调用 →
17 年 × 12 期 = **204 次调用/指数** → 7 个指数 ≈ 1400 次调用，按 3 次/秒 ≈ **8 分钟** ✅

**其它接口探测结论**：
- `index_member_all` → 是**申万行业分类**（801xxx.SI），不是宽基指数 ❌
- `index_stock_cons` / `index_stock_cons_csindex` / `index_weight_all` → 接口不存在 ❌
- `ths_member` → 空 ❌（同花顺在另一个接口族）

### 2.2 存（关键设计）

**不要**存成"指数 → 成分列表"的宽表。存成**长表事件流**：

```
data/index_weight/partition_key_year=2024/part-0.parquet
  date        (Date)   ← 快照日（月末）
  index_code  (Utf8)   ← 000300.SH
  con_code    (Utf8)   ← 600519.SH
  weight      (Float64)
```

**为什么这样存**（4 个理由，都是实测驱动的）：

| 理由 | 说明 |
|---|---|
| **查询形态** | 策略只需要"某日某指数的成分" → 查询永远是 `date = (≤D 的最近快照) AND index_code = X` → 长表上是一次带 filter 的列扫，**结果集极小**（300~1000 行）→ 毫秒级 |
| **写入形态** | 每次同步只新增 1 个月末快照 → **追加即可，不需要重写**（年分区 → 每年一个文件）→ 与日线 store 的 `append_data` 同一套机制 ✅ |
| **去重** | `(date, index_code, con_code)` 是主键 → `unique(subset=id_cols, keep="last")` 幂等 ✅ 重跑同步不会脏 |
| **可扩展** | 加指数 = 加几行数据，不用改表结构；未来可加"权重变化率""成分股历史" |

**与日线 store 复用同一基类** `ParquetStorage`：
- 存储路径：`data/index_weight/partition_key_year=YYYY/part-0.parquet`（年分区，与日线一致）
- 主键列：默认 `["date", "asset"]` → 需要子类覆盖为 `["date", "index_code", "con_code"]`（**这是基类要新增的一个可配置项**）

### 2.3 读 API（PIT 语义）

```python
class IndexWeightStore(ParquetStorage):
    def constituents(self, index_code: str, as_of: date) -> pl.DataFrame:
        """返回 as_of 当日**可见**的成分（含权重）。

        语义：取 trade_date <= as_of 的最近一个快照日 → 严格 PIT，无前视。
        """
```

策略侧新增 `universe_mode="index_pit"`：
- 用 `as_of = 信号日` 取成分 → 再叠加现有的流动性/市值过滤 → 完全无前视
- 这同时修掉一个现有隐患：现在 `universe_mode=market_cap_trim` 用**当前**市值做截断，
  成分有轻微前视 ⚠️；`index_pit` 模式彻底干净。

### 2.4 存储量估算

沪深300+中证500+中证1000+中证2000+创业板 ≈ 2000 只 × 12 月 × 10 年 = **24 万行/年** → 约 8MB/年 → 10 年 80MB。**微不足道**。

---

## 3. 指数行情：怎么取、怎么存

- 取：Tushare `index_daily(ts_code, start_date, end_date)` → 沪深300 回溯到 **2010-01-04**（4078 行），
  单年 244 行，5 年 2.35 秒 → **极快**。
- 存：**复用已有 `IndexBarsStore`**（`data/bars/index/`），字段 `sector_id/open/high/low/close/volume/amount`。
  - 需要把 `sector_id` 改名语义为指数代码，或新增 `index_code` 列（推荐：加 `index_code` 列，保留 `sector_id` 兼容）
  - 分区：年分区 ✅
- 用途：**基准/超额**（回测报告里现在只有绝对收益）、市场 regime 判断、指数池策略的基准。

---

## 4. 统一行情契约（MarketDataHub 唯一实时入口）

### 4.1 契约（已存在，直接用）

```python
# quantide/core/domain/events.py
@dataclass
class QuoteSnapshot:
    symbol: str            # 统一代码格式：000001.SZ / 600519.SH
    price: float | None    # 最新价
    open: float | None
    high: float | None     # 当日最高（集合竞价期间 = 竞价价）
    low: float | None
    volume: float | None   # 累计成交量（股）
    amount: float | None   # 累计成交额（元）
    ts: datetime | None    # 行情时间戳

# quantide/core/ports/market_data.py
class MarketDataPort(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def subscribe(self, symbols: list[str]) -> None: ...
    def unsubscribe(self, symbols: list[str]) -> None: ...
    async def stream(self) -> AsyncIterator[MarketEvent]: ...
    def snapshot(self, symbols: list[str]) -> dict[str, QuoteSnapshot]: ...
```

**这就是"格式固定统一"的落点** ✅ —— 已有契约，不用新造。`PaperBroker` 已经按
`lastPrice/high/low/volume` 消费，适配器负责把用户的数据转成 `QuoteSnapshot` ✅。

### 4.2 用户接入方式（二选一）

**方式 A：进程内插件**（推荐，零进程间开销）
- 用户在自己的 Python 环境里实现一个 `MarketDataPort`，放到 `~/.quantide/plugins/market_data.py`，
  约定一个入口函数 `create_provider() -> MarketDataPort`。
- 启动时按 `settings.market_data_provider`（`plugin` / `tencent` / `sina` / `akshare`）加载。

**方式 B：HTTP 桥**（适合用户已有行情服务）
- 用户起一个 HTTP 服务，实现两个接口：
  - `GET /snapshot?symbols=000001.SZ,600519.SH` → `{"000001.SZ": {price, open, high, low, volume, amount, ts}, ...}`
  - `GET /stream`（SSE/WebSocket）→ 增量推送同结构
- 我们内置 `HttpMarketDataProvider` 读它。

**两种方式都只暴露上面那份 `QuoteSnapshot` 结构** → Paper 侧完全不变 ✅。

### 4.3 官方参考实现：AkshareProvider

```python
# quantide/data/providers/akshare_provider.py（参考实现，用户可复制改造）
class AkshareProvider:
    """基于 AkShare 的行情提供方（免费）。

    依赖：pip install akshare
    能力：snapshot（批量拉取）、stream（轮询转事件流）
    刷新：默认 3 秒轮询（交易时段）
    """
    def __init__(self, symbols: list[str], interval: float = 3.0): ...
    def snapshot(self, symbols) -> dict[str, QuoteSnapshot]: ...
```

**AkShare 覆盖的行情源**（可作为发布者实现的模板）：
- `ak.stock_zh_a_spot_em()` → 全市场实时快照（东财），一次调用覆盖所有股票 → **最适合 Paper**
- `ak.stock_zh_a_hist_min_em(symbol, period="1", ...)` → 分钟线历史
- `ak.stock_zh_index_daily_em(symbol="sh000300")` → 指数日线

### 4.4 腾讯发布者（实时来源，不是第二条实时入口）

实测三个免费源在 Pro 上**全部可用**（无需 token、无需付费）：

| 源 | 端点 | 字段 | 备注 |
|---|---|---|---|
| 腾讯 | `http://qt.gtimg.cn/q=sh000001,sz000001` | 88 字段 GBK | 可批量 50+ 代码，**1 次/秒无压力** |
| 新浪 | `http://hq.sinajs.cn/list=sh000001` | 34 字段 GBK（需 Referer） | 字段最干净 |
| 东财 | `http://push2.eastmoney.com/api/qt/stock/get?secid=1.000001` | JSON f 编码 | 需逐个 secid |

实测样例（腾讯，2026-10-22 收盘后）：
```
v_sh600519: name=贵州茅台 code=600519 现价=1318.49 昨收=1309.69 今开=1303.21
             最高=1322.00 最低=1296.00 成交量(手)=42491 成交额(万)=557622 时间=20261022161500
```
→ `high/low` **含当日最高最低** → 集合竞价期间可用作"竞价价" ✅（第 8 节要用）。

`TencentDataFetcher`/`TencentPublisher` 是一个可选的批量发布者：它把快照写入
`MarketDataHub` 的消息入口，不能被 Paper、风控或 UI 直接作为另一条实时通路读取。
腾讯不可用时，Hub 不会自行切换到另一个实时源；必须由配置的发布者或操作员提供有效数据。

### 4.5 涨跌停价

现状：`PaperBroker._get_price_limits` 可以从 `MarketDataHub` 读取发布者的实时限价；
`LimitPriceStore` 也已经存在并由 Tushare 刷新。目标：把本地存储作为日频静态数据的
主读路径（见 §5），实时发布者只作为明确的当日覆盖；涨跌停不应成为跨数据集的实时
source switch。用户源仍可在快照中提供 limit 字段。

---

## 5. L2 存储层：高性能要求（"10x 数据不降速"）

### 5.1 现状与风险

`ParquetStorage` 已经是列存 + 年分区 + polars lazy scan，**底子是对的**。但有两个会在 10x 时咬人的点：

**风险 1：写放大（`append_data` 全量重写分区）**
```python
# _save_as_partition：每个分区 base_lf + part_lf → concat → unique → sort → 全量 write_parquet
```
→ 每次增量同步都**重写该年的整个文件**。年数据量 10x（≈2500 万行）时，每次同步写 2500 万行 → 同步时间线性劣化 ❗
**修法**：改为**按年分片 + 行组**（每年 N 个 `part-{i}.parquet`），增量只写"新的行组文件"，
不重写历史 → 写入 O(新增量) ✅。同时用 `row_group_size` 控制粒度。

**风险 2：读路径缺列裁剪/统计信息**
`get()` 现在 `pl.scan_parquet("**/*.parquet")` → 每次都要 glob 全目录 + 打开所有文件的 footer。
10x 数据（10 年 × 5678 只 = 5000 万行）时：
- glob 的文件数变多（10 年 × 12 月组 = 120 文件）→ 元数据开销上升
- 没有按列裁剪的默认值（策略面板要 30+ 列，实际全部都要，收益有限）
- 没有 min/max 统计 → `date` 过滤只能靠 parquet 的 row group 统计（polars 会用 ✅，但前提是按 date 有序 → 需要保证写入时**按 (date, asset) 有序** ✅ 现有代码已 sort ✅）

**修法**：
1. **两级分区**：`partition_key_year` → 每月一个文件（`year=YYYY/month=MM/part.parquet`）→ 读 80 天只碰 4-5 个文件 ✅（现在是 1 个大文件，读全部行再过滤 → 10x 时扫描量 10x ❗❗ 这是当前最大的降速点）
2. **月级分区 + 覆盖列裁剪** → 读放大从 O(全量) 降到 O(目标窗口) ✅
3. **日期索引**：现有的 `dates.pq` 索引保留 ✅（用于判断缺哪些日期）
4. **写增量**：不重写历史文件 ✅

### 5.2 目标（可验证的判据）

| 场景 | 现在 | 10x 后目标 | 判据 |
|---|---|---|---|
| 面板读 80 天全市场 | 0.002s | **< 0.05s** | 读取行数 ∝ 窗口，不随总量增长 |
| 单资产读 120 天 | 0.003s | **< 0.01s** | 走 asset 过滤 + 列裁剪 |
| 增量同步 1 天 | 重写整年文件 | **只写 1 个月文件** | 写入量 ∝ 新增行数 |
| 进程启动扫描目录 | 全量 collect 日期 | **只读索引文件** | 已有 `dates.pq` ✅，需补 `index_bars`/`index_weight` 的同款索引 |

### 5.3 具体改造清单（存储层）

1. `ParquetStorage` 支持**多级分区**（`partition_by=("year","month")`）→ 目录 `partition_key_year=YYYY/partition_key_month=MM/part.parquet`
2. `append_data` 改为**增量追加**：新数据按分区路由到文件；同分区同 key 冲突时才重写该分区
   （用 `pl.concat` + `unique` 但只对**目标分区**做，且只在数据量小的时候；否则写新文件 + 读时合并）
   → 更稳的做法：**每个 (year, month) 一个文件，月末同步时整体重写该月**（月数据量 ≈ 5678×21 = 12 万行 → 重写成本可接受 ✅）
3. 所有 store 统一 `_collect_dates()` → 写 `dates.pq` 索引（已有 ✅，扩展到 index_weight）
4. 新增 `LimitPriceStore`（涨跌停价，年分区，字段 date/asset/up_limit/down_limit）
5. `IndexWeightStore`（新增）
6. `IndexBarsStore` 补 `index_code` 列 + 索引

### 5.4 内存与并发

- 面板缓存已有上限（2 个面板 ≈ 110MB）✅；日线 store 的 `get()` 走 lazy → 不整表进内存 ✅
- 参数优化的 worker 进程各持一份缓存 → 4 worker × 110MB = 440MB ✅（Pro 64GB）

---

## 6. L1 数据源层（当前能力审计）

Tushare 是当前个股日线及其辅助字段的主源，但不是所有数据集的全局主源。
数据源必须按**数据集 + frame + 时间范围**判断能力；例如 Tushare 的日线能力不能
自动推导出它具备全市场历史 30 分钟能力，腾讯的实时快照也不能替代 PIT 成分或复权因子。
下面的实现清单描述当前适配器的实际边界，后文 §15 描述如何在不破坏这些边界的情况下
可靠替换来源。

### 6.1 已实现 fetcher 能力（`quantide/data/fetchers/tushare.py`）

以下是当前适配器已经提供的取数能力；“已实现”不等于已经具备 §15 的候选验证和
原子提升语义。

| 方法 | tushare 接口 | 频率/耗时（实测） | 用途 |
|---|---|---|---|
| `fetch_index_bars(dates, index_codes)` | `index_daily` | 5 年 2.35s | 基准/超额 |
| `fetch_index_weights(index_codes, start, end)` | `index_weight` | 按月，几十次调用 | PIT 成分 |
| `fetch_limit_price(dates)` | 已有 `stk_limit` ✅ | 单日 1.1s | 涨跌停（存储化） |
| `fetch_minute_bars(...)` | `stk_mins` | **1 次/分钟限频** ⚠️ | 可选，仅对持仓/候选 |
| `fetch_bars(dates)` | 已有 `daily` ✅ | 单日 0.2s | 日线 |
| `fetch_adjust_factor` | 已有 ✅ | 单日 0.13s | 复权 |
| `fetch_daily_basic` | 已有 ✅ | 单日 1.29s | 市值/换手 |
| `fetch_st_info` | 已有 ✅ | — | ST |

**重要限制**：`stk_mins` 限频 1 次/分钟 → **全市场 30 分钟历史不可行**（要跑数月）。
→ 决策：**分钟数据不进发行版核心**；若用户需要，提供"仅对候选池/持仓拉分钟"的工具函数（几十次调用 ✅）。

**回补 2015-2023 的实测成本**：
- 4 个接口 × 2200 交易日 ≈ 41 分钟/接口 → **并行约 1.5~2 小时**（Tushare 限频是每接口每分钟 N 次，可并发）
- 指数日线几乎免费（2.35s/5 年）
- → **发行版应内置"历史回补"向导**（选起始年份 → 后台跑 → 断点续传）

### 6.2 指数池代码表（实测确认）

| 名称 | tushare 代码 | PIT 成分历史 | 日线历史 | 备注 |
|---|---|---|---|---|
| 上证指数 | `000001.SH` | — | 2010+ | 基准 |
| 沪深300 | `000300.SH` | **2010+** ✅ | 2010+ | 首选基准 + 首选成分池 |
| 中证500 | `000905.SH` | **2010+** ✅ | 2010+ | |
| 中证1000 | `000852.SH` | 2015+ | 2014+ | |
| 中证2000 | `932000.CSI` | 2023+ | 2023+ | 指数 2023 才发布 |
| 创业板指 | `399006.SZ` | **2010+** ✅ | 2010+ | |
| 上证50 | `000016.SH` | **2010+** ✅ | 2010+ | |
| 中证A100 | `000903.SH` | **2010+** ✅ | 2010+ | |
| 中证全指 | `000985.CSI` | ❌ 仅 2 期 | 2010+ | **只作日线基准，不作成分池** |

**关键结论**：沪深300 / 中证500 / 创业板指 / 上证50 / 中证A100 的 PIT 成分可回溯到 **2010**
→ **指数池选股可以用于 2015-2023 的历史回测** ✅ → 直接解决"没有干净样本外"的问题。

**发行版应内置一张可配置的"关注指数表"**（`settings.index_codes`），并在 UI 列出每个指数
实际的 PIT 快照区间（从本地存储统计），让用户知道"这个指数从哪年开始才有成分"。

---

## 7. 同步任务（数据服务任务）

### 7.1 现状问题与遗留边界

- `DataSyncService` 已覆盖日历、证券列表、个股日线、市值、指数日线、PIT 成分和可选
  30 分钟历史；旧初始化向导/证券列表路径仍有直接 `asyncio.create_task` 或逐日拉取的
  legacy 入口，应该逐步收敛到统一编排器。
- 当前编排器已经持久化任务、断点阶段和同实例互斥，但还没有 §15 的 staging、完整
  验证、重叠比较、provenance/source epoch 和 manifest 原子提升。
- 个别旧逐日路径仍是 2200 天 = 2200 次 HTTP；统一路径可改为**按月批量**（Tushare
  `daily` 支持 `start_date/end_date` 区间 → 2200 天只需约 132 次调用）。

### 7.2 目标：一个统一的同步编排器

```
DataSyncService
  · 任务队列：DB 持久化（现有 failed_tasks 表可扩展）→ 进程重启后自动恢复
  · 单实例互斥（同一数据集不并发同步）
  · 阶段编排：
      1. calendar     （交易日历）—— 已有
      2. stock_list   （证券主数据）—— 已有
      3. daily_bars   （个股日线 + 复权 + ST + 涨跌停）← 合并 4 个接口为按月批量
      4. daily_basic  （市值/换手）
      5. index_bars   （指数日线）★新增
      6. index_weight （指数成分 PIT）
      7. minute_bars  （BaoStock 历史 30 分钟，可选）
  · 断点续传：每个阶段记录已完成区间 → 重跑只补缺口
  · 进度：复用 `fetch_data_progress` 主题 + SSE ✅（前端已有）
  · 失败重试：现有 `failed_tasks` 表 ✅
```

### 7.3 收益

- 按月批量 → 回补 2015-2023 从 41 分钟/接口 降到 **~3 分钟/接口**（132 次调用 × 1.3s）
- 指数/成分纳入同一任务 → 一次点击全量对齐
- 持久化队列 → 重启不丢

### 7.4 当前实现与可靠同步目标

`DataSyncService` 已经是当前唯一的同步编排器：任务持久化在 SQLite，阶段顺序固定，
同一进程内互斥，并支持取消、恢复和进度发布。旧的 web 入口可以创建任务，但不应再
各自直接编排 fetcher。

当前编排器仍主要负责“抓取后写入规范化 store”，尚未把候选 staging、完整验证、重叠
比较、provenance/source epoch 和 manifest 原子切换做成同步阶段。因此“任务成功”目前
只表示抓取/写入流程完成，不表示候选源已经通过可靠替换审计；这正是 §15 的目标补齐项。

---

## 8. 集合竞价收盘价买入（第 8 点需求）

### 8.1 现状

- 回测：信号日 = T-1（上一交易日收盘）→ **T 日开盘买入**（`BacktestBroker` 撮合 T 日 open ✅）
- Paper：实盘循环每 2 秒 `on_bar(now)` → 但**没有"按信号日去重"** → 会重复下单 ❗（我之前提过、一直没修）

### 8.2 目标：集合竞价（14:57-15:00）算信号 + 下单

A 股收盘集合竞价：**14:57-15:00**（3 分钟）→ 15:00 以集合竞价价格成交。

> 2026-10-27 更新：本节 14:57 只是 **1d + cheat_on_close** 的默认值；统一时序见
> `spec-strategy.md` FR-055。30m 使用每个 bar 结束前 2 分钟，1d 默认提前 3 分钟；
> `next_open` 使用下一 bar/交易日开盘，午休与收盘信号需持久化队列。

**时序设计**（新增 `ExecutionClock`）：

```
14:57:00  行情源开始提供集合竞价实时价（high/low/price = 竞价价）
14:57:00  → 策略在此刻用「截至 14:57 的实时价」算信号
          → 预算 2 分钟（14:57-14:59）完成因子/模型/排名
14:59:00  → 下单（限价 = 竞价价 + 容忍）
15:00:00  → 集合竞价撮合成交
```

**关键设计点**：
1. **信号计算用实时价**：策略的因子本来是日频（用当日 close）→ 集合竞价期间当日 close 还没定，
   但**集合竞价价格 ≈ 收盘价**（你的判断 ✅）→ 所以用 14:57 的竞价价替代"当日收盘价"计算因子 ✅
   → 这需要策略的因子计算支持"注入一个 override 收盘价"（见下）
2. **下单价**：用竞价价（或竞价价 × (1+容忍)）→ 成交价即集合竞价价 ✅
3. **3 分钟预算**：
   - 面板重建：全市场 2000 只 × 因子计算 ≈ **1.5s** ✅ 远够
   - 模型重训：45 天 × 2000 只 LightGBM ≈ **0.4~2.5s** ✅ 够
   - 排名/下单：毫秒级
   → **总耗时 < 5s**，3 分钟绰绰有余 ✅（当前回测里每 20 天重建面板 + 每 5 天重训的节奏，
   在 paper 场景应改为**每天**重建面板 + 重训 → 仍在 3 分钟内 ✅）
4. **降级策略**：若 14:59 前算不完 → 回退到"用 T-1 收盘信号，T+1 开盘买"（= 现在的回测语义）→ 记录告警 ✅

### 8.3 需要改的代码

| 位置 | 改动 |
|---|---|
| `quantide/service/strategy_runtime.py` | ① 循环改为**按交易日 + 时段**驱动（不是每 2 秒）；② 引入 `ExecutionClock` 判断"现在是集合竞价窗口"；③ **按信号日去重**（同一信号日只决策一次）❗ |
| `quantide/strategies/example/ml_momentum_reversal.py` | ① 因子计算支持"用实时价覆盖当日 close"（`price_override` 参数）；② 面板构建支持"当日未收盘"的模式 |
| `quantide/service/sim_broker.py` | 撮合支持"集合竞价成交"标记（成交价=竞价价，成交量按竞价量） |
| `quantide/core/ports/market_data.py` | 已有 `QuoteSnapshot.high/low` ✅ 可表达竞价价 |
| 回测侧 | 新增 `fill_timing` 配置：`next_open`（默认）/ `auction_close` → **回测也能模拟集合竞价成交** ✅（用当日 close 成交） |

### 8.4 回测与 Paper 的一致性

要能验证 Paper 行为，必须在**回测里也能复现集合竞价成交**：
- `fill_timing="auction_close"`：信号用 T-1 收盘（回测里没有盘中数据）→ 成交用 **T 日收盘价**
- 与真实 Paper 的差异：真实 Paper 用 14:57 竞价价（≈收盘价）→ 偏差可接受（可用 `slippage_pct` 覆盖）
→ 这样回测报告里的数字才和 Paper 可比 ✅

---

## 9. 只支持模拟交易（Paper only）

| 现状 | 处置 |
|---|---|
| `deploy_to_live` → 券商网关 | **移除/禁用**（发行版不接实盘） |
| `GatewayBrokerAdapter` / `GatewayClient` | 保留代码但**默认不注册**；实时行情仍只由 `MarketDataHub` 提供 |
| `LiveQuote` / `live_quote` | **已退役**：旧 websocket、独立缓存和发布逻辑已移除；模块只保留到 `MarketDataHub` 的兼容别名 |
| `PaperBroker` | **强化为唯一执行路径** |
| 运行时模式 | `runtime_mode` 只允许 `backtest` / `paper`（去掉 `live`） |
| 撮合 | `PaperBroker` 消费 `MarketDataPort` 快照 ✅（已有） |

**Paper 的行情从哪来**（用户自备）：
- `TencentPublisher` 可作为免费、批量的发布者；它必须把数据送入 `MarketDataHub` ✅
- 用户可换 `AkSharePublisher`、自带发布者或 HTTP 桥，但 Paper 永远只从 `MarketDataHub` 读取

---

## 10. 实施顺序（建议）

| 阶段 | 内容 | 产出 | 预估 |
|---|---|---|---|
| **P0** | 存储性能改造：两级分区（年+月）+ 增量写 + 列裁剪 | 10x 数据不降速 | 2-3 天 |
| **P0** | `LimitPriceStore` + `IndexWeightStore` + `IndexBarsStore` 补 `index_code` | 三个新存储 | 2 天 |
| **P0** | Tushare 新增 `fetch_index_bars` / `fetch_index_weights` | 数据源能力 | 0.5 天 |
| **P1** | `DataSyncService` 统一编排（持久化队列 + 按月批量 + 断点续传） | 同步任务可靠 | 2-3 天 |
| **P1** | `MarketDataHub` + `TencentProvider` + `AkshareProvider`（参考实现）+ 插件/HTTP 桥 | 统一行情契约落地 | 2-3 天 |
| **P1** | Paper 链路：按日去重 + `ExecutionClock` + 集合竞价下单 | Paper 可用 | 3-5 天 |
| **P2** | 回测 `fill_timing="auction_close"` + 基准/超额指标 + 指数池选股 | 回测与 Paper 一致 | 2-3 天 |
| **P2** | 历史回补向导（2015-2023） | 干净样本外 | 1 天 |
| **P3** | 发行版打包：配置向导（tushare token、指数选择、行情源选择）、文档 | 可发行 | 2 天 |

---

## 11. 需要你拍板的点

1. **指数成分的历史覆盖**：中证1000 只有 7 期快照、中证2000 待确认 → 指数池策略在早期年份不可用。
   是否接受"指数池策略只支持有快照的区间"？还是要求"用全市场等权/市值代理"做兜底？
2. **回补起始年**：2015 还是 2010？（2010 起更久，但 Tushare 限频下 2010-2026 ≈ 4000 交易日 × 4 接口 ≈ 3 小时）
3. **集合竞价的容差**：下单用"竞价价"还是"竞价价 ×(1+ε)"（ε 默认 0.1%？），以及"算不完则回退 T+1 开盘"的阈值是否 2 分钟。
4. **是否保留 30 分钟数据**：我的建议是**不做全市场**，只提供"按需拉候选池分钟线"的工具；你认可吗？
5. **发行版是否强制要求 tushare token**：没有 token 就无法初始化（当前 `fetch_stock_list` 等都依赖它）→ 是否给"仅离线模式"（用已有 parquet，不做同步）？

---

## 12. 实施进展（2026-10-23）

### 12.1 已落地

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 存储两级分区（年+月）、目录裁剪读、增量写、`repartition_to_levels()` 迁移 | ✅ |
| P0 | `IndexWeightStore`（PIT 成分）/ `LimitPriceStore` / 指数日线 | ✅ |
| P0 | Tushare `fetch_index_bars` / `fetch_index_weights`（逐期绕过 7000 行上限） | ✅ |
| P0 | `Date`/`Datetime` 日期列归一化（`date_as_date` + `normalize_partition_schema`） | ✅ |
| P1 | `DataSyncService`（六阶段、持久化、断点续传、互斥、取消、按月批量） | ✅ |
| P1 | 行情管理页「手动补全」接入统一同步服务（可选指数代码、进度流） | ✅ |
| P1 | `MarketDataHub` 发布/订阅 + 发布者协议；腾讯发布者已接入，AkShare 仅保留为示例方向 | ✅ |
| P1 | `ExecutionClock` + Paper 集合竞价下单（竞价价×(1+ε)）+ 策略按日去重 | ✅ |
| P2 | 回测 `fill_timing="auction_close"`（14:57 决策、收盘/竞价价成交） | ✅ |
| P2 | 指数基准 → 超额收益/Beta/Alpha/信息比率（`baseline_returns` 已存在，已接线） | ✅ |
| P2 | `universe_mode="index_pit"`（PIT 成分池，缺失时自动回退市值裁剪） | ✅ |
| P2 | 历史回补 2015-2026（日线 + 指数 + 成分） | ✅ |

### 12.2 实测数据覆盖（Pro）

- 个股日线：`2015-01-05 ~ 2026-10-19`，2863 个交易日，11,837,026 行，5835 只；
  各年行数与旧库 2024 年口径一致（2024=1,293,893）。
- 指数日线：沪深300 / 中证500 / 创业板指 / 上证50，均 `2015-01-05 ~ 2026-10-19`。
- 指数成分（PIT）：沪深300 / 中证500 / 中证1000 / 创业板指 **141 期**
  （2015-01-30 ~ 2026-09-30，逐月）；中证2000 **38 期**（2023-08-31 起）；
  上证50 到 2021-05（Tushare 侧停止更新）。
- 日线分区：`year=YYYY/month=MM`；2024Q1 读取只命中 3/37 个文件。
- 日市值/换手（daily_basic）：2015-2026，约 1175 万行。

### 12.3 回测口径说明

- `fill_timing="auction_close"`：日线回测在 14:57 触发 `on_bar`，策略使用**当日 bar**
  （日线用收盘价近似 14:57 竞价价）；撮合价=当日收盘价，买入限价=收盘×(1+ε)，
  卖出限价=收盘×(1-ε)。这是对"14:57 看竞价价→14:59 下单→15:00 成交"的日线近似，
  存在"14:57 价格 ≈ 收盘价"的轻微乐观偏差，已在文档中声明。
- `fill_timing="next_open"`（旧默认）：9:30 触发，用上一交易日数据决策，开盘价成交。
- `benchmark`（默认 `000300.SH`）：自动读取指数日线计算基准收益；覆盖不足时
  自动降级为无基准指标，不阻塞回测。
- `universe_mode="index_pit"` + `index_pool_codes`：按目标日 PIT 成分选池；
  成分库无覆盖时回退 `market_cap_trim`。

### 12.4 2025H1 实测（Pro，auction_close）

| 配置 | Total | Sharpe | MDD | 超额(年化) | Beta | Alpha |
|---|---|---|---|---|---|---|
| `market_cap_trim`（默认池） | +6.02% | 0.63 | -17.89% | +6.85% | 1.17 | +5.72% |
| `index_pit`（300+500） | +3.31% | 0.42 | -18.48% | +0.63% | 1.01 | +0.55% |
| `next_open`（旧口径） | +0.48% | 0.17 | -18.00% | -5.65% | 1.12 | -6.46% |

注：三者信号与成交口径不同，仅用于验证链路，不构成参数优劣结论。

---

## 13. 多数据源与 30 分钟数据（实现）

### 13.1 按数据集划分“主源”，而不是单一主备

没有任何一个数据源能覆盖全部需求，因此按**数据集**确定来源：

| 数据集 | 主源 | 补充/兜底 | 落盘 |
|---|---|---|---|
| 个股日线、复权因子、涨跌停、ST | Tushare | 腾讯（日线兜底） | 是 |
| 指数日线 | Tushare | 腾讯 | 是 |
| 指数成分 PIT | Tushare | — | 是 |
| 30 分钟历史（上一已收盘交易日及更早） | BaoStock（2020-01-02 起） | — | 是 |
| 当日 30 分钟 | 实时快照每分钟采样，内存合成 | — | 否 |
| 实时快照 / 当日涨跌停 | `MarketDataHub`（唯一实时 ingress）；当前官方发布者为腾讯（`qt.gtimg.cn`，约 800 支/批，全市场 7 批） | 用户自建发布者（同样只能发布到 Hub） | 否 |
| 盘中 forming 30 分钟 / forming 日线 | 由实时快照在内存合成 | — | 否 |

结论：**Tushare 仍是日线与辅助字段的主源；30 分钟历史只信 BaoStock，
当日 30 分钟由 `MarketDataHub` 的实时快照合成**。腾讯 K 线不参与 30 分钟历史/增量，避免
“历史 30 分钟 + 实时快照”同时压腾讯接口触发风控。

### 13.2 代码落点

- `quantide/data/fetchers/tencent.py`：腾讯适配器
  - `fetch_quote_snapshot(symbols)`：实时快照（价格/开高低/量额/**当日涨跌停**）；
  - `fetch_minute_bars(asset, period="30")`：近期 30 分钟 K 线（备用，
    返回口径已统一为 bar 收盘时刻）；
  - `fetch_index_bars`：指数日线兜底；
  - 其余日线批量/复权/ST/成分返回空并记录错误，交由聚合器回落。
- `quantide/data/fetchers/multi.py`：`MultiSourceDataFetcher`
  - 按 `DEFAULT_STAGES` 为每类数据配置 fetcher 优先级；
  - 30 分钟默认只配置 `baostock`，首选异常/空数据不会降级到腾讯。
- `quantide/service/minute_bar_aggregator.py`：当日 30 分钟内存合成器
  （每 60 秒采样、按收盘时刻分桶、收盘后由同步任务清理）。
- `quantide/providers/tencent_publisher.py`：把腾讯快照发布到
  `quotes.all` 与 `stock_limit`，Paper 直接消费；顺带解决“当日涨跌停”
  在盘中不可用的问题（此前只能拿到昨日涨跌停）。

### 13.3 实时延迟与请求量

腾讯实时接口单批约 800 支，全市场约 7 批；单批往返通常 0.2~0.5 秒，
串行一轮约 2~4 秒，满足模拟盘 <5 秒要求。默认 3 秒轮询。

腾讯 **K 线接口是逐股请求**（`param=sh600519,m30,...`），全市场每天约
5000 次 HTTP 请求；这也是不再用腾讯补 30 分钟历史/增量的原因。BaoStock
同样逐股，但每日预算 4.5 万次，且只在“缺历史”时请求。

### 13.4 30 分钟数据的初始化与日常更新

1. **回补范围**：每只标的从 `max(2020-01-02, 本地最后日期+1)` 到
   **最后一个已收盘交易日**；BaoStock 30 分钟线自 2020-01-02 起可用，
   更早的请求会被自动截断并记录日志；
2. **初始化在盘中**：历史只补到上一交易日；当日从进程启动时刻开始采样，
   启动前的桶无法恢复（这是“历史只信 BaoStock”的代价）；
3. **初始化在盘后**：若当日 17:30 之后，BaoStock 已更新当日数据，则
   历史补到当日；否则补到上一交易日，当日数据继续留在内存；
4. **关机 5 天后启动**：BaoStock 一次补齐这 5 个交易日的缺失区间，
   不需要腾讯 5 天前的分钟线；当日仍由实时采样合成；
5. **入库后清理**：同步任务把 BaoStock 数据写入存储后，调用
   `MinuteBarAggregator.clear_between()` 丢弃对应日期的内存合成数据，
   保证历史 30 分钟始终只有一个来源（BaoStock）。

### 13.5 30 分钟线的存储与读取口径

- **存储** `quantide/data/stores/minute_bars.py`：只存原始
  `date, asset, open, high, low, close, volume, amount`；
  - `date` 统一为 **bar 收盘时刻**（与 `Calendar.ticks` 一致：10:00 表示
    09:30-10:00；每日 8 根：10:00/10:30/11:00/11:30/13:30/14:00/14:30/15:00）；
  - 成交量单位 **手**、成交额单位 **千元**（与 Tushare 日线一致）；
  - 按年分区，主键 `(date, asset)`，重复写入保留最新；
  - 每个分区存储使用独立日期索引 `<store>-dates.pq`，避免与日线共用。
- **写入口径统一**：
  - BaoStock 返回的时间已经是 bar 收盘时刻，直接保留；
  - BaoStock 成交量单位是**股**、成交额是**元** → 转换为手/千元；
  - 腾讯 K 线原始为起点口径，需要时加一个周期转换为收盘时刻。
- **读取** `quantide/data/models/minute_bars.py`：
  - 关联当日 `daily_bars` 的 `adjust / is_st / up_limit / down_limit`；
  - `qfq` 时按同一比例调整 OHLC、**以及涨跌停价**（保证限价与复权后的 close 可比），
    成交量反向调整；`hfq` 同理；
  - 日线辅助字段缺失时按未复权 + 无涨跌停处理并告警；
  - 时间截断按 `end_dt` 精确到分钟（不再只按日期）。
- **Broker 入口**：`get_history(..., frame_type=FrameType.MIN30)`（也兼容
  `"30m"`/`"m30"`/`"30"`），回测走 `HistBarView`（仅完成 bar），实盘走
  `LiveBarView`（BaoStock 历史 + 内存完成桶 + 当前 forming 桶）。

### 13.6 盘中 30 分钟线的内存合成

`MinuteBarAggregator` 每 60 秒采样一次实时快照，只对策略实际读取过的标的
（`subscribe`）合成：

- 分桶使用 `Calendar.ceiling(now, FrameType.MIN30)`，桶索引为**收盘时刻**；
- `open` = 桶内第一个采样价；`high/low/close` = 桶内累计最高/最低/最新价；
- `volume/amount` = 快照当日累计值 − 桶开始时的累计值；当日第一桶从 0 起算；
- 已收盘的桶进入“完成桶”，`forming` 只保留当前桶；
- 午休、非交易日不采样；15:00 后不再产生新桶，读取时自动完成最后一根；
- 数据只在内存，BaoStock 入库后由同步任务清理。

已知限制：盘中启动时，启动前已经走完的桶无法恢复；此时第一个桶的成交量
从启动时刻开始累计。回测永远只使用落盘的 BaoStock 完成 bar。

### 13.7 除权日盘中的复权对齐

盘中 30 分钟历史（qfq，基准为昨日因子）与当日内存合成行（原始价）在除权日
会出现基准不一致。处理方式：

- 交易所当天的 `prev_close`（昨收）已经是**除权除息后的参考价**，因此
  `ratio = prev_close / 上一交易日原始收盘` 就是“今日因子 / 昨日因子”；
- 仅当历史止于昨日时，把历史价格（OHLC/涨跌停价）乘以 `ratio`、成交量除以
  `ratio`，今日原始行与订阅中心推送的当日涨跌停保持不变；
- 非除权日 `ratio == 1`；发布者未提供 `prev_close` 时退回原行为；
- 若存储已包含今日数据（盘后同步完成，qfq 基准已是今日真实因子），则**跳过**
  该换算，避免重复缩放；
- 精度受昨收两位小数限制（误差 ≤ 0.005/昨收），收盘后 Tushare 真实因子落盘
  后自动替代近似值。

日线 live 路径目前全程返回原始价（raw + raw），不存在 qfq 与原始价拼接的
边界问题；若后续把日线路径切回 qfq，可直接复用 `_rebase_history_to_today`。

另外，分钟线读取时若最新一天缺少日线辅助字段（例如分钟库比日线多一天），
`adjust` 会按标的前向/后向填充，而不是填 1.0，避免 qfq 基准被错置。

## 14. 当日涨跌停、复权与 ST 的双链路（实盘/模拟）

### 14.1 当日涨跌停

Tushare 每个交易日早晨发布当日 `stk_limit`。运行时由
`quantide/service/limit_price_refresher.py` 负责：

- 启动时立即刷新一次；
- 09:00 刷新；若未拿到数据，09:20 再补拉一次（只补一次，非交易日跳过）；
- 写入 `LimitPriceStore`（`~/.quantide/data/limit_price`，年+月分区），
  同时广播 `stock_limit`（含 `up/down` 与 `up_limit/down_limit` 两套键名）。

读取优先级（Paper 撮合与 30 分钟线读取一致）：

1. 行情发布者实时推送到 `MarketDataHub`（腾讯快照自带当日限价）；
2. `LimitPriceStore`（Tushare 早晨落盘，重启/发布者缺失时仍可用）；
3. 本地日线（上一交易日兜底）。

这是**限价数据集内部的显式读取优先级**，不是跨数据集的全局 fallback，也不是
已实现的自动 source switching：当前实现没有对两份数据做完整候选验证、重叠比对或
原子 promotion。缺失或冲突时，Paper 应按 §15 fail-closed，而不是猜测哪一份正确。

### 14.2 撮合规则（2026-10 修订）

- **实盘**：不对涨跌停做限制，由真实市场决定是否成交；
- **Paper**：涨停价不买入、跌停价不卖出——在**下单阶段直接拒绝**（`LimitPrice`），
  不允许挂单等待；委托价超出 `[down_limit, up_limit]` 仍抛 `PriceOutOfLimit`；
  撮合按实时价格与成交量进行真实匹配；
- **回测（日线）**：涨停不买、跌停不卖；缺少涨跌停数据（`up_limit <= 0` 或
  `down_limit <= 0`）时**拒绝成交并告警**（新股上市前 5 日等本身无涨跌幅限制的
  标的也会被拒）；
- **回测（30 分钟线）**：只要该 bar **没有完全封死**在涨停/跌停，就允许成交，
  并按涨停价/跌停价成交：
  - 买入：`low < up_limit` 即可（bar 内曾出现低于涨停价的价格）；
  - 卖出：`high > down_limit` 即可；
  - 若整段 bar 的 `low >= up_limit`（封死涨停）或 `high <= down_limit`
    （封死跌停），则不成交。
### 14.3 复权因子与 ST

- **复权因子**：Tushare `adj_factor` 落盘为主；盘中除权日由发布者 `prev_close`
  推导今日基准（`prev_close / 上一交易日原始收盘`），用于把 qfq 历史换算到今日基准；
- **ST**：Tushare `st_info` / 日线 `is_st` 为主；发布者快照的 `name` 含 `ST` 时
  作为备份（`MarketDataHub.is_st()`），用于当日内存合成行。

用户自建行情发布者只需在快照中额外提供 `prev_close`、`name`、`up_limit`、
`down_limit`，即可获得与官方腾讯发布者相同的双链路能力。

### 14.4 内置腾讯发布者（可选，默认关闭）

公开版默认不自动拉取实时行情，用户可自行接入发布者。若希望开箱即用，
可设置环境变量后重启服务，由服务进程内启动腾讯发布者：

```bash
export QUANTIDE_QUOTE_PUBLISHER=tencent
export QUANTIDE_QUOTE_SYMBOLS=600519.SH,000001.SZ   # 可选，缺省为全市场
export QUANTIDE_QUOTE_INTERVAL=3                    # 秒
```

注意：`msg_hub` 是进程内消息总线，因此发布者必须运行在**服务进程内**；
单独执行 `python -m quantide.providers.tencent_publisher` 不会把行情送给
正在运行的服务。定时任务使用 `misfire_grace_time=None`，机器休眠后唤醒
仍会补跑 09:00/09:20 的当日限价刷新。

---

## 15. 只读审计：可替换数据源的可靠架构（目标）

本节是对前面实现说明的收束。它规定“换源”必须怎样被证明，而不是把当前的
`MultiSourceDataFetcher` 顺序尝试描述成已经完成的可靠切换系统。

### 15.1 数据集/frame 能力矩阵

能力必须精确到数据集和周期（frame），不能只登记一个笼统的“provider 可用”。
下表是当前适配器实际能够承担的角色：

| 数据集 | frame / 时间语义 | 当前权威来源或入口 | 可替换候选与硬限制 |
|---|---|---|---|
| 个股行情 | `1d`，已收盘交易日 | **Tushare**：`daily`，并配合 `adj_factor`、`daily_basic`、`st_info`、`stk_limit` | 腾讯只能作为有限的日线补充，不能提供完整日期批量、复权因子、ST 或 PIT 语义；不能因为腾讯返回一行就替换整段日线。 |
| 指数行情 | `1d`，已收盘交易日 | **Tushare**：`index_daily` | 腾讯可作为指数日线补充；仍需单独检查代码、覆盖区间和 OHLC/成交量单位。 |
| 指数成分 | PIT 月度快照，`trade_date <= as_of` | **Tushare**：`index_weight` | 当前没有 BaoStock/腾讯候选。区间查询有 7000 行限制，必须逐快照期请求；无快照不能用当前成分替代。 |
| 日线辅助字段 | `daily_basic`、复权因子、ST、涨跌停 | **Tushare** 落盘；实时涨跌停可由 Hub 的发布者补充 | 腾讯快照的涨跌停只覆盖其返回的标的和当前交易日；名称含 `ST` 只能是备份信号，不能替代历史 ST 记录或复权因子。 |
| 历史分钟线 | 已完成 `30m` bar，bar 时间为收盘时刻 | **BaoStock**，自 2020-01-02 起的项目支持范围 | 单 socket 串行，不能并发；每日硬上限约 5 万请求，适配器默认 45,000 并会在限频/黑名单时冻结。成交量原为股、成交额原为元，必须转换为手/千元；它不是实时源。 |
| 当日已完成/进行中分钟线 | `30m`，当天由采样形成 | **MarketDataHub** 快照经 `MinuteBarAggregator` 在内存合成 | 启动前已结束的桶无法恢复；盘后由 BaoStock 历史落盘并清理内存合成。腾讯 K 线近期接口是逐股请求，不作为全市场历史回补。 |
| 实时快照 | tick / 当前 `QuoteSnapshot`，含 `ts` | **MarketDataHub 是唯一实时 ingress**；当前 TencentPublisher 是一个发布者 | Hub 不是外部 provider，也不负责跨源切换；腾讯约 800 支/批、全市场约 7 批，受 HTTP 可用性和字段口径影响。 |
| 当日 forming 日线 | `1d` forming，内存 | MarketDataHub 快照 | 不等同于 Tushare 已收盘日线；必须标注 forming 状态和实时来源，不能写入已收盘历史分区冒充正式 bar。 |

### 15.2 四个组件的实际角色

**Tushare** 是有 token 和接口限频约束的历史/参考数据主源，覆盖交易日历、证券列表、
个股日线、复权因子、市值/换手、ST、涨跌停、指数日线和 PIT 成分。`stk_mins` 的分钟
接口约每分钟一次，全市场历史分钟线不适合发行版核心；Tushare 也不是实时行情 ingress。
`index_weight` 的 7000 行限制是接口行为，不能通过长区间或简单分页假设消失。

**BaoStock** 在本项目中只承担已收盘历史分钟线，重点是 30 分钟。它的连接和预算约束
决定了抓取必须串行、可断点、可恢复；它不负责个股日线的辅助字段、PIT 成分或实时快照。

**Tencent** 通过 `qt.gtimg.cn` 提供批量实时快照（含价格、当日高低、成交量/额、时间和
通常可用的涨跌停），并能提供近期 K 线和指数日线。它没有项目所需的完整复权、ST、PIT
成分和日期批量日线能力；K 线逐股请求，分钟历史不应与实时轮询混用。其成交量口径还
存在普通股票/科创板差异，成交额部分由源字段或估算得到，必须在候选验证时显式声明单位。

**MarketDataHub** 是规范化实时消息入口、快照缓存和事件流，不是第三方 provider，也不
是历史数据 fallback。发布者（腾讯、AkShare 或用户自建 HTTP/WS/SDK）只负责取得并发布
快照；Paper、风控、UI 和 forming bar 只能从 Hub 读取。旧 `LiveQuote` 的 websocket、
独立缓存和发布逻辑已经退役，`quantide.service.livequote` 只保留兼容名称指向 Hub。

### 15.3 当前没有自动切换

当前 `MultiSourceDataFetcher` 的 `DEFAULT_STAGES` 确实列出少数顺序，例如日线
`[tushare, tencent]`、指数日线 `[tushare, tencent]`；它在调用层遇到异常或空结果时
尝试下一个 fetcher。这是**窄范围的 best-effort 取数 fallback**，不是可靠的自动切换，
因为它目前没有同时证明：

1. 返回结果的 schema、覆盖、OHLC、单位、时间戳和整体质量合格；
2. 新旧来源在重叠区间的一致性达到该数据集容差；
3. 数据来源、规范化版本和 source epoch 已被记录；
4. 写入对读者是原子可见的，且失败时旧快照仍然可读。

因此当前运行语义是：**没有可依赖的自动 source switching，也没有跨数据集的全局
fallback**。尤其不能因为 Tushare 失败就把所有数据都切到腾讯，也不能因为实时发布者
短暂无数据就从历史 store 猜造实时价格。候选选择、提升和实时发布者更换都必须遵守
下面的工作流和运行模式策略。

### 15.4 推荐的候选提升工作流

一个数据集的替换必须由同一个 `DataSyncService` 编排器执行，且对当前已发布快照保持
只读。推荐顺序如下：

1. **按能力选择候选**：按精确的 `dataset + frame + asset universe + date range`
   查询能力记录；不匹配的 provider 不得因为“能返回数据”而进入候选。
2. **抓取到 staging**：候选写入临时对象/临时分区，带请求参数和原始响应摘要；在所有
   检查完成前，生产 store 和读者不可见。
3. **schema 验证**：检查必需列、类型、主键、代码格式、日期/时间类型、调整字段和
   可选字段的约定；拒绝静默改名或缺列填零。
4. **coverage 验证**：根据交易日历、目标标的集合和目标区间检查缺日、缺标的、提前
   结束、重复分区以及 frame 是否完整；允许的缺口必须是数据集策略明确声明的缺口。
5. **OHLC 验证**：检查 `low <= open/high/close <= high`、正价、成交量/成交额非负，
   并检查涨跌停、复权和 forming/已收盘状态没有混用。
6. **单位验证**：明确成交量是股还是手、成交额是元、千元还是万元，价格是否已复权；
   转换后用抽样和数量级规则复核，未知单位直接失败。
7. **时间戳验证**：检查时区、交易时段、bar 是起点还是收盘时刻、单调性、未来时间和
   分钟桶对齐；`30m` 必须继续遵守项目的收盘时刻语义。
8. **质量验证**：检查空值、重复主键、异常跳变、停牌/零量解释、跨分区连续性和源
   freshness，并生成可审计的 validation report，而不是只返回“非空”。
9. **重叠比较**：将候选与当前已提升版本在重叠的 key/date/frame 上比较，记录覆盖率、
   OHLC/量额差异、允许容差、差异样本和结论。没有重叠时必须由数据集策略明确批准，
   不能把“无从比较”当作“比较通过”。
10. **写 provenance 和 source epoch**：候选通过后，为该数据集/范围生成来源记录和
    新 epoch；epoch 在 provider、原始版本、单位/时区/规范化语义改变时递增。
11. **原子提升**：先完成不可变候选分区和 manifest，再以一次 manifest/version swap
    将候选设为 active。任何验证、比对或写入失败都只删除/保留 staging，读者继续看
    旧 active snapshot。

### 15.5 数据集级策略，不是全局 fallback

替换边界是一个数据集及其 frame，而不是一个进程级的“主源/备用源”开关。例如：

- Tushare 日线失败时，只有在**日线候选**完成上述验证并被提升后，才可以改变日线
  manifest；这不会改变 30 分钟、PIT 成分或实时快照的来源。
- BaoStock 触发限频时，历史 30 分钟任务应暂停/失败并保留旧快照，不得把腾讯实时
  K 线拼成未经验证的历史 30 分钟。
- TencentPublisher 无快照时，MarketDataHub 应报告 stale/missing；不得由 Hub
  自动启动另一个 provider，也不得把上一收盘价伪装成实时价。
- 当日涨跌停是一个独立数据集，Hub 的发布值与 `LimitPriceStore` 的 Tushare 值可以
  按该数据集的显式优先级读取，但冲突须记录，不能触发全局源切换。

### 15.6 能力、健康和 provenance 数据结构

下面是目标数据结构的最小形状。它们是数据集 manifest/审计记录的契约，不要求本次
引入一个面向所有 provider 的大而全注册中心。

```python
@dataclass(frozen=True)
class ProviderCapability:
    provider_id: str                 # tushare / baostock / tencent / hub-publisher
    dataset: str                     # daily_bars / minute_bars / quote_snapshot ...
    frame: str                       # 1d / 30m / tick / pit_monthly
    supported_from: date | None
    supported_to: date | None
    universe: str                    # all_a / configured_assets / index_codes
    fields: tuple[str, ...]
    units: dict[str, str]            # volume=share|lot, amount=cny|thousand_cny
    timestamp_semantics: str         # session_date / bar_close / exchange_ts
    adjustment: str                  # raw / qfq / hfq / none
    max_batch: int | None
    rate_limit: str | None
    realtime_ingress: bool

@dataclass
class ProviderHealth:
    provider_id: str
    dataset: str
    frame: str
    checked_at: datetime
    state: str                       # healthy / degraded / blocked / unknown
    latency_ms: float | None
    freshness_at: datetime | None
    consecutive_failures: int
    remaining_budget: int | None
    last_error: str | None

@dataclass(frozen=True)
class DataProvenance:
    dataset: str
    frame: str
    range_start: date | datetime
    range_end: date | datetime
    provider_id: str
    source_epoch: str                # immutable epoch for this source/normalization
    request_fingerprint: str
    retrieved_at: datetime
    normalization_version: str
    validation_report_id: str
    overlap_report_id: str | None
    content_hash: str
    promoted_at: datetime | None
```

`ProviderCapability`回答“能不能覆盖这个请求”，`ProviderHealth`回答“现在是否值得
尝试”，`DataProvenance`回答“已发布的数据究竟来自哪里、何时、按什么口径生成”。
三者不能互相替代：健康状态不能证明 schema 正确，能力声明不能证明本次覆盖完整，
provenance 也不能掩盖验证失败。

### 15.7 Paper/live 的 fail-closed 规则

历史回测可以由调用方显式选择数据范围和容忍策略；**Paper 和 live 必须 fail-closed**：

- 没有 active 且通过验证的快照、快照超过 freshness 上限、时间戳无效或单位未知时，
  不产生交易信号/委托；
- OHLC、覆盖、质量或重叠检查失败时，不把候选数据暴露给撮合或策略；
- `MarketDataHub` 没有新鲜快照时，Paper 停止形成实时 bar，并报告 stale，而不是用
  旧值静默继续；
- source epoch、provenance 或 manifest 不完整时，拒绝把数据标记为 active；
- **live 模式的来源提升或来源切换必须有操作员明确批准**，包括候选、验证摘要、重叠
  差异和回退版本；不能由定时任务或网络错误自动切换。当前发行版仍只允许 backtest
  和 paper，以上 live 规则是未来 live 能力的安全边界。

### 15.8 本次范围边界

本次只记录审计结论和推荐契约：不实现广义 provider registry，不改 fetcher、store、
同步器或运行模式，不提交、不部署。后续实现应先在 `DataSyncService` 内落地一个数据集
的 staging/validation/manifest 闭环，再逐个扩展能力矩阵；在此之前，文档中的“目标”
不能被宣传为已经具备自动切换或零停机替换能力。
