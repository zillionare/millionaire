# v0.4-001 第四轮代码审查

日期：2026-11-08。范围：基于 `b790c71` 的当前未提交工作区，包含新任务队列、来源版本、归因、合成检验、变异目录、月线及验收声明。没有修改生产代码、fixture 或规格，没有提交、部署、发布。

## 结论

**请求修改，当前不宜合并为完整 v0.4-001，也不是仅剩三平台 CI 验收。** 上一轮 G1（窗口混入全局来源版本）、G2（独立来源失效）和 G3（FAIL 优先级）的原反例已有针对性修复及测试。但本次扩展模块存在可复现的实际运行错误，部分验收证据只是单独函数/静态路径，不能支持“39/40 covered”的产品完成声明。

以下 12 项是本轮集中反馈。P1 是合并/发布前应修的正确性问题；P2 也是本 spec 的工作，不表示可以删除或直接当作验收通过。

## R1 · P1：归因没有独立对账实际期末权益，遗漏事实仍显示零残差

位置：`quantide/service/attribution_facts.py:130–178,194–233`。

虽然新增 AccountFacts/FactSnapshot，实际计算仍把 `_period()` 传入的事实交给 `attribute_period` 重建期末权益；end.equity、end.cash、end.positions 没被用来核对重建结果。报告 residual 是数学 oracle 的内部残差，不是与账户观测的差额。

复现：账户事实从现金/权益 1000 变为 995，缺失了 5 元费用事实。结果为 `status=OK, end_equity=1000, delta_equity=0, residual=0`，实际期末为 995、变动为 -5。

影响：核心“缺少费用/分红等事件可被残差发现”仍不成立，直接违反 FR-4007/AC-4010。这是前几轮独立对账要求的未关闭部分，不是增加新范围。

修复：使用独立的期末权益/现金/持仓对账，残差包含事实解释与观测之间的差异；保留数学 oracle 的内部检查，但不能用其重建值代替真实账户事实。增加漏费用、漏成交、漏分红和持仓不符负例。当前 e2e 的 `test_account_fact_attribution_reconciles` 甚至给了无成交却新增 100 股的快照，仍仅断言 residual=0，应改成检测缺失事实。

## R2 · P1：月线历史把形成中月份当成闭合月份

位置：`quantide/service/monthly_bars.py:82–87,139–150,266–273`；`quantide/strategies/example/monthly_ma.py:64–73`。

月末从“传入日历中该月最后一天”推断；`monthly_history()` 先过滤日历到 end，策略 on_bar 也只传截至当天的 days。这样形成中的月最后一条行情恰好等于截断日历的“月末”，就被标 closed。

复现：完整日历含 2024-09-02/13/30，行情只到 09-13。直接用完整日历聚合得到 forming=1、closed=0；调用生产 `monthly_history(..., end=09-13, calendar=完整日历)`，却返回 09-13 的 `closed=True`。

修复：保留足够的权威未来日历以确定实际月末，行情读取截止与月末身份分开；月末还须满足价格/依赖真实 available_at。增加月中 history、月末盘前/盘后和未来数据扰动测试。当前仅检末日是否存在也不足以证明整月数据完整或正确复权，月内缺数/拆股须有独立合同与 oracle。

## R3 · P1：月线订单意图在不同账户/回测间共享，造成漏单或串单

位置：`quantide/service/monthly_intents.py:118–122`；`quantide/strategies/example/monthly_ma.py:54,83–101,129–131`。

所有实例默认使用同一持久文件 `monthly-intents.json`；key 只有资产、信号日和方向，没有账户/runtime、策略版本或运行身份。`_execute_due()` 也不按当前实例过滤意图。

复现：账户 one 完成 `A:2024-01-31:buy` 后，账户 two 的同一信号 enqueue 返回 False。重复回测、不同优化试验或转入 Paper 也会受已完成键影响；另一个实例还可能执行全局 pending 中原本属于其他账户的意图。

修复：意图必须绑定账户/运行、策略身份、版本与规范参数；回测/优化试验有独立生命周期，不能消费真实 Paper 意图。broker client_order_id 使用同一有命名空间的稳定身份。新增两个账户、重复回测、并行优化及跨实例恢复负例。

## R4 · P1：月线没有接通实际运行/恢复入口；分钟与月份仍有混淆

位置：`quantide/service/strategy_runtime.py:190–202,595–618,939–956`；`quantide/service/runner.py:123–135`。

BacktestRunner 新增 1M 接受，但 StrategyRuntimeManager 的创建、恢复/校验仍限定 `1d/30m`，并统一 lower。实际校验 `interval='1M'` 抛出“无法验证持久化策略周期: '1m'”。因此应用运行链和转仿真/恢复不是已交付的月线能力。

反方向也有问题：`validate_strategy_interval(MonthlyMAStrategy, {'bar_interval':'1m'}, FrameType.MONTH)` 返回 `1M`，因为 supplied_text.upper() 把分钟覆盖当成月份。示例构造函数自身另有拒绝，不等于通用验证器正确。

当前所谓月线三路径 e2e 手工构造两个 intent，在三天普通行情中直接调用 execute_intent；没有跑 MonthlyMAStrategy、月线时钟或跨月策略恢复，无法覆盖此缺口。

修复：从真实应用入口贯通创建、持久化、时钟、三个 Broker、优化和报告，精确保留 1M/1m；验收须运行真实月线类而非绕开策略的手工 intent。月末先提交未来 order_time 也须验证实际 Broker 不提前推进资金/成交时钟，不能仅靠未来订单时间代表真正 next_open 调度。

## R5 · P1：自定义检验 spawn 子进程没有初始化数据层，真实任务失败

位置：`quantide/service/factor_study_worker.py:39–64`；`quantide/service/process_runner.py:82–103`。

子进程使用 spawn，只导入 `_study_target` 并直接 run_custom_study；没有传入有效数据配置快照，也没有 init_data/连接 daily_bars 和日历。父进程的单例连接不会被 spawn 继承。

复现：父进程连接外部临时 daily.parquet，成功读到两行行情；用真实 run_isolated 执行 `_study_target`，子进程仍从占位 `/dev/null` 读取，返回 failed：`OSError: Operation not supported by device (os error 19)`。

现有 task 成功测试 monkeypatch 了 run_isolated，不能证明真实子进程能计算。

修复：持久任务保存并传递所选数据 home/配置和输入版本，在子进程显式初始化只读数据层、关闭资源；不要误连用户账户数据库或假定父进程状态已继承。增加不 mock run_isolated 的本地完整任务集成测试，包含失败、取消及成功输出。

## R6 · P1：失去任务所有权或停止 worker 后，旧执行仍可继续写结果

位置：`quantide/service/factor_runs.py:314–321,500–521,581–586`；`factor_study_worker.py:75`；`factor_tracking.py:549–580`。

heartbeat 在 touch 失败后仅 return，没有设置 cancel；set_result 不要求 owner、RUNNING 或有效租约；跟踪快照发布没有与队列 lease/owner 的 fencing 校验联动。stop 只设置“不再领取”的 stop Event 并 join，不通知正在执行的 cancel Event。

独立复现：旧任务被 superseded，heartbeat 已停止，但 cancel_signalled=False；旧 run 的 set_result 仍返回 True。另一个阻塞任务在 stop(timeout=.02) 返回后仍活着、状态 running，释放后正常写成 succeeded，executor 从未看到取消。

修复：丢失租约/所有权立即取消；结果写入和当前快照指针发布需要 owner+generation/CAS 的 fencing，不能仅保护最终 finish 状态。停止时通知全部活动任务并等待受控退出/终止；不可中断的重计算需隔离 worker，不能只设线程计时器。增加“旧 owner 晚到写入必须被拒绝”和“stop 后没有发布”的真实竞争测试。

## R7 · P1：部分“关键变异被杀死”实际没有施加对应变异

位置：`quantide/audit/mutations.py:115–162,165–180`。

- t_plus_one_unlock 调用正常 AccountLedger 并在同日卖出被正常拒绝时计 KILLED，没有真的让被测执行器提前解锁。
- period_override 调用正常周期拒绝逻辑，被拒绝就计 KILLED，没有植入允许覆盖的实现。
- duplicate_cost 传入两笔本来就不同的成交/费用，正确计算为 -10 即计 KILLED，没有检测同一事实被错误重复扣减。
- fee_omission 比较两个不同输入的正常结果，没有把生产柜台漏费用后的实际账户事实与独立 oracle 对拍。

这些可以保留为普通负例/数学控制，但不是 FR-4006 要求的目标变异执行及杀死证据。未来 shift 等手写错误 pipeline 确有检测价值，也不能证明 T+1/费用/幂等的真实执行路径变异已覆盖。涨跌停绕过、重复下单、撤单丢部分成交等关键目录也没有完整交付。

修复：对明确受审实现施加可撤销的代码/行为变异，运行独立维护的目标断言，记录位置、变异差异、命令、断言失败和 AC；正常基线必须先过。同一 testcase 在正常实现通过、在对应 mutant 失败，才能计杀死；错误条件不能仅写在 MutationCase.description。

## R8 · P2：多策略持有同一证券时，全部历史贡献被分给最后一个策略

位置：`quantide/service/attribution_facts.py:182–190`。

mapping 用 asset→最后一笔交易 strategy 覆盖，没有逐时段/批次/来源持仓事实。复现：策略 first 买 100 股@10，second 次日买 100 股@11，期末价 12；应为 first=200、second=100，当前全分为 second=300。

修复：使用稳定成交来源及按时点归属的持仓账本；来源缺失列 unassigned，不把后来交易来源倒灌给历史收益。分开原币与链接收益贡献，验证合计对账。

## R9 · P2：归因基准不跟随研究区间过滤，也未绑定报告指纹

位置：`quantide/service/attribution_facts.py:73–112,246–271`。

periods 使用 start/end 过滤后的 snapshots，benchmark 却使用 facts 全部 snapshots 日期。4 个快照只请求后 3 个时，strict zip 抛 ValueError：第二个参数更长。另一个复现是只改变 benchmark，AccountFacts.fingerprint 完全相同。

修复：选定区间及事件分段只生成一份对齐的期间索引，策略和基准使用同一索引；指纹绑定所选区间、基准数据/口径和策略来源。当前 `_period` 仅按日期求和 flows，也没有实现文档宣称的事件内估值分段；缺足够事件时间/估值时必须明确不适用，不能自动称 TWR 已完成。

## R10 · P2：任务 scope 相互干扰，过期任务只标中断而未恢复执行

位置：`quantide/service/factor_runs.py:188–209,351–364,478–486`。

`_supersede` 只看 factor_ids，不看任务 scope。复现：为 bias_5 排队自定义 study，再排队同因子自动跟踪，study 被标 superseded。两者本应独立，自动更新不应取消用户固定区间研究。

另外，recover/claim 把过期 running 改为终态 interrupted，没有按检查点重排。复现：attempt=1、max_attempts=2 的任务过期后，next claim 得不到该任务。跟踪启动另有粗粒度补查，不能据此声称自定义任务及服务运行期间的 worker 故障已可恢复。

修复：定义同类任务的替代关系，study 与 tracking 隔离；过期租约按策略重排/重跑合法阶段，记录恢复链与预算，避免永久挂起。真实终止子进程/owner 后重启并完成同一业务任务，不能只断言 status=interrupted。

## R11 · P2：合成目标 IC 在实际收益标签中改变，声明种子集未全部执行

位置：`quantide/audit/synthetic.py:99–130,136–147,163–195,199–234`。

目标 Pearson IC 植入在正态变量 forward 上，但生产标签使用 `exp(forward)-1`。Pearson 相关不在这个非线性转换下保持，直接恢复与真实 horizon 检验并非同一统计目标。

复现：target=.5、500 日期、120 资产、种子 3：直接 signal_recovery 的 IC≈.49754/RECOVERED，study_synthetic_signal 的 IC≈.39771/FAILED。不是生产研究内核出错，而是合成输入目标口径不同。

此外配置 seeds=(3,999) 时仍只实际执行 seeds[0]，返回 profile 却包含两个种子。RandomControl.seeds 同样不是完整重复执行的证据。required_days/区间的有效样本量模型没有与“截面相关的跨日均值”校准，不能只凭天数公式声称目标功效已验证。

修复：先明确实际简单/对数收益和 Pearson/Rank 度量，再生成满足该目标的市场；每个预注册种子都运行并保存结果；用独立模拟校准零分布、区间覆盖率及检验功效，修复后不得通过放宽阈值抹平这个反例。

## R12 · P2：39/40 covered 是静态标签，不是对应 AC 的验收证据

位置：`quantide/audit/acceptance.py:12–31,147–151,261–269`；`docs/strategy-audit.md` 的完成声明。

默认 status='covered'，只要 evidence 字符串元组非空就视为 release_ready；不检查路径、测试是否实际执行或是否验证该 AC。AC-4302 引用的 test_alpha_ledger.py 已被删除，仍被计入 covered。月线恢复、任务恢复、费用变异等也因列了测试文件而被标覆盖，但本轮反例证明核心行为尚未验收。

修复：区分“映射已登记”和“行为已验证”；维护 AC→具体 nodeid/命令/fixture 版本→同 ref 运行结果的关系，并检查证据存在。完整需求未覆盖时标 partial/pending，不能称仅剩 AC-4014。无需每次打印矩阵都重跑所有测试，但完成声明必须来自可核验的执行产物，而非默认常量。

## 尚不能从文件存在推断完成的合同

- 当前 factor audit 入口仍主要审计固定 compute_alpha_features；完整训练标签/模型、业务 Bool 状态、冷/热缓存与策略信号的适配和验收未有充分证据。手写错误小 pipeline 不等于已接通真实训练/缓存路径。
- facts_from_db 没有实际接通基准、现金流/公司行为的完整事实；facts_from_counter_state 只返回单快照，不能完成多期柜台归因。页面中出现归因入口不代表三来源最低发布范围已完成。
- 月线聚合不应直接用未复权价格做跨拆股均线；复权、月内缺数/停牌及真实账户规则仍需独立对拍。新三路径测试是订单提交辅助函数对拍，尚不是同一月线策略全链验收。
- RunBudget 没有完整面板/内存预算；tracking 的长计算仍在协作线程里运行，超时不能保证及时终止。完整统计与有效变异的同 ref 发布硬门禁仍需补证。

## 验证结果

| 检查 | 本轮结果 |
| --- | --- |
| 全量 unit | 4918 passed、3 skipped；覆盖率工具整数汇总 83% |
| 现有 release_gate 选择集 | 27 passed、276 deselected；JUnit gate 非空且无 skip/xfail |
| mypy | 357 个源文件通过 |
| Ruff/行宽、复杂度、重复/大小 | 全部通过 |
| mkdocs 严格构建 | 通过，输出位于外部临时目录 |
| 目录布局与 git diff --check | 通过；未新增 checkout 运行产物 |

全绿说明现有用例未捕获这些反例，不表示问题不存在。本次没有执行三平台安装或远端部署。

复现脚本与原始结果位于 `/tmp/millionaire-ce/audit001-r4-repro.py`、`audit001-r4-repro-results.json`、`audit001-r4-queue-repro.py`、`audit001-r4-queue-results.json`；日志为同目录 `audit001-r4-*`。复现均使用临时配置/数据，不写入真实账户；父进程行情样本写入临时文件，仓库 fixture 不作修改。

## 建议下一步

先修 R1～R7 的事实对账、真实执行与任务所有权问题，并把本报告反例转成持久回归；同时修正验收矩阵与产品声明。随后处理 R8～R11，按原 completion-guide 的 AC 闭环核验缺口。每个阶段提交可审查的代码和行为测试，避免再次用局部 mock、空样本或静态标签代替整体验收。
