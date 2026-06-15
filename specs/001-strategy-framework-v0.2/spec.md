# Millionaire 策略框架与运行模式 — Spec

- **Spec ID**: 001-strategy-framework-v0.2
- **创建日期**: 2026-06-15
- **状态**: 草稿（待 Aaron IDE review）

## 用户故事

### US-010
story: 作为独立量化开发者，我想把策略一次开发同时跑回测/仿真/实盘/dry-run 四种模式，以便不重复改代码
priority: P0

### US-020
story: 作为策略作者，我希望框架自动发现我编写的策略（连同参数与默认值），以便在 UI 中列出与选择
priority: P0

### US-030
story: 作为用户，我希望通过 SDK + AI Agent skill 编写策略（v0.2 仅声明接口，v0.3 落地 skill）
priority: P2 (v0.2 仅占位，v0.3 实现)

### US-040
story: 作为用户，我希望使用双均线（内置）、回落卖出（内置）、成本止损（内置）三种策略
priority: P0

### US-050
story: 作为用户，我可以选择三种下单方式（cheat-on-close / 次日开盘 / 次日限价）
priority: P0

### US-060
story: 作为用户，我希望策略有独立的资金账户（独立策略），风控策略不占独立账户
priority: P0

### US-070
story: 作为用户，我可以在 dry-run 暂停实盘后通过并行仿真观察策略行为，以便决定何时重启
priority: P1

### US-080
story: 作为用户，我可以在 Web UI 上管理实盘与仿真交易
priority: P0

### US-090
story: 作为用户，我使用 qmt-gateway 与 tushare 两种数据源
priority: P0

## 用户使用场景

### scenario-010 一次开发四模式运行

开发者编写 `MyStrategy(Strategy)` 并提供 `default_config()`。在 Web UI "策略" 页，策略被自动发现。开发者选择模式（回测/仿真/实盘/dry-run）+ 参数 → 启动。同一份策略代码在四种模式下运行；不修改策略代码。

### scenario-020 双均线 cheat-on-close 回测

选择双均线策略 + cheat-on-close 下单 + fast=5 / slow=20 + 回测起止日期。系统每日计算 MA5/MA20，cross-over 时发出买卖信号，T+0 收盘价成交。运行后产生报告（含净值曲线、买入点、卖出点、MA 指标、参考线）。

## 功能需求

### FR-010 策略作为 SDK 暴露（v0.2 占位，v0.3 落地）

公开 `quantide.millionaire.strategy.Strategy` 基类与 `default_config()` 约定。v0.2 仅提供 Python SDK 入口；AI Agent skill 推迟到 v0.3。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-020 自动发现策略

框架扫描用户配置目录（默认 `~/.millionaire/strategies/`），列出所有继承 `Strategy` 的类，读取 `default_config()` 获得参数 key/default，UI 渲染策略选择器与参数表单。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-030 策略参数透传至回测/仿真/实盘

回测启动时设置的参数 dict 在转仿真/实盘/dry-run 时**不需重新设置**，沿用同一组。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-040 一次开发四模式无感迁移

同一份策略代码，不修改即可在回测/仿真/实盘/dry-run 四种模式运行。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-050 下单方式 — cheat-on-close

回测时按 T+0 收盘价成交；仿真/实盘时在尾盘集合竞价（用户可配置时间点，默认 14:57）执行策略，触发即按规则发单。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-060 下单方式 — 次日开盘

回测时按 T+1 开盘价成交（开盘即涨跌停则不撮合）；仿真/实盘时盘后运行，次日开盘集合竞价发单（卖出跌停价、买入涨停价）。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-070 下单方式 — 次日限价

回测时若指定价格落在下一 bar 的 [low, high] 区间则全部成交；仿真/实盘时盘后运行，次日开盘集合竞价发单由撮合系统处理。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-080 内置策略 — 双均线（MA crossover）

日线策略。计算 fast/slow 周期均线，fast 上穿 slow → 买入信号；slow 上穿 fast → 卖出信号。支持参数 `[fast, slow]`，默认 `[5, 20]`。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-090 内置策略 — 回落卖出（风控）

个股当天上涨至 m% 后，若 n 分钟内下跌超过 k%，立即卖出。参数 `[m, n, k]`，默认 `[5.0, 30, 2.0]`。需 tick 级数据。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-100 内置策略 — 成本止损（风控）

持仓个股跌破买入价 k% 时立即卖出。参数 `[k]`，默认 `[-5.0]`。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-110 运行时参数

策略可通过 `runtime_params()` 类方法声明运行时参数（如回测起止、初始资金、订单方向、下单方式）。UI 渲染表单。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-120 风控策略不占独立账户

风控策略监控其它策略的持仓，无独立资金账户，只统计超额收益；不进入回测，不能独立仿真，可随时停止。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-130 实时策略驱动契约

实时策略（不可回测）支持 `on_day_open` 与 `on_bar` 驱动；`on_bar` 对应 30m/1d 等框架定义周期；30m 等非原始数据由框架聚合后提供。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-140 A 股交易规则 — 涨跌停

下单前校验价格在 `[down_limit, up_limit]` 区间；不通过则下单失败。涨跌停字段由数据源提供（普通 ±10%、ST ±5%、创/科 ±20%）。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-150 A 股交易规则 — 整百股与零股

买入数量 100 股整倍数；不足 100 股部分向下取整，取整后为 0 则下单失败。卖出可允许零股与清仓例外。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-160 A 股交易规则 — T+1

当日买入持仓当日不可卖；次日起方可卖。框架按"可卖持仓"与"在途持仓"分别记账。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-170 数据源 — qmt-gateway

通过外部 `qmt-gateway` 项目（已独立实现）拉取实时行情与历史 K 线；本项目按其 API 适配。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-180 数据源 — tushare（项目内已实现）

通过 `tushare` Python 库拉取 A 股历史日线、复权因子、涨跌停字段、交易日历等。`quantide.millionaire.data` 模块封装。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-190 复权与涨跌停 — forming bar

当日未收盘时，框架从最近 tick 合成"实时日线"（open/high/low/close/amount/volume + up_limit/down_limit + adj_factor）；复权完整链路含昨收价、复权因子、forming 字段。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-200 数据完整性校验与报告

数据同步后框架执行完整性校验（缺日、重复日、字段空值率等），生成报告 `data_quality_report.md`；UI 可查。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-210 运行模式 — 回测

历史区间回放策略，按选定下单方式撮合；输出回测报告（净值曲线、买入点、卖出点、MA 指标、参考线）。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-220 运行模式 — paper（仿真）

接入行情但不真发委托；按选定下单方式模拟撮合。输出与回测同结构的报告（外加"是否实盘价"标注）。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-230 运行模式 — live（实盘）

通过 qmt-gateway 真实发单；与撮合系统对接。提供 dry-run 切换开关（见 FR-240）。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-240 运行模式 — dry-run

实盘策略临时切换至"不下单"状态，策略持续运行、内部状态可观测；用户可随时切回 live。并行仿真（FR-221/222）可在 dry-run 期间观察策略行为。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-250 调度总览

调度器支持日线/实时/风控三类策略并行；同账户下资金隔离（独立策略），风控监控全局持仓。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-260 调度 UI

Web UI 列出当前所有运行中策略（含模式、状态、最后心跳）；支持启动/停止/切到 dry-run。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-270 策略评估指标 — 日线策略

年化收益、最大回撤、Sharpe、胜率、盈亏比、最大连续亏损天数等。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-280 策略评估指标 — 实盘/仿真

较日线回测增加：滑点、成交量占比、订单拒绝率、撮合失败原因分布。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-290 策略评估指标 — 风控策略

仅超额收益 + 触发次数 + 平均响应时间。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-300 可视化 — 净值曲线 + 参考线 + 买卖点

回测报告含净值曲线、参考线（基准指数）、买卖点 marker、MA 指标线。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-310 回测进度可视化

运行中回测展示进度条（按交易日推进）与最新净值。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-320 账户管理 — 总览与持仓

Web UI "账户" 页：现金、持仓、委托、成交、当日盈亏。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-330 实盘交易界面（§6）

实盘专属 UI：闪电单、限价单、撤单、改单；委托/成交实时刷新。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-340 仿真交易界面（§7）

仿真专属 UI：与 §6 同构但不允许真实下单；可一键"提升至实盘"（生成 live 任务）。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-350 消息通知 — 邮件 / 钉钉 / 飞书

策略事件（信号、成交、错误、风控触发）支持邮件 / 钉钉 / 飞书 webhook 推送；可在策略级配置。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-360 系统配置

系统级设置：网关连接、数据源、消息通道、用户偏好。

```yaml
testability: ✅
resolved: ✅
valid: ✅
```

### FR-370 安装与运行

提供 `pip install` / `uv install` 与 `millionaire init` 初始化向导；提供 `start.sh` 一键启动 web + 调度器。

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
- 项目使用 `uv` + `venv` 管理依赖，pyproject.toml 中已声明的库优先（不混用，如 `loguru` 与内置 logging 不混用）
- 项目从未发布过，不考虑旧版本兼容
- git remote owner (`zillionare`) 与 gh user (`quantclaws`) 不一致——v0.2 显式接受此状态

### 排除项
- **Billionaire / Zillionaire** 不在本仓库范围
- **AI Agent skill** v0.2 不交付，v0.3 计划
- **回测与实盘结果差异**允许（cheat-on-close 在回测用 T+0 收盘，仿真/实盘在尾盘集合竞价撮合，价格可能不同）—— 这是**已声明的预期差异**，非 bug

## 澄清记录

> **Sage 状态**: 本 spec 为 Sage Step 2 初稿，所有 FR/NFR 已落地。FR-010（SDK/Agent）按 Aaron 决定标记为 v0.2 占位、v0.3 实现。
>
> 待用户在 IDE 中 review 后，Sage 将在 Step 3 进一步追问或根据用户回答将 `resolved` 改为 ✅。
