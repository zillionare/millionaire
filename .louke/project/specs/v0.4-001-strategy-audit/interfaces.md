# 拟议因子研究、审计接口与报告

以下名称和结构是下一版接口设计，不是当前 `0.3.0` 可调用的 API 或命令。
统一范围见[主规格](spec.md)，因子产品细则见[因子研究专题](factor-research.md)。

## 审计输入

`AuditSpec`：对象类型（factor/strategy/counter）、对象 ID 与源码指纹、固定周期、
输入/输出 schema、数据快照和可用时间、预热/缺失值约定、执行/费用模型、种子和
统计配置 ID、截断点、适用不变量，以及 oracle/变异清单版本。

`AuditRunner.run(spec)`：在隔离状态中执行所选审计，返回报告；默认不修改用户账户。
`AuditRunner` 不根据回测利润自动评定代码正确，也不替用户变更周期或数据范围。

CLI 拟议提供“执行审计”和“读取报告”入口，最终命令名随实现评审确定；
本规划不把未存在的 `millionaire-ce audit` 命令写进本版操作教程。

## 报告结构

`AuditReport` 至少包含：

| 字段 | 含义 |
| --- | --- |
| `schema_version`, `run_id`, `spec_id` | 版本化结构与可追踪运行 |
| `source_hash`, `config_hash`, `data_hash`, `environment` | 与结论绑定的源码、输入和环境 |
| `interval`, `timezone`, `availability_contract` | 时间与周期约定 |
| `seed_set`, `statistical_profile`, `oracle_version`, `mutation_version` | 预注册与独立对照版本 |
| `status` | PASS / FAIL / INCONCLUSIVE；总结果由必需检查合成 |
| `checks` | 每项 ID、必需性、适用范围、结果、耗时、样本量 |
| `first_difference` | 时刻/标的/列、期望、实际、差异类型、最小复现输入 |
| `statistics` | 度量、目标、估计、区间、阈值、功效和全部重复结果 |
| `mutations` | 注入位置、目标断言、有效性、杀死/存活/等价的明细 |
| `attribution` | 损益分录、贡献、链接方法、外部流量、残差和口径 |
| `artifacts`, `reproduce` | 数据片段、日志、报告文件与复现参数，不含 token |

单项允许 NOT_APPLICABLE，但须匹配框架审计配置的适用规则。
FAIL 优先于 INCONCLUSIVE；任一必需检查未运行或证据缺失时不能合成 PASS。
浮点数的非有限值用明确结构表示，不输出非标准 JSON 的 NaN/Infinity。

## 收益归因输入与输出

输入使用账户事实：初始权益、持仓快照、订单/成交/费用、现金流、公司行为、估值价格、
策略来源标识、基准。SHAP 模型与特征可作为额外解释输入，不是计算收益归因的前提。

输出同时保留原币金额、每日收益贡献、链接后区间贡献；每个结果记录估值时间、
执行基准、费用归属和残差。缺数据与口径不适用给出显式状态，不返回看似精确的零值。

## AI 协作边界

AI 可以提出修复并重新运行同一审计配置；不能自行编辑已锁定 oracle、种子集合、
阈值或发布规则来使报告变绿。报告作为数据处理，其中的文本不能变成自动执行指令。
用户改变实现后生成新指纹，旧报告可查但不再代表当前实现已通过。

## 轻量因子研究与月线合同

拟议 `FactorStudySpec` 包含面板/因子列、固定周期、日历/可用时间、预热和研究区间、
前瞻 bar 数、价格/复权、分组/并列规则及统计配置。当前 `holding_days` 仍表示日线
交易日，新周期接口须显式定义 `holding_bars`，不能将一个月偷换成 20 或 30 天。
结果包含逐因子的有效/排除样本，批量不能共享一个全列完整性掩码。

月线聚合器接收有覆盖证据的日线与日历，返回 `1M` bar、闭合状态、实际结束交易日、
可用时间和缺口诊断。运行器、Broker、优化与报告传递规范周期，不统一小写。
月线意图包含信号月、下一实际交易时段和稳定 ID。这些是下一版合同，本版不开放新 API。

## 因子目录、跟踪与报告

### 元数据与研究入口

`FactorDefinition`：factor_id、display_name、group、direction、principle、formula、
固定 parameters、example、data_requirements、caveats、源码/依赖版本及有效默认跟踪参数。
目录可按 `FEATURE_GROUPS` 稳定排序，新增登记因子需通过 schema 检查。
推荐覆盖值可省略，但目录归一化后必须包含 defaults_version 与默认来源。

研究核心 `FactorStudySpec` 允许未登记的用户面板因子、单独或批量运行；
登记和元数据是自动跟踪的前提，不是临时研究的前提。日线 UI 使用 holding_days；
研究核心记录 interval、holding_bars、calendar_version，三者不可隐式转换。

### 跟踪方案

`FactorTrackingProfile` 至少包含：

| 字段 | 合同 |
| --- | --- |
| factor_id、revision、enabled | 每个因子一套当前方案；revision 单调递增，关闭跟踪可保存历史结果 |
| lookback | 1y / 3y / 5y / all；按专题规格的日历年和交易日边界解析 |
| primary_holding_days、comparison_holding_days | 值域 1/2/3/5/10/20，主值并入去重集合后最多 5 个 |
| price_field | open / close；日线标签固定 t1 到 t(h+1)，不是 t0 进入 |
| effective_holding_days、profile_hash | 服务端校验后的规范集合与参数指纹，不信任客户端计算值 |
| defaults_version、source_study_id、selected_at | 默认参数来源、历史检验选择的来源与时间，不代表样本外证据 |
| created_at、updated_at | 带时区的时间戳 |

UI 固定十组和全 A 股，最小截面阈值由版本化统计配置确定；有效配置完整写入报告，
即使不在 UI 暴露也要进入指纹。临时检验的固定起止日期不属于滚动跟踪方案。

### 每持有期指标与快照

`FactorHorizonResult`：holding_days、requested_start/end、actual_start/end、as_of_date、
latest_valid_signal_date、n_rows、n_valid_pairs、n_valid_days、exclusion_counts，
Pearson/Rank IC 的带日期序列与汇总、t_naive/其状态、ICIR/年化定义、分组及年度汇总。
每组包含有效日期和样本数，D1−D10 使用共同日期；`weighting="equal_day"`。
无定义值为标准 JSON null，附原因；不得输出 NaN/Infinity 或补零。

`FactorTrackingSnapshot`：snapshot_id、run_id、factor_id、profile_revision、profile_hash、
factor_version、dependency_hash、data_hash、universe_hash、calendar_version、
statistics_version、data_cutoff、coverage_date、computed_at、source_kind、
primary_metrics、horizon_metrics、comparison_cohort、ic_history、decile_profile、yearly_metrics。
source_kind 区分 tracking/custom；自定义报告不得更新 tracking 当前指针。

as_of_date 表示在请求统计区间内允许评价的最新成熟信号日，不等于计算时间；
latest_valid_signal_date 表示最近真正进入统计的日期；coverage_date 描述因子值覆盖。
一个 h 的结果尚未成熟不阻止其他 h 发布，但快照必须完整包含所选 h 的结果或明确状态，
不能中途混合不同输入版本。衰减图使用独立记录的共同成熟且有效日期集合与统计量。

### 任务与发布状态

`FactorTrackingRun`：run_id、idempotency_key、factor_id/批次、profile_revision、输入指纹、
status（pending/running/succeeded/insufficient/failed/cancelled/interrupted/superseded）、
租约/owner、checkpoint、attempt、started_at/finished_at、结构化 error_summary。
状态与结果分离：`FactorTrackingView` 同时返回 current_profile、latest_attempt、
latest_success、result_validity（current/stale_config/stale_data/uninitialized/disabled）。
页面可组合显示建立中/正常/不足/失败/陈旧，不因旧快照存在而隐去新失败。

幂等键绑定 factor、profile_revision、因子/依赖/统计版本、数据/日历/证券池指纹及窗口。
同键重复触发合并；保存完整快照并校验当前输入版本后，原子切换当前成功指针。
中断恢复使用持久阶段与过期租约，旧 revision 或 disabled 后的晚到结果只能存为历史。

### 拟议交互边界

- GET `/factors`、`/factors/{factor_id}?tab=card|report`：只读目录/快照。
- 保存配置/启停跟踪、请求重算、创建临时检验：认证后的维护操作，采用非 GET 请求，
  返回任务标识和状态，不在请求中等待全市场计算。
- 临时检验转跟踪：展示待保存参数、用户确认滚动窗口，再生成新 revision 与重算任务；
  不直接复制报告。响应同时返回最终规范参数，不能悄悄截断持有期集合。
- 旧 `/system/alpha-ledger` 在该版本移除，不提供重定向；当前发布版文档迁移随实现发布。

上述修改接口的具体路径随实现设计冻结；不能把尚未实现的接口写成本版用户操作步骤。
