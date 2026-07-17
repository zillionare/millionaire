# v0.2-004-coverage-recovery Review (2026-07-13)

> **范围**: story.md + spec.md + acceptance.md + test-plan.md + architecture.md + interfaces.md + coverage-waivers.json
>
> **评审维度**: (1) spec/acc 与 story 对齐; (2) test-plan/architecture/interfaces 与 spec/acc 对齐; (3) 其他错误

---

## 第一部分: spec/acc 与 story 对齐

### 1.1 story 新增 FR 与 spec FR 映射

story §2 定义了三个新增 FR：FR-0801（文件分类审计）、FR-0802（分档覆盖率门禁）、FR-0803（豁免升级流程）。spec 使用独立的 FR-1001~FR-1901 编号体系，architecture §2.1 提供了映射表：

| story 标签 | spec 落点 | 对齐状态 |
|---|---|---|
| FR-0801 文件分类审计 | FR-1001 + FR-1101 + FR-1201 | ✓ 已映射 |
| FR-0802 分档覆盖率 ≥95/≥80 | NFR-1001 + FR-1901 | ✓ 已映射 |
| FR-0803 豁免升级流程 | FR-1801 | ⚠ 架构映射表缺失（见 P2-2） |

### 1.2 继承合同对齐

story §1 声明继承 v0.2-003 的 story/spec/acceptance/test-plan/architecture/interfaces。spec 明确声明"不重开或改写 v0.2-003"，继承 DoD、契约判定优先级、测试隔离和反作弊规则。acceptance 编号使用 FR-1001+ 避免碰撞。**对齐良好**。

### 1.3 DoD 对齐

story §3 列出 6 项 DoD（继承 5 项 + 新增第 6 项"coverage-file-classification.json"）。spec FR-1001/FR-1101/FR-1901 和 NFR-1001 覆盖了全部 6 项。acceptance AC-FR1001/FR1101/FR1901/NFR1001 逐条对应。**对齐良好**。

### 1.4 范围边界对齐

story §4 声明"不纳入范围"和"在范围内"，spec "范围与边界"节同步声明。但 story §4 有一处表述歧义（见 P2-1）。

### 1.5 发现总结

| # | 级别 | 问题 |
|---|---|---|
| P2-1 | P2 | story §4 "修复生产代码" 表述歧义 |
| P2-2 | P2 | FR-0803 → FR-1801 映射缺失于 architecture §2.1 |

---

## 第二部分: test-plan/architecture/interfaces 与 spec/acc 对齐

### 2.1 test-plan ↔ spec/acc

| 检查项 | 结果 | 说明 |
|---|---|---|
| 169 路径覆盖 (B01-B13) | ✓ | 逐 batch 计数合计 169，与 spec FR-1001 一致 |
| 196 RW 绑定 (B01-B13) | ✓ | 逐 batch 计数合计 196，与 spec FR-1301/FR-1401 一致 |
| AC 覆盖 | ✓ | test-plan §4 覆盖所有 FR family |
| Canonical pytest 命令 | ⚠ | **timeout 参数冲突**（见 P1-1） |

### 2.2 architecture ↔ spec/acc

| 检查项 | 结果 | 说明 |
|---|---|---|
| AC outlet map 总数 | ✓ | 64 AC = 52 FR + 12 NFR，与 acceptance 一致 |
| FR family 边界表 | ✓ | 10 FR + 4 NFR，与 spec 一致 |
| Recovery artifact layout | ✓ | 路径和 SHA 与 spec/interfaces 一致 |
| Story 映射表 §2.1 | ⚠ | FR-0803 映射缺失 |

### 2.3 interfaces ↔ spec/acc

| 检查项 | 结果 | 说明 |
|---|---|---|
| Canonical pytest 命令 | ⚠ | **与 test-plan 冲突**（见 P1-1） |
| Per-file checker 命令 | ✓ | 与 spec FR-1001/FR-1801 和 NFR-1001 一致 |
| Recovery artifact reader | ✓ | SHA 与 spec/acceptance 一致 |
| Waiver schema | ⚠ | **coverage-waivers.json 缺少 schema 字段**（见 P1-2） |
| Evidence package | ✓ | 字段与 spec FR-1901/AC-FR1901 一致 |
| AC outlet allocation §12 | ✓ | 64 AC 分布与 acceptance 一致 |

### 2.4 发现总结

| # | 级别 | 问题 |
|---|---|---|
| P1-1 | P1 | test-plan vs interfaces canonical pytest --timeout 冲突 |
| P1-2 | P1 | coverage-waivers.json 缺少 schema 字段导致 AC-FR1801-01 验证失败 |

---

## 第三部分: 其他错误

### P1-1: Canonical pytest 命令 --timeout 冲突

**test-plan §2.3** 的 canonical command:
```bash
python3 -m pytest tests/unit --timeout=120 ...
```

**interfaces §1** 的 canonical command:
```bash
poetry run pytest tests/unit --cov=quantide --cov-fail-under=95 --timeout=60 -o faulthandler_timeout=90 ...
```

`--timeout` 分别为 **120** 和 **60**，相差一倍。两者都声称是 canonical command，实施者无法确定应使用哪个值。

**建议**: 统一为一个值。如果 120s 是为了兼容慢机器，interfaces §1 应同步更新；如果 60s 是标准，test-plan §2.3 应修改。

### P1-2: coverage-waivers.json 缺少 schema 字段

**interfaces §8** 定义的 waiver registry schema 要求:
```json
{
  "schema": "coverage-waivers/v1",
  "spec_id": "...",
  "waivers": []
}
```

**当前文件**内容:
```json
{
  "spec_id": "v0.2-004-coverage-recovery",
  "description": "...",
  "waivers": []
}
```

缺少 `schema` 字段，多了一个 `description` 字段（interfaces schema 未声明此字段）。

**影响**: acceptance AC-FR1801-01 要求"初始 coverage-waivers.json 通过版本化 schema 校验"——当前文件无法通过该 AC。

**建议**: 在 coverage-waivers.json 中添加 `"schema": "coverage-waivers/v1"` 字段，并确认 `description` 是否在 schema 允许范围内（如不在，interfaces §8 应补充或文件应删除 description）。

### P2-1: story §4 "修复生产代码" 表述歧义

**位置**: story.md §4 "不纳入范围"

story §4 列出:
```
- 修复生产代码：当锁定合同证据显示实现缺陷时，修改生产代码以匹配合同。
- 修复/新增/删除测试（经可追溯审查）...
```

这些条目在 "不纳入范围" 标题下，但实际是**在范围内**的工作。读者第一眼会误认为"修复生产代码"也不做。spec "范围与边界" 节已正确声明"在范围内：生产代码修复"，但 story 作为上游合同不应有歧义。

**建议**: story §4 拆为 "在范围内" 和 "不在范围内" 两个子节。

### P2-2: architecture §2.1 缺少 FR-0803 映射

**位置**: architecture.md §2.1 "FR-08xx story 结构调和"

映射表包含 FR-0801（audit）和 FR-0802（v0.2-added ≥95%），但 FR-0803（豁免升级流程）没有出现。FR-0803 在 spec 中由 FR-1801 覆盖，但架构表未显式映射。

**建议**: 在 architecture §2.1 表中新增一行:

| Story 标签 | Spec 落点 | 架构解释 |
|---|---|---|
| FR-0803 豁免升级流程 | FR-1801 | 文件特定临时 waiver 验证；当前 registry 为空 |

### P2-3: spec.md FR-1901 尾部截断

**位置**: spec.md FR-1901 最后一个 bullet

文本显示:
```
- `--force`、generic waiver、issue 全关闭、人工口
```

末尾字符被截断（`口` 应为 `口头确认` 或类似词语）。

**建议**: 补全截断内容，例如:
```
- `--force`、generic waiver、issue 全关闭、人工口头确认均不满足 PASS 条件。
```

### P2-4: test-plan 引用 pytest-random-order 但未锁定版本

**位置**: test-plan §2.1

test-plan 声称:
> 顺序基线必须真实执行 `pytest --random-order`；执行环境须提供与 pytest 9 兼容的 `pytest-random-order` plugin。若 pytest 报 unknown option，环境 gate 失败。

但 `pytest-random-order` 未在 §2.1 版本约束列表中（只有 pytest/pytest-cov/pytest-asyncio/pytest-timeout/freezegun）。

**建议**: 在 test-plan §2.1 版本约束表中补充 `pytest-random-order` 的版本范围，或确认 pyproject.toml 已包含该依赖并显式引用。

### P3-1: spec.md 内嵌大量 Lex-Sage 讨论线程

**位置**: spec.md FR-1201、FR-1301、FR-1501、FR-1601 内

这些讨论线程提供了有价值的审计历史，但使 spec 主体文本难以快速阅读。FR-1201 和 FR-1601 的讨论线程各超过 20 行。

**建议**: 考虑将讨论线程移到独立文件（如 `recovery/lex-sage-threads.md`），spec 中只保留最终决议摘要和引用链接。

---

## 第四部分: 总结

| 指标 | 数值 |
|---|---|
| story → spec 覆盖 | 3/3 新增 FR 全部覆盖 |
| spec → acceptance 覆盖 | 10 FR + 4 NFR → 64 AC，100% |
| test-plan 169 路径 | ✓ 已验证 B01-B13 合计 169 |
| test-plan 196 RW | ✓ 已验证 B01-B13 合计 196 |
| architecture AC outlet | ✓ 64 AC 与 acceptance 一致 |
| interfaces SHA pin | ✓ 与 spec/acceptance 一致 |
| 发现问题 | 2 个 P1 + 4 个 P2 + 1 个 P3 |

**总体评价**: 这是一份高度精密的覆盖率恢复 spec——169 路径、196 RW、64 AC、5 个 SHA pin 全部交叉验证通过。六文档结构清晰，recovery 控制面与生产代码严格隔离。

主要问题集中在两个 P1：**canonical pytest --timeout 在 test-plan 和 interfaces 中不一致**（120 vs 60），以及 **coverage-waivers.json 缺少 schema 字段**导致 AC-FR1801-01 验证无法通过。这两个问题实施前必须修复。

P2 中 story §4 的表述歧义、architecture §2.1 缺失 FR-0803 映射、spec FR-1901 尾部截断和 pytest-random-order 版本缺失应在 review 阶段处理。
