# AI 因子风洞工作台与发布完备性 — 验收标准（Acceptance Criteria）

- 状态：实施验收标准；实际执行结果见[审查闭环](../../reviews/2026-11-18/)及对应提交的 CI。
- 规范来源：[主规格](spec.md)、[接口契约](interfaces.md)、[测试计划](test-plan.md)。

## 1. 验收总表

| AC 编号 | 对应需求 | 验收判定标准 |
| --- | --- | --- |
| AC-5001 | FR-5001 | 在不修改 `quantide/factors/` 任何源码文件的情况下，向 `<app_config_dir>/factors/` 放入合法 `.py` 因子插件并扫描后，该因子出现在 Web「因子」总览/侧栏/详情卡片及同周期 LightGBM 回测因子勾选列表中，可正常完成检验与回测。 |
| AC-5002 | FR-5001 / NFR-5002 | 外部因子目录中同时存在语法错误文件、抛出导入异常文件、与内置因子重名文件、缺少元数据文件及合法插件文件时，服务正常启动，内置因子与合法插件正常可用，坏文件逐一生成准确的 `SkippedFactorEntry` 诊断；指向源码树内部的目录配置被明确拒绝。 |
| AC-5003 | FR-5001 / NFR-5003 | 修改外部因子插件的计算公式代码后，`factor_version` 立即变化，关联的特征面板缓存、跟踪快照和风洞徽章全部自动标记陈旧，不会命中旧缓存结果。 |
| AC-5004 | FR-5002 | 合法外部因子运行风洞校验时，契约检查、跨证券隔离、至少 3 个截断点的三类未来扰动（冷/热缓存）及 `GOLDEN_CASES` 全部 `PASS`，历史截断点及之前输出逐位一致。 |
| AC-5005 | FR-5002 | 分别注入负向 `shift(-1)`、未加 `.over("asset")` 的跨证券滚动、全样本未来均值标准化、以及二次重复乘 `adjust` 的坏因子插件时，风洞校验均返回 `FAIL`（退出码 `3`），并定位到首次差异的日期、证券、期望值与实际值；Web 向导默认阻止勾选 `FAIL` 因子运行正式回测。 |
| AC-5006 | FR-5003 | 单因子检验报告与 `factor check --json` 输出候选因子与已注册同周期因子的截面 Spearman 秩相关 Top-5；构造一个与 `ma20_slope` 单调同向变换的冗余因子时，`max_abs_rank_corr > 0.85` 且触发 `HIGH_COLLINEARITY` 提示；某个无关对照因子存在缺失值不改变其余因子相关性数值。 |
| AC-5007 | FR-5004 | 用户可将不同因子子集、训练标签与策略超参保存为多个具名 `FactorPreset`；删除或破坏某预设引用的外部因子后，运行该预设会明确报错阻断，不会静默删列继续运行。 |
| AC-5008 | FR-5004 | 对 Baseline 预设与新增 1 个 AI 因子的 Variant 预设执行一键消融对比（Ablation），两次运行自动锁定相同日期区间、初始资金、费用、PIT 选池与随机种子，报告准确输出超额净值差、回撤差、换手率差与差异因子的平均绝对 SHAP 贡献占比。 |
| AC-5009 | FR-5005 / NFR-5001 / NFR-5005 | 在无网络（`--disable-socket`）且未配置任何 Tushare Token 的全新环境中，通过向导选择“内置离线体验数据包”可在数秒内完成初始化，顺利跑通因子检验报告、LightGBM 回测与 K 线单笔 SHAP 预测解释；静态资源增量 `≤ 15 MB`。 |
| AC-5010 | FR-5005 / NFR-5004 | 启用、使用及退出内置体验数据包全过程不写入、不覆盖用户正式 `data_home` 目录，不触发后台外部爬虫同步；体验模式下全局顶栏显示体验数据标识与切换正式源入口。 |
| AC-5011 | FR-5006 | `millionaire` 新增的 `data status`、`factor list/init/check/study`、`preset list/save`、`backtest run` 命令在 `--json` 模式下均输出合法标准 JSON（无 `NaN`/`Infinity`、无未脱敏 Token），退出码严格符合 `0/2/3/4` 语义约定。 |
| AC-5012 | FR-5006 | 仓库包含官方 Agent `SKILL.md` 及 `docs/ai-development.md` 挂载说明；按 Skill 指引驱动端到端测试脚本（创建插件 → 风洞拦截坏实现 → 修复重检 `PASS` → 查正交性 → 保存预设并消融回测）闭环通过，且研究 CLI 不修改任何运行中仿真账户状态。 |
| AC-5013 | FR-5007 | Web「因子详情页」与「策略回测报告页」准确渲染五态风洞体检徽章（`PASS` / `FAIL` / `INCONCLUSIVE` / `STALE` / `UNVERIFIED`）；篡改已通过因子的源码或底层行情文件后刷新页面，徽章立即由 `PASS` 变为 `STALE`。 |
| AC-5014 | FR-5008 | 根目录 `README.md` 与 `docs/index.md` 叙事一致，包含 3 分钟免 Token 快速体验指引、四大核心能力视觉图示与客观竞品能力对照表；`mkdocs build --strict` 零警告通过。 |
| AC-5015 | FR-5009 | 未配置 Tushare Token 时，选择免积分历史日线源（BaoStock 日线适配器）可拉取并落库符合 SQEP 口径的日线 OHLCV、复权因子、交易日历与证券列表；缺少市值列时选池自动按配置降级为成交额流动性截断并显式标注，不伪造零市值。 |
| AC-5016 | FR-5009 | PIT 股票池过滤严格使用信号日 `t0` 当时已知的上市天数、当日停牌、当日历史 ST 状态与当日收盘涨跌停状态；对“2022 年正常交易、2024 年才被 ST 或退市”的测试样本，回测 2022 年时绝不将其误剔除；若数据源缺失历史 ST 表则明确输出 `st_history_unavailable` 警告。 |
| AC-5017 | FR-5010 | 内置日线 ML 策略支持 `raw_return`、`excess_mean`、`cs_rank` 三种训练标签，在 3×10 手算面板上与独立公式计算结果逐位一致；未成熟交易日整日不进入截面均值或截面秩计算；切换 `label_kind` 会生成独立的 `model_key` 且 SHAP 解释可准确复现。 |
| AC-5018 | FR-5011 | 全新启动 CE 服务时，`risk_program_registry` 默认仍为空列表；执行 `millionaire risk-extension enable --copy-example` 后，`example.single_asset_weight_cap` 在回测叠加层和 Paper 仿真中均生效且单标的买入市值不超过设定权益比例上限。 |
| AC-5019 | FR-5012 | `BAR_INTERVAL = "30m"` 的策略转入仿真后，每个闭合 30m bar 的历史数据就绪时影子账户准确回放一次，未闭合 forming bar 绝不提前触发；`/tracking/<账户ID>` 展示 30m 逐 bar 对照净值、持仓与缺口状态。 |
| AC-5020 | FR-5012 | 30 分钟 Shadow-Run 在午休跨段、跨交易日 T+1 解锁、历史分钟缺口延迟回补以及进程强杀重启场景下，与独立人工分钟账本对拍一致，无重复下单、无漏算已闭合 bar。 |
| AC-5021 | FR-5012 | `docs/native-installation.md` 首屏显著包含三平台安装包 SHA256 校验命令及 macOS Gatekeeper / Windows SmartScreen 未签名放行步骤，`docs/index.md`、`docs/scope.md`、`docs/roadmap.md`、`docs/paper-trading.md`、`docs/initialization.md`、`docs/ai-development.md` 中的向导、AI 工坊与 30m Shadow-Run 状态说明与实际实现完全同步。 |
| AC-5022 | 版本边界与开放扩展 | 双重验证“官方不预置，扩展不封堵”：① CE 官方内置代码未捆绑 **millionaire pro** 专属模块（官方 `DailyBasic` 采集维持 `total_mv`/`circ_mv` 而不预置拉取 `pe_ttm`/`pb`/`turnover_rate`，不内置申万行业库与中性化开关，内置 ML 示例不预置 `hold_buffer`/`buffer_k`，不内置三重障碍/回撤卖出/成本止损私有风控，`supports_live_trading()` 实盘隔离完好）；② 用户/AI 在外部目录中自定义带附加列（如自定义换手率/估值/行业列）的数据面板与因子插件、在 `strategy_dir` 自定义带持仓缓冲带的策略子类、在用户扩展中自定义风控程序，均可顺畅加载并运行，无任何字段黑名单或人为限制。 |
| AC-5023 | 范围控制红线 | 确认未新增已裁定暂缓的柜台 OpenAPI 靶场 CLI 与异常告警 UI 联动工程，避免非计划范围膨胀。 |
| AC-5024 | NFR-5004 / NFR-5006 | 全量单元与验收测试离线通过，新增关键变异 100% 被目标断言杀死，满足 `docs/quality.md` 全部代码质量（含 Web Agent 与 CLI 零重复业务逻辑 `R0801`）与覆盖率门禁，且 `python -m scripts.artifact_paths --check-layout` 通过。 |
| AC-5025 | FR-5013 | 初始化向导“运行环境”步骤与系统设置同时展示并持久化 `data_home`、`factor_dir`、`strategy_dir`，默认路径免手敲即可自动创建并通过服务进程读写探针校验，保存后自动挂载至因子发现器与 `StrategyLoader`；指向源码 checkout 内部的路径或不可写路径被明确拦截并给出中文原因。 |
| AC-5026 | FR-5013 / NFR-5007 | 初始化向导中的“AI 助手配置”步骤为 `OPTIONAL`，一键跳过后仍可正常完成初始化并使用全部非 AI 功能；配置 OpenAI 兼容参数后“测试连接”能准确区分鉴权失败、模型不存在、限流与网络不可达；`api_key` 在 HTML、API JSON、日志与异常信息中全程脱敏，绝不明文回显。 |
| AC-5027 | FR-5014 / NFR-5001 | 在离线回环 Mock OpenAI 兼容模型驱动下，不会编程的用户仅通过 Web `/factors/studio` 输入自然语言需求即可走通闭环：当首轮模型生成漏写 `.over("asset")` 的坏因子时，工坊自动触发风洞拦截、回喂 `first_difference` 自我修复并二轮风洞 `PASS`、渲染通俗 IC/十分位/正交性卡片，并可一键创建 `FactorPreset` 跑通消融回测；连续失败达到 `max_repair_rounds`（默认 3 轮）时受控停止并展示通俗诊断，不无限重试。 |
| AC-5028 | FR-5014 / NFR-5007 | Web AI 工坊工具沙箱严格拒绝任何越出 `factor_dir` 直接子级的写入请求（覆盖 `../` 路径穿越、绝对路径、符号链接逃逸、尝试写 `strategy_dir` 或内置模块重名），无任何任意 Shell 执行工具；会话持久化在刷新页面后完整恢复，运行中点击“停止”可及时终止模型轮次与后台子进程任务。 |

## 2. 阻断判定原则

- 任一 `AC-5001` ～ `AC-5028` 出现空测试、skip、xfail、使用生产被测函数自证 oracle、或修改既有门禁阈值均视为未通过。
- 涉及未来扰动检验（`AC-5004`、`AC-5005`、`AC-5016`、`AC-5017`、`AC-5019`、`AC-5027`）的历史输出对比采用逐位精确相等，不适用浮点金额容差豁免。

## 3. 2026-11-18 实施补充

- `AC-5012` 的 CLI 闭环必须在真实子进程中执行，且研究/消融前后 Paper 账户事实与正式模型 `latest` 指针均不变；实验模型仍需可通过不可变 `model_ref` 回放。
- `AC-5017` 的退出日按权威交易日历计算；退出日缺该证券价格时标签为该行 `null`，截面标签整日排除。历史训练截面按每个信号日当时资格形成，不把当前决策日筛选结果或后来 ST/退市状态倒灌到全部训练历史。三种标签与实际训练行需由独立 3×10 oracle 对拍。
- `AC-5019/AC-5020` 的同一闭合槽位后续 tick 仍推进 `next_open` 队列，但策略回调只执行一次；已有 actual 事实的槽位不得被当前账户快照覆盖。
- `AC-5027/AC-5028` 的 Web 闭环只 mock 外部模型/transport；插件写入、worker 风洞、first-difference 修复、真实 IC/正交性、预设与模型引用必须走生产工具路径。新一轮完成后，旧轮次任何延迟返回都不得覆盖新轮状态、卡片或 active factor。


## 交付状态（2026-11-18）

本文件保留需求与验收合同。实现以当前源码和机器验收为准：AC-5001～AC-5028 逐项绑定具体测试节点，普通因子准入只阻断风洞 `FAIL`，AI 工坊必须当前源码指纹 `PASS`；研究标准入口记录实际 PIT `universe_filter`/逐日诊断、价格口径和依赖指纹；30 分钟影子按 8 个闭合槽位、forming 不触发、真实 actual 事实及 T+1/缺口/重启账本运行。无法恢复的输入或证据标记 `STALE`/`INCONCLUSIVE`/不可用，不静默通过。跨平台与实体安装结论只以对应 CI/安装器证据为准。
