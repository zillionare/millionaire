# v0.4-001 第六轮复核

日期：2026-11-08。范围：基于 `b790c71` 的当前工作区，对第五轮 F1～F5 的修复逐项复测并检查相关执行边界。本次只新增审查文档，没有修改实施代码、测试 fixture、需求或预算，没有提交、部署、发布。

## 结论

**第五轮 F1～F4 的原反例可以关闭；F5 仍有一项 P2 参数化证据问题，尚不能全部关闭第五轮反馈。** 本轮在所审修复范围内未复现新的 P1。关闭这些反馈本身不等于整个 v0.4-001 的全部 FR/AC 或三平台发布验收已经完成。

## 关闭状态

| 第五轮项 | 本轮结果 |
| --- | --- |
| F1：月线信号回调提前产生未来成交 | 已修复原反例。信号阶段只 enqueue；Runner 增加次日开盘执行事件。独立真实 Runner 复现：01-31 09:30 无信号，15:00 有 1 个待执行意图、现金仍 10000；02-01 09:30 才成交，现金为 10。新增开盘前信号保护也覆盖了回测从月末当日开始的边界。 |
| F2：撤销租约后旧任务仍发布 | 已修复原反例。RunFence 的共享 FileLock 与会改变 owner/状态的队列操作使用同一锁，提交锁内再次核验；原确定性竞争现在拒绝旧快照。失权 heartbeat 设置 cancel；已有并新增竞争/停止测试通过。 |
| F3：费用 oracle 来自生产函数 | 已修复该原反例。冻结费用为人工值 5.01；正常生产函数故意改为 123 后，case 返回 BASELINE_FAILED，而非 KILLED。此项关闭不代表所有关键变异及真实执行链验收都因此完成。 |
| F4：未知期初持仓被分给已知策略 | 已修复原反例。来源持仓按初始存量、成交、拆股事件维护；独立复现得到 known=100、unassigned=100。新增混合来源和拆股测试通过。 |
| F5：失败/报错/跳过被计 covered | 普通用例的原反例已修复；但参数化身份被截断，部分执行仍可 covered，详见下文。 |

## F5-R · P2：丢弃参数化 nodeid，未执行完整参数集也被认定覆盖

位置：`quantide/audit/acceptance.py:283–289,300–318`，以及 `_evidence_ok()`。

`_case_identity()` 用 `name.split("[")[0]` 丢弃参数 ID，`_defined_tests()` 只用正则提取函数名。因此同一个测试函数只执行一个参数实例，就与“该函数全部参数实例执行完”无法区分。

本轮使用真实 pytest 执行，不是只伪造一份 XML：

```bash
.venv/bin/python -m scripts.artifact_paths --run .venv/bin/python -m pytest \
  tests/unit/quantide/audit/test_synthetic.py \
  tests/unit/quantide/audit/test_statistics.py \
  '--deselect=tests/unit/quantide/audit/test_synthetic.py::test_pearson_power_recovers_positive_and_negative_signals[-0.25]' \
  --disable-socket --allow-unix-socket \
  --allow-hosts=127.0.0.1,::1,localhost --timeout=60 --no-cov \
  --junitxml=/tmp/millionaire-ce/audit001-r6-ic-partial.xml -q
```

结果为 **13 passed、1 deselected**：负向 `-0.25` 的检验明确没有执行。但将这份 XML 交给 matrix 后，`AC-4004.status` 仍为 **covered**。该 AC 明确要求正/负植入信号验证；其映射的 synthetic/statistics 两个文件在函数名层面看似齐全，却没有执行完整参数集。AC-4005 也同时被标 covered。

另一个同根问题：参数身份合并后，先出现的 skipped 参数可以被后出现的 passed 参数覆盖；目前只有 failed 结果被保留为不可覆盖。这仍不满足第五轮要求的“参数化实例/完整用例组”和必需验收无 skip/xfail 的合同。

这不意味着本轮真实全量验收存在失败或已绕过 GitHub 发布规则；问题在于 matrix 本身仍会错误认证不完整的外部证据。

### 修复要求

1. 保存完整 pytest nodeid，包括类身份与参数化 ID；不能按函数基本名合并不同实例。
2. 从同一 ref/配置下的 pytest collection manifest 或显式 AC 用例组获得预期 nodeid 集合；源码正则不能作为参数化收集结果。
3. 只在全部必需实例存在且成功时 covered；缺失、deselected、skip/xfail、failure/error 都不能计通过。
4. 添加真实 pytest 部分参数执行的回归；添加同一函数一参数 skip、另一参数 pass，以及仅运行类中部分测试的证据合并测试。

## 验证

| 检查 | 结果 |
| --- | --- |
| 全量 unit | 4946 passed、3 skipped；覆盖率工具整数汇总 83% |
| 现有 release_gate 选择集 | 29 passed、276 deselected；JUnit gate 非空且无 skip/xfail |
| mypy | 360 个源文件通过 |
| Ruff/行宽、认知复杂度、重复/大小 | 全部通过 |
| 严格文档构建、目录布局、git diff --check | 全部通过 |

独立旧反例复测输出在 `/tmp/millionaire-ce/audit001-r6-old-repro.log`。真实 Runner 与初步参数化边界复现脚本为 `audit001-r6-boundary.py`，输出为 `audit001-r6-boundary-results.json`；仅 synthetic 的初步测试为 `audit001-r6-synthetic-partial.*`。上文完整反例的原始 pytest 日志/JUnit 为 `audit001-r6-ic-partial.*`。其他测试和工具产物为同目录 `audit001-r6-*`，均不提交生成物。

本轮没有执行三平台安装或远端部署。建议修复 F5-R 后再核对该项，随后按 completion-guide 和真实 AC 证据确定整版完成状态。
