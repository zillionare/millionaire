# 首页产品亮点与 CE 实现核实

日期：2026-11-03。范围：用户修改的 `docs/index.md` 与
`.louke/project/specs/v0.2-001-strategy-framework/story.md` 中相关需求，
对照当前工作区代码核实。保留首页的产品宣传口吻，将实现范围直接写清。
这是 CE 源码审查，不是 millionaire pro 发布或实盘验收。

## 产品命名

- millionaire：社区版和专业版的合称，用于共有设计或由上下文明确的产品描述。
- millionaire-ce / CE：本仓库的社区版。
- millionaire pro：专业版；内置三重障碍等专属能力必须明确归属，不能用系列合称暗示 CE 自带。
- 包名、CLI、导入名、现有运行时 edition ID 和测试 marker 保持兼容，不据产品文案改名。

## 逐项结论

| 首页亮点 | 当前实现 | 文档处理 |
| --- | --- | --- |
| 同一策略跨运行模式 | 已有统一 Broker 边界、回测、Paper 和独立 HTTP 模拟柜台；CE 的真实交易被版本门禁阻止。 | 保留无感迁移亮点，标明 CE 的第三条路径由模拟柜台验证；真实交易由 millionaire pro 或用户宿主扩展装配。 |
| 回测参数自动带入 | `deploy_to_paper()` 默认采用 `run.config`，沿用策略周期，并重新设置本金；部署服务也接受显式 config，Web 部署会合并费用、风控等配置。 | 可宣称默认沿用，不能宣称所有调用路径都强制禁止修改。历史 story §1.3 的强锁定要求不能作为已实现证据。 |
| HTTP 柜台与自行适配 | 有 HTTP Broker 适配边界、独立模拟柜台和契约验收。 | 保留自行适配与 AI 辅助的价值；券商实际接口、权限与接入条件仍是前提，不能承诺任意券商即插即用。 |
| 统一数据与 adapter | 有 `DataFetcherPort`、标准 schema、抓取注册表、存储和行情 Hub。 | SQEP 可作为项目内统一约定的名称。历史数据落盘与实时 Hub 分别描述，不能暗示所有 tick 都持久化或新增网络协议服务已经存在。 |
| 固有策略周期与交易防呆 | Runner、运行时部署及恢复均检查固定周期；交易路径有 T+1、资金、限价等检查。部分路径缺有效限价时仍会跳过该项约束。 | 保留防呆亮点和数据前提，不能宣称对任意 Python 策略绝无绕过或回测必然可靠。 |
| LightGBM、优化和归因 | 已有 LightGBM 示例、因子研究及参数优化；SHAP 解释模型预测。 | 称为预测归因/预测解释；完整收益归因仍属下一版。 |
| 主策略与风控自由叠加 | 有显式注册、兼容检查、优先级、多 overlay，以及 Paper 风控构造；默认注册表为空。 | 保留兼容风控可复用的亮点，说明用户需注册实现且适配器提供所用模式的工厂；三重障碍标明 millionaire pro。 |
| Cheat-on-Close | 已有收盘与次日开盘时序、收盘前运行窗口及 T+1。 | 保留尾盘交易的价值。去掉“小资金实盘差异不大”和“接近 T+0”：未有真实成交证据，且同日买入不能同日卖出。 |
| Shadow-Run | 进入 Paper 时默认建跟踪任务和初始影子账户；18:45 盘后用日线回放，记录影子与 actual 快照；有净值、回撤及每日差额页面和开关。 | 日线双实例对照已实现。回测实例需要完整当日数据，盘后运行符合该周期的自然对照时点；30 分钟生命周期和自动差异归因仍待补齐。 |

## 代码与现有用例证据

- 模式迁移与默认参数：`quantide/service/strategy_runtime.py` 的
  `deploy_to_paper()` / `deploy_to_live()`；`quantide/web/pages/strategy.py` 的
  `_deployment_form_config()`；`quantide/config/features.py`。
  独立 HTTP 三路径验收：`tests/e2e/three_mode/test_ce_parity.py`。
- 固定周期：`quantide/service/runner.py` 的 `validate_strategy_interval()`，
  `quantide/service/strategy_runtime.py` 的 `_validate_config_interval()` 和
  `validate_runtime_interval()`。
- 数据：`quantide/core/ports/data_fetcher.py`、`quantide/core/bar_schema.py`、
  `quantide/data/fetchers/registry.py`，以及 `docs/SQEP.md` 说明的单位/时间前提。
- 风控：`quantide/service/risk_programs.py`、`quantide/service/risk_overlay.py`；
  `tests/unit/quantide/service/test_risk_programs.py`、`test_risk_program_live_wiring.py`。
  注册并不保证一个适配器兼容所有策略、周期或模式。
- 影子任务：`quantide/service/strategy_tasks.py` 的 `attach()`、`_run_shadow()`、
  `_actual_snapshot()`、`run_eod()` 和 `_process_shadow_intents()`；
  `quantide/service/shadow_broker.py` 使用日线视图，独立保存现金与持仓。
  `_run_shadow()` 每次新建策略对象，只调用一次日线时点的 `on_bar()`，并非通用分钟生命周期；
  未按常规运行器完整重放自定义状态与所选风控。
- 影子存储和 UI：`quantide/service/strategy_tracking.py` 存储每日来源、账户、交易和模型摘要；
  `quantide/web/pages/tracking.py` 展示净值/回撤/差额，并没有逐笔信号差异列表。
  `tests/unit/quantide/service/test_strategy_tasks.py` 覆盖任务注册、日终快照和 next-open 影子意图；
  `test_strategy_tracking.py` 覆盖存储与基础撮合。
- LightGBM 与研究工具的能力和边界，沿用 `docs/factors-and-ml.md`、
  `docs/optimization.md`、`docs/prediction-explanation.md` 的实现说明。

## 仍需独立实现或验收的部分

1. 策略参数不可变的完整服务端合同；当前是默认继承，不等于强制锁定。
2. 覆盖 30 分钟逐 bar、完整策略状态、生命周期和所选风控的影子重放。
3. 信号、委托、成交的逐条对照与差异原因诊断；净值曲线只能帮助定位问题。
4. millionaire pro 的内置风控和真实柜台行为；CE 仓库不能证明专业版发行质量。
5. 完整收益归因与通用 AI 策略审计，继续按 v0.4 规划交付。

本次不据首页宣传扩展 CE 的运行能力或修改交易代码，也不将历史 story 视为发布完成清单。

## 验证记录

- 严格文档构建通过：经 `scripts.artifact_paths --run` 执行
  `python -m mkdocs build --strict --site-dir /tmp/millionaire-ce/index-capability-review/site`。
  同时确认输出中的 `shadow-run` 锚点与首页跳转一致，修正 `quickstuart.md` 拼写错误。
- 上述 5 个现有测试文件定向运行：**19 passed**，无 skip/xfail。
  覆盖影子任务与存储、风控注册和运行时接入、独立 HTTP 模拟柜台的现金/持仓/费用一致性及恢复。
  测试禁用外网，只允许本地回环和 Unix socket；不使用 Tushare token。
  报告：`/tmp/millionaire-ce/index-capability-review/related-tests.xml`。
- `git diff --check` 与 `python -m scripts.artifact_paths --check-layout` 通过。
- 本次只修改文档与 Agent 指引，未运行全量生产质量扫描、全量回归、安装包重建或专业版验收。
  定向测试通过不能补齐本报告列出的参数锁定和影子生命周期缺口。
