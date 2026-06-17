# Millionaire 策略框架与运行模式 — Spec

- **Spec ID**: v0.2-001-strategy-framework
- **创建日期**: 2026-06-15
- **状态**: v0.2 内审中(已对齐 story + Strategy 抽象根重构 + 4 文档同步;spec 已拆分 3 分册)

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
story: 作为用户，我编写使用 30m 等 live-only 数据粒度的独立策略（如 30 分钟隔夜策略）时，框架通过 on_day_open / on_bar 驱动，调用 get_bars(frame_type="30m") 的策略不可回测，BacktestRunner 会抛 UnsupportedFrameTypeForBacktest
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

### scenario-020 独立策略（30 分钟隔夜）上实盘

编写 `OvernightStrategy(BaseStrategy)`（直接继承 BaseStrategy，使用 `frame_type="30m"` 数据），在仿真界面运行 1 周 → 切到实盘 → 系统当日停止原仿真 → 自动创建并行仿真 → 策略在实盘正常发单。期间如需暂停，点 "dry-run"，策略继续运行不实际下单，可观察并行仿真曲线。

### scenario-030 风控策略叠加

独立策略"双均线"进入实盘时，其绑定的"成本止损"风控策略自动激活。持仓跌破买入价 5% 时风控策略发卖出单，成交归属宿主策略的虚拟账本，不影响宿主收益计算，但贡献一条超额收益记录（按 Triple Barrier 计算：从卖出日起监控 N 日，期间若标的价格上涨到 `P_sell * (1 + up_threshold)` / 下跌到 `P_sell * (1 - down_threshold)` / N 日内未触发则按收盘价退出，分别记 `−up_threshold` / `+down_threshold` / `P_sell/Close_N − 1`，N=0 即当日收盘）。此条贡献属于"双均线进入实盘 → 停止"这一开启区间；风控若被重新开启，则另起新开启区间独立计算。


## 索引

本 spec 已按域拆分为 3 个分册(FR 编号不变, 引用稳定):

| FR 范围 | 所属分册 | 说明 |
|---|---|---|
| FR-010 ~ FR-080 | [spec-strategy.md](./spec-strategy.md) | 策略对象模型、SDK 暴露、下单方式、跨模式差异 |
| FR-090 ~ FR-110 | [spec-strategy.md](./spec-strategy.md) | 内置策略(双均线/回落卖出/成本止损) |
| FR-115 ~ FR-130 | [spec-strategy.md](./spec-strategy.md) | 驱动契约 + 风控契约 |
| FR-140 ~ FR-180 | [spec-trading.md](./spec-trading.md) | 交易规则(涨跌停/数量/时间/特殊状态/资金) |
| FR-185 | [spec-strategy.md](./spec-strategy.md) | 持仓成本基准(加权均价算法) |
| FR-190 | [spec-trading.md](./spec-trading.md) | 回测 vs 实盘差异 |
| FR-200 | [spec-strategy.md](./spec-strategy.md) | 运行时参数(策略层) |
| FR-210 ~ FR-220 | [spec-trading.md](./spec-trading.md) | 虚拟账本 + 手工交易归属 |
| FR-230 ~ FR-260 | [spec-strategy.md](./spec-strategy.md) | 调度(回测启动路径/无回测启动/风控调度/调度 UI) |
| FR-270 ~ FR-470 | [spec-trading.md](./spec-trading.md) | 数据源、评估、账户、UI、通知、安装 |
| NFR-010 ~ NFR-050 | [spec-foundation.md](./spec-foundation.md) | 非功能需求 |
| 已知约束 / 排除项 / 推迟 | [spec-foundation.md](./spec-foundation.md) | 范围声明 |

**Coverage cutoff**: 本 spec 当前定稿至 FR-185(含占位), FR-190 ~ FR-470 视为下一轮增量.

**Coverage 进度**:
- ✅ FR-010 ~ FR-185: spec + acceptance + test-plan + interfaces 四文档已对齐
- ⏸ FR-190 ~ FR-470: spec 已有, acceptance 待补, test-plan 待补

---

## 跨分册引用约定

- 引用具体 FR 时使用: `(见 [spec-strategy.md §FR-115](./spec-strategy.md))`
- 引用整个分册时使用: `(见 [spec-strategy.md](./spec-strategy.md))`
- 不再使用"见上一节" / "见下一节" 等位置性引用
