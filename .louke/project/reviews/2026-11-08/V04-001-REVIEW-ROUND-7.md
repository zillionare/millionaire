# v0.4-001 第七轮复核：参数化验收证据

日期：2026-11-08。对象：基于 `b790c71` 的当前未提交工作区，重点复核第六轮唯一未关闭项 F5-R。没有修改实施代码、fixture、需求或预算，没有提交、部署、发布。

## 结论

**第六轮 F5-R 可以关闭，本轮修复审查通过。** 本轮审查范围内未发现新的可复现问题。该结论针对这次返修，不替代整个 v0.4-001 的完整 FR/AC 签收、三平台安装或同 ref 发布验收。

## 实现复核

- JUnit 身份保留完整函数名、类身份与参数 ID，不再按函数基本名合并实例。
- 预期集合来自真实 pytest `--collect-only`，并按 AC 的证据范围形成 manifest；不再用源码正则推测参数化实例。
- 缺失任何必需 nodeid 时保持 mapped；普通失败/error、skip/xfail 不计成功。
- 多份结果合并采用最差结果优先，先 skip 后 pass 不会被洗成成功。
- 无结果或无预期集合时不默认 covered。CLI 没有显式 manifest 时实际调用当前 checkout 的 collection；本轮也验证了这个默认入口。

## 独立复现结果

复用第六轮的真实 pytest 反例，分别执行完整与缺失负向参数两种情况，并用新收集的同一预期集合判定：

| 场景 | pytest 结果 | AC-4004 | AC-4005 |
| --- | --- | --- | --- |
| synthetic + statistics 完整执行 | 14 passed | covered | covered |
| deselect `test_pearson_power_recovers_positive_and_negative_signals[-0.25]` | 13 passed、1 deselected | mapped | mapped |

实际 manifest 保留 `[-0.25]` 和 `[0.25]` 两个独立 nodeid；AC-4004 预期 14 个实例，AC-4005 预期 8 个实例。

CLI 不提供 `--manifest`、只输入部分执行的 XML 时，同样得到 AC-4004/4005=mapped、release_ready=false，并以非零状态结束。不是只在测试手工传入的 manifest 下有效。

新增定向测试也覆盖了部分类执行、未知用例、失败/error/skip、参数 skip 与 pass 混合，以及跨报告 skip 不能被后续 pass 覆盖。

## 验证

| 检查 | 结果 |
| --- | --- |
| 验收矩阵定向测试 | 7 passed |
| 完整/部分参数化独立复现 | 符合预期，见上表 |
| 全量 unit | 4949 passed、3 skipped；覆盖率工具整数汇总 83% |
| 现有 release_gate 选择集 | 29 passed、276 deselected；JUnit gate 非空且无 skip/xfail |
| mypy | 360 个源文件通过 |
| Ruff/行宽、认知复杂度、重复/大小 | 全部通过 |
| mkdocs 严格构建 | 通过，产物在外部 tmp |
| 目录布局与 git diff --check | 通过，未新增 checkout 运行产物 |

生成物在 `/tmp/millionaire-ce/audit001-r7-*`：`repro.py`/`repro-results.json` 保存独立收集与判定；`ic-full.*`/`ic-partial.*` 为真实 pytest 结果；`cli-partial.json` 和日志验证自动收集入口。全部使用临时配置/输出，不修改真实用户数据。

建议关闭第六轮这项返修反馈，后续整版完成声明仍按 completion-guide、实际 AC 证据和三平台执行结果确认，不把本轮局部审查通过当作自动发布授权。
