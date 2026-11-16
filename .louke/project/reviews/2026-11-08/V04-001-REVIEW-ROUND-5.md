# v0.4-001 第五轮复核：第四轮 12 项修复

日期：2026-11-08。对象：基于 `b790c71` 的当前未提交工作区。只审查并新增本报告，未修改实施代码、fixture、规格或质量预算，未提交/部署/发布。

## 结论

**请求修改。不能关闭全部 12 项。** 大部分原反例已有有效修复，但第四轮 R4、R6、R7、R8、R12 仍存在可复现的未关闭部分。下文仅集中说明这五项，不将其重新包装为更多互不相关的新需求。

## 第四轮关闭状态

| 第四轮项 | 本轮状态 |
| --- | --- |
| R1：实际期末权益不参与对账 | 原反例关闭。1000→995 现在报告期末 995、delta=-5、residual=-5、OK_WITH_RESIDUAL；补了现金/持仓差异检查。 |
| R2：月中历史被当作闭合月线 | 截断日历的原反例关闭；history 和示例改传 full_calendar。月线实际调度/成交时序仍见 R4。 |
| R3：不同账户共享意图键 | 原反例关闭。增加 lifecycle/account/strategy/version/params 命名空间，并按 namespace 过滤 due 意图。 |
| R4：运行入口拒绝月线、周期混淆 | 周期 token 和创建/恢复入口已修；新增真实策略三 Broker 测试。但次日成交仍提前发生，不能关闭，见 F1。 |
| R5：spawn 子进程未初始化数据 | 原反例关闭。持久 payload 增加 data_home，子进程 init_data(..., init_db=False)；新增不 mock 子进程的成功测试并实际通过。 |
| R6：失去所有权/stop 后继续发布 | set_result 的 owner/lease 条件及 stop 的活动 cancel 有进展；跟踪快照仍有检查后发布竞争，heartbeat 失权不通知 cancel，见 F2。 |
| R7：变异没有真正施加 | 部分变异开始 patch 目标或明确改变状态，但费用 baseline 仍依赖受审生产实现，不是独立 oracle，见 F3；不能据此验收完整关键变异体系。 |
| R8：全部贡献归最后一个策略 | 已知成交来源的原简单样本修复；未知期初持仓被按已知成交比例重新归属，仍违反“来源未分配”，见 F4。 |
| R9：基准区间/指纹 | 两个原反例关闭：按 period.end_date 对齐，指纹绑定基准及选定期间。仅按日汇总外部流量仍不构成完整事件分段 TWR，不能顺带声明该合同完成。 |
| R10：任务 scope 干扰、过期不重排 | 原反例关闭：替代区分 scope；过期且尚有预算的任务可重新 claim。完整跨进程恢复和所有权安全还受 R6 约束。 |
| R11：合成 Pearson 目标改变、遗漏种子 | 两个原反例关闭。改用简单收益，多种子逐一运行；target=.5 的直接与 horizon 结果一致。统计区间覆盖率/功效校准仍需独立验收证据。 |
| R12：静态 39/40 covered | 无结果时改为 mapped、检查路径，已有进展；JUnit 失败/跳过及用例身份不参与判定，仍会假报 covered，见 F5。 |

## F1 · P1 · 原 R4 未关闭：月末回调已写入次日成交，next_open 只剩时间标签

位置：`quantide/strategies/example/monthly_ma.py:128–147`，`quantide/service/runner.py:562–570,588–600`。

示例在信号日 enqueue 后立即 `_submit()`，只是把 order_time 设置为次日 09:30；BacktestBroker 会立即读取该未来日期行情并更新现金/持仓/成交。FrameType.MONTH 没有进入已有 next_open 排队代理。

独立复现：只调用一次 `on_bar(2024-01-31 15:00)`，尚未进入 02-01 的执行回调，账户现金已从 10000 降到 10，已经存在 1 笔 `2024-02-01 09:30` 的成交。Paper/柜台因延后撮合还未成交，三路径在信号时点并不一致。

新增 `test_real_monthly_strategy_runs_across_three_brokers` 在信号日只检查 Paper/remote 无成交，遗漏 Backtest；因此能在该错误下通过。Runner 的默认 next_open 回调时刻还来自 09:30，不能在当月最后交易日早盘读取当天最终月线收盘值。

修复要求：信号 bar 闭合时只产生持久意图，真实执行事件到达时再变动账户；订单排队可以提前，但不能先产生未来成交。用真实 BacktestRunner/月线时钟验证月末盘前、盘后、次日开盘、区间结束及中断恢复，断言三个路径在每个事件边界的订单/现金/持仓一致，而不只核对最终结果。

## F2 · P1 · 原 R6 未关闭：所有权检查与快照发布不是原子操作

位置：`quantide/service/factor_tracking.py:542–568`，`quantide/service/factor_runs.py:563–570`。

`_publish_snapshot()` 在 fence() 返回 True 后，才计算 publication_plan 并写 JSON；fence 是独立 SQLite 查询，后续写入不受同一事务/有效 generation 条件保护。进程内 RLock 不能阻止另一 worker 修改数据库租约或另一个进程更新配置。

确定性竞争复现：

1. 旧 owner 拥有有效租约，fence 查询得到 True 后暂停。
2. 撤销旧 owner，任务由新 owner 领取。
3. 恢复旧发布调用。
4. `old_owns_after_revoke=False`，但旧快照仍成为 current，`published=True`。

另一个原反例仍成立：superseded 后 heartbeat 的 touch 失败并退出，但 cancel Event 仍 False。新增 set_result 的 SQL 条件确实能拒绝旧 owner 的研究结果；不能把这一修复推论为 JSON 跟踪快照也已具备相同 fencing。

修复要求：把当前快照指针与任务 owner/generation 的最终提交放在一个可原子校验的持久事务/CAS 中。大结果可先写不可变文件，再在该事务内发布指针。失权时立即设置 cancel；旧任务不得以 last_attempt 更新为由改写新状态。新增检查后撤销租约、跨进程新旧发布交错的测试，不能只测 fence 一开始就是 False。

## F3 · P1 · 原 R7 未关闭：费用变异的 baseline oracle 仍来自生产函数

位置：`quantide/audit/mutations.py:144–175`。

新增 fee_omission 变异确实把 PaperMatching._calculate_fee patch 成零，这是有效进展。但 baseline 账户期望值使用 `_production_fee(False)` 生成；被测费用错了，期望值也跟着错。

独立复现：先把正常生产费用函数故意改为固定 123 元，再运行 fee_omission case，仍报告 KILLED。此 fixture 的明确参数应得 `max(5,1000*0.0003)+1000*0.00001=5.01` 元，baseline 本该先失败，而不是被认证为正确。

其他局部变异也仍不能代替真实执行链：T+1 case 改的是独立 AccountLedger 的 pending 状态；归因符号和 bad_link 仍主要在结果外构造错误值比较。不能据此证明生产三个 Broker 的关键错误都被对应验收杀死。

修复要求：冻结人工费用/账户 oracle，不调用生产实现生成期望；同一独立断言在正常基线通过、施加目标 mutant 后失败。基线本身错误时整个变异运行报 baseline failure/ERROR，不计杀死。保存目标位置、实际变更和失败断言，而不是仅返回两个数不相等。

## F4 · P2 · 原 R8 未关闭：未知期初持仓被强制分配给已知策略

位置：`quantide/service/attribution_facts.py:230–241`。

`_owners_at()` 将已知成交净股数按 target/total 放大到全部实际持仓。当已有来源未知的持仓，又发生一笔有来源的买入，就把未知部分也分给后者。

复现：期初有来源未知的 A 100 股，另有现金 1000；known 策略再买 100 股@10。次日 A 从 10 涨到 11，实际贡献应为 unassigned=100、known=100。当前输出 known=200、unassigned=0。

这是“不能猜测分摊”的同一问题，不是新归因模型需求。仅为同日两个已知买入写回归，覆盖不了期初存量、转入持仓、拆股后新买入等路径。

修复要求：持久维护已知来源的持仓数量，无法证明来源的差额保留 unassigned；公司行为按当时来源持仓变换，禁止按已知净成交比例补齐未知份额。新增未知+已知混合、分批买卖、拆股后的来源对账。

## F5 · P2 · 原 R12 未关闭：失败、报错、跳过的 JUnit 被当成 covered

位置：`quantide/audit/acceptance.py:279–284,304–312`。

解析 JUnit 时只收集 testcase 对应文件名，不读取 failure/error/skipped；同一测试文件中任意一个 testcase 出现，就满足该文件的全部证据要求。

独立复现：分别提供只有一个 testcase 的 XML，其内容为 failure、error 或 skipped，classname 指向 test_synthetic，甚至 name 为不存在的 not_real。三种情况下 AC-4005 均被计为 covered。

当前独立 `scripts.check_test_results` 会拒绝不合格 JUnit，但 matrix 接口没有使用同等约束，不能要求每个消费者自行猜到额外前置条件。本次实际 acceptance XML 全部通过；本 finding 不声称本轮真实测试失败或已经绕过 GitHub 发布规则。

修复要求：证据映射到具体 nodeid/参数化实例或明确的用例组，逐项核对实际执行成功；failure/error/skip/xfail 不得计覆盖。结果应绑定 ref、配置与 fixture 版本；只运行文件中的一个无关用例，不能使整项 AC 完成。新增失败/跳过/不存在用例与部分执行反例。

## 验证与边界

| 检查 | 本轮结果 |
| --- | --- |
| 全量 unit | 4939 passed、3 skipped；覆盖率工具整数汇总 83% |
| 现有 release_gate 选择集 | 28 passed、276 deselected；JUnit gate 非空且无 skip/xfail |
| mypy | 359 个源文件通过 |
| Ruff/行宽、认知复杂度、重复/大小 | 全部通过 |
| mkdocs 严格构建 | 通过，输出在外部 tmp |
| 目录布局及 git diff --check | 通过，未新增 checkout 运行产物 |

没有执行三平台安装、远端部署或发布。有限用例全绿不等于这五项反例已满足 AC；也不等于整个 001 的尚缺合同可以关闭。

复现脚本与原始输出：`/tmp/millionaire-ce/audit001-r5-repro.py`、`audit001-r5-repro-results.json`；测试和工具日志为同目录 `audit001-r5-*`。全部使用临时账户配置/数据库/行情副本，不修改真实账户或仓库 fixture。

建议下一轮优先关闭 F1/F2 的真实时序与原子发布，再关闭 F3～F5 的独立证据和来源归属；沿用本报告编号与反例逐项反馈，不要仅报告“12 项全部完成”。
