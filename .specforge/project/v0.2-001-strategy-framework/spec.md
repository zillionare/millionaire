# Millionaire 策略框架与运行模式 — Spec

- **Spec ID**: v0.2-001-strategy-framework
- **创建日期**: 2026-06-15
- **状态**: v0.2-001 spec 覆盖 FR-010 ~ FR-360 范围; tag `v0.2-001-internal-locked` 标记基线; **AC 闭环** 至 FR-010/013/014/015/020/125/360 + NFR-060; **AC 待补** FR-030~080/090~130/140~180/200/230~260/440/450(按 P2 分域推进); FR-185 占位(算法见 spec-strategy.md §FR-185, P1 推进)

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

**Coverage cutoff**: 本 spec 当前定稿至 FR-260 (含 FR-440/450), FR-270 ~ FR-470 视为下一轮增量. FR-185 (持仓成本基准) 已解 (P1 经典方案 A, 见 [spec-strategy.md §FR-185](./spec-strategy.md)). 全部已锁定 FR 均已建 issue (Sage cycle 1+2: 33 个 issue 覆盖 FR-010~250 + FR-360/440/450).

**Coverage 进度** (2026-06-21 校准, 反映 P0-P2 工作):
- ✅ FR-010 ~ FR-185: spec + acceptance + test-plan + interfaces 四文档已对齐 (内审锁定)
- ✅ FR-190 ~ FR-260 + FR-440/450: spec + acceptance + test-plan 已补齐, 跨越 P2 域 1 (FR-030~080 调度/下单方式) / 域 2 (FR-090~110 内置策略) / 域 3 (FR-115/130 驱动契约) / 域 4 (FR-140~190 交易规则) / 域 5 (FR-200~250 运行时参数+调度+通知); FR-260/FR-460 调度 UI/系统配置已迁移 [v0.2-002-ui](../v0.2-002-ui/spec.md)
- ✅ NFR-060: 运行时注入契约, 见 [interfaces.md §7.4](./interfaces.md)
- ⏸ FR-270 ~ FR-470: spec 已有, acceptance/test-plan 待补 (数据同步/评估/账户/通知/安装等扩展域)
- ✅ FR-185: 经典加权均价方案 A (P1 已解), 见 [spec-strategy.md §FR-185](./spec-strategy.md)

#### v0.2-001 已锁定 FR (有锚点, 已建 issue)

| FR | 标题 | 锚点 | Issue |
|---|---|---|---|
| [FR-010](./spec-strategy.md#fr-010) | 策略对象模型与 SDK 暴露 | spec-strategy.md#fr-010 | [#55](https://github.com/zillionare/millionaire/issues/55) |
| [FR-013](./spec-strategy.md#fr-013) | RiskStrategy 结构契约 | spec-strategy.md#fr-013 | [#56](https://github.com/zillionare/millionaire/issues/56) |
| [FR-014](./spec-strategy.md#fr-014) | SDK 元数据接口 — 交易日历 | spec-strategy.md#fr-014 | [#57](https://github.com/zillionare/millionaire/issues/57) |
| [FR-015](./spec-strategy.md#fr-015) | SDK 元数据接口 — 证券列表 | spec-strategy.md#fr-015 | [#58](https://github.com/zillionare/millionaire/issues/58) |
| [FR-020](./spec-strategy.md#fr-020) | 自动发现策略 | spec-strategy.md#fr-020 | [#59](https://github.com/zillionare/millionaire/issues/59) |
| [FR-030](./spec-strategy.md#fr-030) | 策略参数跨模式透传 | spec-strategy.md#fr-030 | [#60](https://github.com/zillionare/millionaire/issues/60) |
| [FR-040](./spec-strategy.md#fr-040) | 一次开发四模式无感迁移 | spec-strategy.md#fr-040 | [#61](https://github.com/zillionare/millionaire/issues/61) |
| [FR-050](./spec-strategy.md#fr-050) | 下单方式 — cheat-on-close | spec-strategy.md#fr-050 | [#62](https://github.com/zillionare/millionaire/issues/62) |
| [FR-060](./spec-strategy.md#fr-060) | 下单方式 — 次日开盘（正常模式） | spec-strategy.md#fr-060 | [#63](https://github.com/zillionare/millionaire/issues/63) |
| [FR-070](./spec-strategy.md#fr-070) | 下单方式 — 次日限价 | spec-strategy.md#fr-070 | [#64](https://github.com/zillionare/millionaire/issues/64) |
| [FR-080](./spec-strategy.md#fr-080) | 跨模式回测-实盘差异（声明性） | spec-strategy.md#fr-080 | [#65](https://github.com/zillionare/millionaire/issues/65) |
| [FR-090](./spec-strategy.md#fr-090) | 内置策略 — 双均线（日线策略） | spec-strategy.md#fr-090 | [#66](https://github.com/zillionare/millionaire/issues/66) |
| [FR-100](./spec-strategy.md#fr-100) | 内置策略 — 回落卖出（风控） | spec-strategy.md#fr-100 | [#67](https://github.com/zillionare/millionaire/issues/67) |
| [FR-110](./spec-strategy.md#fr-110) | 内置策略 — 成本止损（风控） | spec-strategy.md#fr-110 | [#68](https://github.com/zillionare/millionaire/issues/68) |
| [FR-115](./spec-strategy.md#fr-115) | BaseStrategy 驱动契约（独立策略默认） | spec-strategy.md#fr-115 | [#69](https://github.com/zillionare/millionaire/issues/69) |
| [FR-125](./spec-strategy.md#fr-125) | 风控策略驱动契约 | spec-strategy.md#fr-125 | [#70](https://github.com/zillionare/millionaire/issues/70) |
| [FR-130](./spec-strategy.md#fr-130) | 风控策略契约（生命周期 + 不可回测） | spec-strategy.md#fr-130 | [#71](https://github.com/zillionare/millionaire/issues/71) |
| [FR-140](./spec-trading.md#fr-140) | 交易规则 — 价格（涨跌停） | spec-trading.md#fr-140 | [#72](https://github.com/zillionare/millionaire/issues/72) |
| [FR-150](./spec-trading.md#fr-150) | 交易规则 — 数量 | spec-trading.md#fr-150 | [#73](https://github.com/zillionare/millionaire/issues/73) |
| [FR-160](./spec-trading.md#fr-160) | 交易规则 — 时间 | spec-trading.md#fr-160 | [#74](https://github.com/zillionare/millionaire/issues/74) |
| [FR-170](./spec-trading.md#fr-170) | 交易规则 — 特殊状态（停牌） | spec-trading.md#fr-170 | [#75](https://github.com/zillionare/millionaire/issues/75) |
| [FR-180](./spec-trading.md#fr-180) | 交易规则 — 资金 | spec-trading.md#fr-180 | [#76](https://github.com/zillionare/millionaire/issues/76) |
| [FR-185](./spec-strategy.md#fr-185) | 持仓成本基准（加权均价 — 经典方案 A, P1 已解） | spec-strategy.md#fr-185 | [#77](https://github.com/zillionare/millionaire/issues/77) |
| [FR-190](./spec-trading.md#fr-190) | 交易规则 — 回测 vs 实盘的差异 | spec-trading.md#fr-190 | [#78](https://github.com/zillionare/millionaire/issues/78) |
| [FR-200](./spec-strategy.md#fr-200) | 运行时参数（框架管理，策略不可见） | spec-strategy.md#fr-200 | [#79](https://github.com/zillionare/millionaire/issues/79) |
| [FR-210](./spec-strategy.md#fr-210) | 虚拟账本（按 qtoid 归因） | spec-strategy.md#fr-210 | [#80](https://github.com/zillionare/millionaire/issues/80) |
| [FR-220](./spec-strategy.md#fr-220) | 手工交易/补单/风控卖出的归属 | spec-strategy.md#fr-220 | [#81](https://github.com/zillionare/millionaire/issues/81) |
| [FR-230](./spec-strategy.md#fr-230) | 独立策略的回测启动路径 | spec-strategy.md#fr-230 | [#82](https://github.com/zillionare/millionaire/issues/82) |
| [FR-240](./spec-strategy.md#fr-240) | 独立策略的无回测启动路径 | spec-strategy.md#fr-240 | [#83](https://github.com/zillionare/millionaire/issues/83) |
| [FR-250](./spec-strategy.md#fr-250) | 风控策略调度 | spec-strategy.md#fr-250 | [#84](https://github.com/zillionare/millionaire/issues/84) |
| [FR-360](./spec-trading.md#fr-360) | 评估指标 — 风控策略（Triple Barrier） | spec-trading.md#fr-360 | [#85](https://github.com/zillionare/millionaire/issues/85) |
| [FR-440](./spec-strategy.md#fr-440) | dry-run 模式 | spec-strategy.md#fr-440 | [#86](https://github.com/zillionare/millionaire/issues/86) |
| [FR-450](./spec-strategy.md#fr-450) | 消息通知（微信）— 事件定义 | spec-strategy.md#fr-450 | [#87](https://github.com/zillionare/millionaire/issues/87) |

> **Issue 格式** (Sage cycle 1 决策, 2026-06-17; cycle 2 调整, 2026-06-22):
>
> **Sage cycle 1** (FR-010/013/014/015/020, #55-#59) — 旧格式:
> - **Body**: `### 需求 ID` + `### Spec 链接` + **Spec 段落全文** (自包含, 不依赖外部文档)
> - **第一条 reply**: `## 验收标准 (AC 列表)` 完整从 acceptance.md 复制, 每条 AC 带 `AC-1, AC-2, ...` 编号
> - **关联 Project**: `Millionaire 0.2` (#5, 位于 zillionare user 下)
>
> **Sage cycle 2** (FR-030~250 + FR-360/440/450, #60-#87, 2026-06-22) — **新格式** (GitHub 文档内链接):
> - **Body**: `## 需求 ID` + `## 文档链接` (Spec/Acceptance/Test-plan/Interfaces 4 个文档锚点链接, **不复制内容**)
> - **理由**: spec 文档在 PR 中可能更新 (如 v0.2-001 流程 F1~F5 修了 spec), issue body 不必同步, 最多加 comment 提示文档有更新. AC 验证时直接读最新 acceptance.md.
> - **关联 Project**: `Millionaire 0.2` (#5, zillionare user) — 关联操作待 gh token scope (`read:project`) 补充后单独 batch.
>
> **范围说明** (2026-06-22 校准):
> - Sage cycle 1 (2026-06-17): FR-010/013/014/015/020 (5 issue)
> - Sage cycle 2 (2026-06-22): FR-030/040/050/060/070/080/090/100/110/115/125/130/140/150/160/170/180/185/190/200/210/220/230/240/250/360/440/450 (28 issue)
> - 排除: FR-011/FR-012 已删; FR-260 已迁 v0.2-002-ui; FR-270~470 (除 FR-360 外) 标 ⏸ deferral
> - 全部已锁定 FR (FR-010~250 + FR-360/440/450) 均已建 issue, 共 33 个 (#55-#87)

---

## 跨分册引用约定

- 引用具体 FR 时使用: `(见 [spec-strategy.md §FR-115](./spec-strategy.md))`
- 引用整个分册时使用: `(见 [spec-strategy.md](./spec-strategy.md))`
- 不再使用"见上一节" / "见下一节" 等位置性引用
