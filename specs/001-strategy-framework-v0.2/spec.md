# Millionaire 策略框架与运行模式 — Spec

- **Spec ID**: 001-strategy-framework-v0.2
- **创建日期**: 2026-06-15
- **状态**: 草稿（基于 story 351 行原文重写，待 Aaron IDE review）

## 用户故事

### US-010
story: 作为独立量化开发者，我想通过 SDK 编写策略，且让同一份代码在回测/仿真/实盘/dry-run 四种模式无修改运行
priority: P0

### US-020
story: 作为用户，我希望框架自动扫描指定目录，列出所有策略（含名称、描述、参数）
priority: P0

### US-030
story: 作为用户，我希望选择三种下单方式（cheat-on-close / 次日开盘 / 次日限价）之一
priority: P0

### US-040
story: 作为用户，我希望使用三种内置策略：双均线（日线）、回落卖出（风控）、成本止损（风控）
priority: P0

### US-050
story: 作为用户，我编写实时策略（如 30 分钟隔夜策略）时，框架通过 on_day_open / on_bar 驱动，且不可回测
priority: P0

### US-060
story: 作为用户，我希望风控策略跟随宿主策略生命周期自动激活，且不占独立账户
priority: P0

### US-070
story: 作为用户，我使用回测参数启动策略后，转仿真/实盘时参数自动带入
priority: P0

### US-080
story: 作为用户，我可以为每次运行单独设置运行时参数（本金/滑点/手续费），不被回测结果锁定
priority: P0

### US-090
story: 作为用户，我希望在 dry-run 暂停实盘时，并行仿真继续跑，便于我决定何时重启
priority: P1

### US-100
story: 作为用户，我使用 tushare + qmt-gateway 两种数据源，前者用于历史与参考数据、后者用于实时
priority: P0

### US-110
story: 作为用户，我通过 Web UI 的策略选择器查看任一运行中策略的账户/委托/成交
priority: P0

### US-120
story: 作为用户，我在策略/委托/成交事件发生时收到微信通知
priority: P0

## 用户使用场景

### scenario-010 双均线 cheat-on-close 回测

选择双均线策略 + cheat-on-close 下单 + fast=5 / slow=20 + 回测起止 + 运行时本金。系统每日计算 MA5/MA20，cross-over 时发出买卖信号，T+0 收盘价成交。回测实时显示进度与净值曲线（按 on_bar 推进），结束后输出完整报告（指标 + 4 类图表）。

### scenario-020 实时策略上实盘

编写 `OvernightStrategy(Strategy)`，在仿真界面运行 1 周 → 切到实盘 → 系统当日停止原仿真 → 自动创建并行仿真 → 策略在实盘正常发单。期间如需暂停，点 "dry-run"，策略继续运行不实际下单，可观察并行仿真曲线。

### scenario-030 风控策略叠加

独立策略"双均线"进入实盘时，其绑定的"成本止损"风控策略自动激活。持仓跌破买入价 5% 时风控策略发卖出单，成交归属宿主策略的虚拟账本，不影响宿主收益计算，但贡献一条超额收益记录（基于卖出价至当日收盘的反向收益率）。

## 功能需求

> **编号约定**: FR 采用 3 位零填充，10-step 递增（FR-010/020/...），便于中间插入新需求。FR 与 story §x.y 一一对应。NFR 同。

### FR-010 策略作为 SDK 暴露（v0.2 仅声明接口，v0.3 实现 AI Agent skill）

公开 `BaseStrategy` 基类与统一生命周期 API。v0.2 提供 Python SDK；AI Coding Agent skill（基于 skill 暴露数据/交易接口、生成策略模板）推迟至 v0.3。

#### 生命周期钩子

| 钩子 | 调用时机 | 参数 | async |
|---|---|---|---|
| `init()` | 实例化后立即调用 | 无 | ✅ |
| `on_start()` | 运行开始前 | 无 | ✅ |
| `on_stop()` | 运行结束后 | 无 | ✅ |
| `on_day_open(tm)` | 每日开盘前 | `tm: datetime` | ✅ |
| `on_day_close(tm)` | 每日收盘后 | `tm: datetime` | ✅ |
| `on_bar(tm, quote, frame_type)` | 每个周期驱动 | `tm: datetime`, `quote: dict`, `frame_type: FrameType` | ✅ |

所有钩子默认实现为空操作（`pass`），子类可覆盖任意子集。

#### 交易接口

| 方法 | 语义 |
|---|---|
| `buy(asset, shares, price=0)` | 按股数买入，市价当 price=0 |
| `buy_percent(asset, percent)` | 按现金比例买入（0~1） |
| `buy_amount(asset, amount)` | 按金额买入 |
| `sell(asset, shares, price=0)` | 按股数卖出 |
| `sell_percent(asset, percent)` | 按持仓比例卖出 |
| `sell_amount(asset, amount)` | 按金额卖出 |
| `cancel_order(qt_oid)` | 取消指定订单 |
| `cancel_all_orders(side=None)` | 取消所有未成交订单，可按方向过滤 |
| `trade_target_pct(asset, target_pct)` | 调仓至总市值占比 |

所有买卖方法返回 `TradeResult`（含 `qt_oid` 订单 ID 和 `trades` 成交记录列表）。

#### 查询接口

| 属性 | 类型 | 语义 |
|---|---|---|
| `positions` | `dict[str, Position]` | 标的代码 → 持仓对象 |
| `cash` | `float` | 当前可用资金 |

#### 数据接口

`get_bars(asset, count, end_dt=None, frame_type="1d", include_forming_bar=True)` → `pl.DataFrame`

- `end_dt` 默认为当前运行时间
- `include_forming_bar=True` 时返回含当日 forming bar
- `include_forming_bar=False` 时只返回昨日及更早数据

#### 辅助接口

| 方法 | 语义 |
|---|---|
| `default_config()` → `dict[str, Any]` | `@staticmethod`，声明策略参数名与默认值，默认返回 `{}` |
| `log(msg, level, tm)` | 输出日志，时间戳默认为仿真时间 |
| `record(key, value, dt)` | 记录策略指标/信号，`dt` 默认为仿真时间 |

#### 约束

策略代码中无任何 API 可获取当前运行模式（回测/仿真/实盘/dry-run）。基类不暴露 `get_mode()` 或等价方法。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-020 自动发现策略

扫描用户配置目录（默认 `~/.millionaire/strategies/`，可配置）中的策略类，读取 `default_config()` 类方法返回的 dict（key=参数名, value=默认值）获得参数列表，UI 展示。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-030 策略参数跨模式透传

回测启动时设置的策略参数在转仿真/实盘/dry-run 时**自动带入**，不再单独设置。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-040 一次开发四模式无感迁移（且策略不可知运行模式）

同一份策略代码，不修改即可在回测/仿真/实盘/dry-run 四种模式运行。**策略代码不可感知运行模式**（见 §12 限制声明）。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-050 下单方式 — cheat-on-close

- 回测：T+0 收盘价信号，T+0 收盘价撮合
- paper/live：T+0 尾盘信号，在尾盘集合竞价（用户可配置时间点，默认 14:57）执行；触发即发单等撮合

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-060 下单方式 — 次日开盘（正常模式）

- 回测：T+0 收盘价信号，T+1 开盘价成交（开盘即涨跌停则不撮合）
- paper/live：盘后运行；T+1 开盘集合竞价发单（卖单跌停价、买单涨停价）

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-070 下单方式 — 次日限价

- 回测：T+0 收盘价信号，若指定价落在 T+1 bar [low, high] 则全部成交
- paper/live：盘后运行；T+1 开盘集合竞价发单，由撮合系统处理

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-080 跨模式回测-实盘差异（声明为预期）

三种下单方式下，回测/仿真/实盘**运行结果差异是允许的**。差异来源详见 story §1.5 末尾说明。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-090 内置策略 — 双均线（日线策略）

日线策略。计算 [fast, slow] 周期均线，fast 上穿 slow → 买入；slow 上穿 fast → 卖出。参数 `[fast, slow]`，默认 `[5, 20]`。回测结果图形化展示：净值、参考线、买入点、卖出点、MA 指标。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-100 内置策略 — 回落卖出（风控）

个股当天上涨至 m% 后，若 n 分钟内下跌超过 k%，立即卖出。参数 `[m, n, k]`，默认 `[5.0, 30, 2.0]`。需 tick 级数据。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-110 内置策略 — 成本止损（风控）

持仓个股跌破买入价 k% 时立即卖出。参数 `[k]`，默认 `[-5.0]`。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-120 实时策略驱动契约

- 仅支持 paper/live，不支持回测
- 通过 `on_day_open` 与 `on_bar` 驱动
- `on_bar` 对应 30m/1d 等框架定义周期
- 30m 等非原始数据由框架基于实时行情聚合后提供
- 不直接访问 qmt-gateway 原始接口，仅通过框架 API
- tick 级驱动不在本 spec 范围（需后续 spec 明确）

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-130 风控策略契约

- 无独立资金账户，监控其它策略的持仓
- 只统计超额收益（定义见 story §1.8），不统计其他指标
- 不可回测、不可独立仿真
- 可随时停止
- 操作他人持仓时不改变持仓归属、不改变原策略的收益计算
- 自动叠加：宿主独立策略进入 paper/live 时其关联风控策略自动激活（见 FR-230/240/250）

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-140 交易规则 — 价格（涨跌停）

- 以数据 `up_limit` / `down_limit` 字段为准（普通 ±10%、ST ±5%、创/科 ±20% 由数据源提供，框架不内置规则）
- 限价单指定价必须落在 `[down_limit, up_limit]` 内，否则下单直接拒绝
- 开盘即涨停的标的买入单不撮合；开盘即跌停的标的卖出单不撮合
- `is_st=true` 股票不做下单限制（策略自行过滤）

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-150 交易规则 — 数量

- 买入数量必须是 100 整倍数；下单前自动向下取整（不足 100 部分丢弃）；取整后为 0 则下单失败
- 卖出一般须 100 整倍数；**清仓（卖出全部可用持仓）与零股（不足一手的零散股）允许例外**
- 仿真/实盘实际成交数量受涨跌停/停牌/成交量约束，可能少于委托
- 回测中订单要么全成交，要么作废（不考虑成交量）

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-160 交易规则 — 时间

- **T+1**：当日买入的持仓当日不可卖；次日起方可卖。框架按"可卖持仓"与"在途持仓"分别记账
- 非交易时段（含午休、周末、节假日）生成的信号，订单顺延至下一交易时点（具体行为由 FR-050/060/070 决定）

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-170 交易规则 — 特殊状态（停牌）

停牌股票（数据缺失或 `volume=0`）不可下单；持仓中的停牌股票按停牌前最后收盘价估值。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-180 交易规则 — 资金

- 卖出回款当日可用于继续买入（A 股现金账户规则）
- 印花税（卖方收取，按比率）、佣金（按比率，不低于单笔最低佣金）按 FR-200 配置扣除，扣减发生在成交后立即结算
- 资金校验在虚拟账户层进行：买入下单时检查虚拟账户可用资金是否足以覆盖（成交金额 + 佣金）

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-190 交易规则 — 回测 vs 实盘的差异

回测时上述规则由框架仿真全部实施；仿真/实盘时，时间/价格/数量规则由交易所/柜台强制保证，框架只在下单前做预校验以避免明显错误委托被发出。撮合差异见 FR-080。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-200 运行时参数（框架管理，策略不可见）

每次启动回测/仿真/实盘时，用户需指定：
- **本金**：实盘/仿真时作为虚拟账户资金上限；回测时为初始资金
- **滑点**：比率，作用于撮合价格
- **手续费**：印花税比率（卖方收取）+ 佣金比率 + 单笔最低佣金（绝对值）

由框架统一管理，**策略代码不可见**。切换运行模式时允许重设，不被回测结果锁定。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-210 虚拟账本（按 qtoid 归因）

每个独立策略在 live/paper 中运行时拥有一个虚拟账户，配置独立本金作为资金上限。所有虚拟账户共享真实账户的总资金（用户自行保证各策略本金之和 ≤ 真实账户可用资金；Millionaire 不做跨虚拟账户资金分配校验）。Millionaire 为每个独立策略维护按 `qtoid` 归因的虚拟账本，用于策略级资产/持仓/委托/成交/收益评估/dry-run/并行仿真。除非特别说明，系统中的"策略账户"均指这套虚拟账本，而非柜台原始总账户。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-220 手工交易/补单/风控卖出的归属

手工交易、补单和风控卖出都必须归属到某个独立策略账户，并写入该策略的虚拟账本。柜台原始账户信息主要用于总览和排障，不直接替代策略级归因结果。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-230 日线策略调度路径

- 必须从回测开始，才能进入仿真/实盘（使用该回测的参数）
- 路径 1（顺序）：回测 → 仿真 → 实盘
- 路径 2（直达）：回测 → 实盘
- 策略允许多次回测；每个策略最多保留 **30** 个回测结果
- 进入实盘后，原仿真（若有）当日停止运行，自动创建新的并行仿真

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-240 实时策略调度路径

- 不可回测
- 路径：仿真 → 实盘，或直接实盘
- 进入实盘后，原仿真（若有）当日停止，自动创建并行仿真

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-250 风控策略调度

无独立调度路径。跟随所叠加的独立策略（日线或实时）的生命周期。宿主独立策略进入 paper/live 时，其关联风控策略自动激活。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-260 调度 UI

提供 UI 实现策略调度。启动回测时提供界面改写策略默认参数，运行结果与参数一起保存。在回测、回测转仿真、实盘时都允许单独设置运行时参数（FR-200），不被回测结果锁定。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-270 数据源 — 行情（tushare）

日线（个股、指数）核心历史数据。字段：OHLCV + amount + adjust + is_st + up_limit + down_limit。Parquet 存储，按年分区。数据源：**tushare**。tick/分钟/30 分钟仅 live/paper 模式下使用，不保存。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-280 数据源 — 参考数据（tushare）

- 交易日历（所有交易所）
- 证券列表（全市场代码/名称/拼音/上市退市日期）
- is_st 标记（ST / *ST）

数据源：**tushare**。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-290 数据源 — 复权与涨跌停（tushare）

- adjust（复权因子）用于前/后复权计算
- 涨跌停价：A 股特有，用于撮合判断与限价单比较

数据源：**tushare**。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-300 数据源 — 实时行情（qmt-gateway）

通过外部 `qmt-gateway` 项目获取实时 tick 与分钟线。**仅 live/paper 模式使用**。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-310 数据同步任务

- 定时执行日线行情、证券列表、交易日历、st、涨跌停历史数据同步
- 盘前获取当日涨跌停价格与复权因子
- 定时任务可配置；运行有报告跟踪；错误在 UI 上报告
- 任务错过执行（错误纠正后）可重新执行
- 支持数据补录

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-320 数据完整性校验及报告

后台任务定时执行数据完整性校验（缺日、重复日、字段空值率等），并在 UI 上报告错误。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-330 数据查询支持

- 支持用户查询交易日历
- 支持用户按名字/数字/拼音模糊查询个股基本信息
- 支持用户查询个股历史行情并绘制 K 线图

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-340 评估指标 — 回测（日线策略）

仅日线策略支持回测。指标：
- 年化收益率
- 最大回撤
- Sharpe 比率
- Sortino 比率
- Calma 比率
- 胜率
- 盈亏比
- 交易次数
- 基准对比（如沪深 300，用于判断策略 alpha）

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-350 评估指标 — 实盘/仿真

日线策略与实时策略在实盘/仿真运行时，**使用与 FR-340 相同的指标**进行评估。数据来源为实盘/仿真实际成交记录。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-360 评估指标 — 风控策略

风控策略无独立资金账户，不计算传统收益指标。仅评估：
- **超额收益**（定义见 story §1.8）
- 风控触发次数及触发原因统计

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-370 可视化 — 核心图表

Web 框架 FastHTML，支持响应式可视化。核心图表：
- 资金曲线（含基准对比线）
- 回撤图
- 交易标注（买入/卖出点标记在 K 线上）
- 月度收益热力图

以上适用于日线/实时策略。**风控策略仅展示超额收益曲线**。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-380 可视化 — 回测进度

策略回测时 UI 实时更新进度：
- x 轴为回测区间
- 随 on_bar 推进逐点绘制策略 + 参照标的的净值变化对比图
- 实时更新回测指标（**仅在回测结束时才能计算的除外**）与交易标注

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-390 账户总览（多策略维度）

- 汇总展示所有运行中策略的账户基本信息（总资产/可用现金/持仓市值/账户盈亏）
- 支持按策略筛选，查看单策略账户详情

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-400 委托与成交记录

- 列出三态（回测/paper/live）下的委托记录，支持按策略/个股/时间段查询
- 列出三态下的成交记录，支持按策略/个股/时间段查询

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-410 paper/live 账户

- 每日收益率查询及净值曲线
- 月度收益热力图
- 支持查询最大 N 亏损、最大 M 盈利个股
- 账户基本信息（总资产/可用现金/持仓市值/账户盈亏）

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-420 实盘交易界面

界面顶部提供**策略选择器**，列出当前所有实盘运行的策略（日线 + 实时），用户可切换。

1. 显示所选策略的账户基本信息
2. 显示所选策略的当日委托/成交并实时刷新
3. 提供基础交易界面，允许用户紧急情况下手动交易
4. 手动交易必须归属一个目标策略（虚拟账户）；**风控策略不可作为手动交易目标**

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-430 仿真交易界面

界面顶部提供**策略选择器**，列出当前仿真运行的策略，用户可切换。

1. 显示所选策略的账户基本信息
2. 显示所选策略的当日委托/成交并实时刷新
3. 提供交易界面，供用户**补单**（防止自动化失败的补救措施）

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-440 dry-run 模式

允许正在实盘的策略进入 dry-run：策略正常运行但**不实际下单**。期间交易信号被记录，但策略指标无法计算。dry-run 期间的策略指标**参考其并行仿真实例**。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-450 消息通知（微信）

以下事件发生时发送**微信通知**：
1. 委托和成交
2. 委托和成交失败
3. 实盘交易网关断开

通知在系统设置界面中配置，通过**二维码扫描**启用。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-460 系统配置（init-wizard）

基于图形化系统配置。首次启动时运行 init-wizard（通过 web）引导用户配置关键项：
- 登录密码
- qmt-gateway 连接
- 通知渠道配置
- 数据源
- 数据目录

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-470 安装与运行

- 程序运行在 mac / linux / windows
- mac/linux：基于 shell 安装
- windows：基于图形界面安装
- 自带 embedded python + get-pip；创建虚拟运行环境
- 始终在虚拟运行环境下启动
- 以服务方式运行，并随开机自动启动

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

## 非功能需求

### NFR-010 性能 — 1000 标的日线回测 < 60s

1000 个 A 股日线、5 年区间、纯 Python 实现下，回测端到端（含撮合）耗时 < 60s（CI 标准机）。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### NFR-020 类型完备

所有公共 API 提供类型标注，mypy/pylance 严格模式 0 报错。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### NFR-030 单一职责原则

每个方法 ≤ 50 行、最长 ≤ 120 行（不含 docstring 与注释）。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### NFR-040 不留冗余代码

不保留"以备将来用"的代码；删除一次性 stub。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

## 已知约束与排除项

### 约束

1. 项目使用 `uv` + `venv` 管理依赖；pyproject.toml 中已声明的库优先（不混用，如 `loguru` 与内置 logging 不混用）
2. 项目从未发布过，不考虑旧版本兼容
3. git remote owner (`zillionare`) 与 gh user (`quantclaws`) 不一致——v0.2 显式接受此状态

### 排除项（来自 story §12 限制声明）

1. **Millionaire 仅支持日线行情存储和回测**；实盘中配合 qmt-gateway 获得当日实时行情（1m/30m/1d），但不存储
2. **策略不能感知运行模式**（见 FR-040）
3. **Stop 单作为风控策略实现**，不作为单独订单类型
4. **Market-on-Close 暂不支持**

### 范围外产品

- **Billionaire / Zillionaire** 不在本仓库范围

### 推迟到 v0.3

- **AI Coding Agent skill**（基于 skill 暴露数据/交易接口、生成策略模板）v0.3 实现，v0.2 仅声明接口（FR-010）
- **tick 级驱动**（story §1.7 提及）需后续 spec 明确，v0.2 不实现

## 澄清记录

> **Sage 状态**: 本 spec 为**重写后**初稿（基于 Aaron IDE 审查反馈的 15 项问题），所有 FR/NFR 直接对应 story 351 行原文。**字数、字段名、约束严格忠实于 story**。
>
> 上一版（commit `05f0972`）存在 15 项审查问题（E1-E15），本版已全部修正：
> - E1-E8 缺失项 → 通过 §1.9/§2/§3/§4/§5/§6/§7 全部补齐为 FR-140~440
> - E9 runtime_params → 改为 FR-200，明确"策略代码不可见"
> - E10 评估指标 → 改为 FR-340/350/360，与 story 严格对齐（Sortino/Calma/交易次数/基准对比已加回）
> - E11 运维指标 → 删除（story 未提及）
> - E12 平均响应时间 → 删除
> - E13 闪电单/撤单/改单 → 删除（spec 自行扩展）
> - E14 一键提升至实盘 → 删除（story 无此功能；通过 FR-230/240 调度路径实现）
> - E15 通知渠道 → 改为 FR-450 微信通知 + 二维码
>
> 待用户在 IDE 中 review 后，Sage 将进入 Step 3（基于 git diff 进一步追问）。
