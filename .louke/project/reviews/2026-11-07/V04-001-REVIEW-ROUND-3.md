# v0.4-001 第三轮复核

日期：2026-11-07。审查基于 `b790c71` 的当前未提交工作区，不仅是已提交 HEAD。
本轮不修改实施代码、不调整需求，仅新增审查及完成指导文档。

## 结论

第二轮 F1/F2/F4/F5/F6 的具体反例已修复；F3 的数据版本失效问题有进展，但尚未完整关闭，并引入不同窗口相互失效的问题。建议继续修正下列 G1～G3，再推进剩余里程碑；不能将“本轮修复完成”与“整个 v0.4-001 完成”等同。

完整剩余工作及建议验收顺序见 [`completion-guide.md`](../../specs/v0.4-001-strategy-audit/completion-guide.md)。这是实施指导，不替代或缩减原 spec/acceptance。

## 第二轮关闭状态

| 第二轮项 | 本轮复核 |
| --- | --- |
| F1：预热全空、空输出、实际无变更仍 PASS | 原反例均改为 INCONCLUSIVE；增加 changed_cells/compared_rows/effective_values 证据。混合结果优先级还有 G3。 |
| F2：显式旧 spec 冒用 | 生成实际执行 spec 后比较身份、源码、输入、配置、周期、时区、种子等字段；改变输入的原反例被 ValueError 拒绝。此项原反例关闭，不代表任意策略、模型和缓存审计已完成。 |
| F3：数据修订不失效/旧输入覆盖新结果 | 新增 source token、manifest revision、旧 token 拒绝及运行后补排队；测试可检测同截止日的日线文件更新。但不同窗口混入全局 manifest，且未覆盖全部输入来源，见 G1/G2。 |
| F4：日历版本碰撞 | 对完整日期序列做摘要；相同首尾和长度、不同内部日期的反例现在得到不同版本。关闭该内容摘要问题；自动观察日历修订属于 G2。 |
| F5：下午可用用于当日开盘 | `_available_by_entry` 按 open=09:30/close=15:00 比较 datetime，并转换配置时区；date-only 采取更保守的前一日约束。原 14:00 因子参与开盘案例有效配对从 3 变为 0。 |
| F6：质量门禁失败 | Ruff、认知复杂度、重复/大小扫描全部通过，未观察到预算被放宽。 |
| 启动只按日期判断积压 | `_needs_backfill` 改为检查完整 tracking_view 状态，新增 interrupted 快照补查测试；租约、检查点和受控重启仍未完整交付。 |
| 数据维护触发 | `maintenance.maintain_data()` 在完整维护成功后调用 trigger_refresh_all；这个路径已接入。不能据此宣称所有数据维护入口都有持久事件和丢失事件恢复。 |

## G1 · P1：全局 manifest 混入研究窗口，正常不同方案互相标陈旧

位置：`quantide/service/factor_tracking.py:321–348,390–400`，以及 `_build_snapshot()` 中 panel/calendar 指纹的生成。

`market-manifest.json` 只有一份。它用 data_hash、universe_hash、calendar_version 判断“市场输入发生变更”，但这些字段来自按 profile.lookback 截取后的面板和日历。3 年与 1 年研究使用相同原始市场版本，也必然得到不同面板/日历指纹。

最小复现：

1. 固定 source_token=(1, 2026-11-06)，为 bias_5 发布 3 年面板结果，状态 normal。
2. 为另一个因子保存 1 年方案并发布相同来源版本的 1 年面板结果。
3. 无任何市场更新，bias_5 状态变成 stale_data，后发布的因子为 normal。

每次重算不同窗口都可推进全局 revision，导致其他窗口再次陈旧，启动补查也可能反复触发。这不满足 AC-4314/4318 的失效和恢复合同。

建议：分开全局原始来源 revision 与“该研究派生面板”的指纹。来源版本只在原始行情/日历/证券池等提交变更时推进；窗口、预热、因子依赖和研究参数进入任务缓存键。不要把每个窗口的计算结果写成全局市场事实。回归测试必须同时启用至少两个窗口，全部完成后均 normal，重复触发不推进来源 revision。

## G2 · P1：自动失效只观察日线文件，日历/证券池/依赖独立修订仍不可见

位置：`quantide/service/factor_tracking.py:261–294,352–366,381–404`。

当前 source token 只读取 daily_bars 的末日和日线 parquet 最大 mtime；页面比较该 token 或最近一次计算产生的 manifest revision。日历、证券池及独立计算依赖没有提供当前来源版本。

因此，日线文件不变、仅修订日历或证券池时：在后台尚未另一次重算前，来源 token 和 manifest 都不变，已有快照仍 normal。新 calendar_version/universe_hash 只有重算后才被计算，不能承担触发本次重算的职责。dependency_hash 目前也只由 FACTOR_VERSION 与手动 STATISTICS_VERSION 合成，没有完整绑定其他计算依赖。

这是第二轮 F3 未关闭的部分，违反 AC-4314 对“最新日期相同但日历/证券池/依赖变更”的明确要求。`docs/factor-analysis.md:20–22` 现在声称日历内容变化会自动标陈旧并排队，超出当前已接通的行为。

建议：在原始数据维护提交点发布可持久查询的各来源版本，页面仅查轻量版本/manifest，任务读取一致的输入快照并绑定依赖版本。来源不可知时不能悄悄当作已验证最新。补“只改日历”“只改证券池”“只改计算依赖”“来源版本读取失败”等测试。全市场 hash 不应在每个页面请求中重算。

## G3 · P2：混合扰动结果中，明确 FAIL 被无证据结果降为 INCONCLUSIVE

位置：`quantide/audit/checks.py:45–77`。

先检查 without_evidence 并立即返回，之后才查失败，违背接口合同 FAIL 优先于 INCONCLUSIVE。

独立复现：三行 x=0，pipeline 故意把全样本 x 均值写进历史 signal；cutoff 设在第二行，模式为 zero 和 extreme。zero 无实际变更；extreme 有实际变更且检测到历史输出差异。底层结果明确含失败位置，但适配器汇总为 INCONCLUSIVE，丢失前视错误的首差异。

这不会变成 PASS，但会把已证明错误误报成“证据不足”，影响用户/AI 的修复方向。

建议：先识别有真实比较证据且摘要不一致的失败；只要存在即 FAIL 并保留首次差异。没有明确失败时才把无有效扰动/无历史输出合为 INCONCLUSIVE。不要直接把“没有未来行”的 passed=False 当成真实失败。测试 FAIL+无变更、FAIL+空证据、全部无证据三类组合。

## 验证

| 检查 | 本轮结果 |
| --- | --- |
| 定向功能测试 | 94 passed |
| 全量 unit | 4862 passed，3 skipped；覆盖率工具整数汇总 83% |
| 现有 release_gate 验收选择集 | 20 passed，276 deselected；JUnit gate 确认非空、无 skip/xfail |
| mypy | 341 个源文件通过 |
| Ruff/行宽、认知复杂度、重复/大小 | 全部通过 |
| mkdocs 严格构建 | 通过，输出到外部临时目录 |

这些不是三平台安装验收或整个 001 的 40 项新增 AC 全部验收。没有部署、发布或提交工作区代码。

独立复现：`/tmp/millionaire-ce/audit001-r3-repro.py` 和 `audit001-r3-repro-results.json`。该脚本也核查了“相同内容、source token 推进后的重算”：当前快照和 revision 正常更新，不应误报成幂等刷新永久陈旧。原始日志及文档构建输出在同目录 `audit001-r3-*`，不提交生成物。
