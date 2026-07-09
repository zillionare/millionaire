---
spec: v0.2-002-ui
title: Louke 工具 Bug
description: v0.2-002-ui 阶段发现的 Louke 0.7.x 工具 bug 及 workaround
---

# v0.2-002-ui — Louke 工具 Bug 报告与 Workaround

> 本页记录 v0.2-002-ui 阶段发现的 Louke 0.7.x 工具 bug，以及本项目采取的 workaround。

## Louke Bug #93 — 中文 label 不支持（wont-fix）

### 描述

`verify_issue_schema.py` 第 77-79 行硬编码英文 field name:
```python
FIELD_FR_ID = "Requirement ID"
FIELD_SPEC_URL = "Spec Link"
FIELD_AC = "Acceptance Criteria"
```

但本项目 `.github/ISSUE_TEMPLATE/feature.yml` 定义的是中文 label:
```yaml
label: 需求 ID    # id: fr_id
label: Spec 链接  # id: spec_url
label: 验收标准    # id: acceptance_criteria
```

GitHub 渲染后 issue body 实际是 `### 需求 ID` / `### Spec 链接` / `### 验收标准`，而 Python 代码用英文 key `"Requirement ID"` 等去取，永远返回空字符串。

### 影响

所有用中文 ISSUE_TEMPLATE 的项目，`verify-issue` 永远 0 PASS（90个issue全部 L2/L3/L7 missing）。

### 本项目 workaround

**已放弃（wont-fix）**: 不改 `feature.yml`（因为 Louke 已 close wont-fix）。

**实际上本项目 45 个 v0.2-002-ui issue body 字段实际合规**，Sage 手动验证：
```
PARSED FIELDS: {'需求 ID': 'FR-0010', 'Spec 链接': 'https://...', '验收标准': '无'}
Requirement ID: None   <- 代码取这个，永远 None
需求 ID: 'FR-0010'    <- 实际在这里
```

### 证据

> "缺陷 1: verify_issue_schema.py 用英文 label, 但 ISSUE_TEMPLATE 用中文 label"  
> `sage-v0.2-002-round-10e-lex-verify.md` line 53-90

### 状态

**Closed (wont-fix)** — 不修 `feature.yml`，保持中文 label，接受 verify-issue 永远 FAIL。

---

## Louke Bug #94 — `verify-issue` 不支持 `--branch`（已修 in louke 0.7.5）

### 描述

`lex.py` 的 `verify-issue` 子命令只注册了 `--spec` 和 `--repo`，没有 `--branch`（对比 `verify-acceptance` 有 `--branch`）。

底层 `verify_issue_schema.py` branch 未传时取 `gh repo view` 的 `defaultBranchRef` = `main`，但本项目 spec 在 `releases/v0.2` 分支，main 上不存在 → 404。

### 影响

即使 bug #93 修复，只要项目用 release 分支而非 main 承载 spec，`verify-issue` 仍会因 L4（spec unreachable）失败。

### 本项目 workaround

**已修（louke 0.7.5）**: `maestro-v0.2-002-stage-m-lock.md` 记录 `#94 ✅ 修（louke 0.7.5）`。

### 证据

> "缺陷 2: verify-issue 不支持 --branch, 默认走 main, 但 spec 在 releases/v0.2"  
> `sage-v0.2-002-round-10e-lex-verify.md` line 93-108

---

## Louke Bug #95 — `project.toml` 硬编码（wont-fix）

### 描述

`_common.py` 第 7 行:
```python
PROJECT_INFO_PATH = Path('.louke/project/project.toml')
```

`_read_project_info_field()` 第 38 行只读 `.toml`，不支持 Markdown 格式的 `project-info.md`。本项目只有 `.louke/project/project-info.md`（Markdown 格式，内有 `Project ID: https://github.com/users/zillionare/projects/5`）。

### 影响

`verify-project` 永远 fail（`project_url = ''`），无法验证 Project 关联。

### 本项目 workaround

**已放弃（wont-fix）**: 不改 `project.toml`（Louke 已 close wont-fix）。

实际上 45 个 issue 已全部关联 Project #5（millionaire-v0.2），Sage 手动验证：
```bash
gh issue view 167 --repo zillionare/millionaire --json projectItems
# 输出包含 "title":"millionaire-v0.2" -> 已关联 Project #5
```

### 证据

> "缺陷 3: verify-project 找 project.toml, 但本项目用 project-info.md"  
> `sage-v0.2-002-round-10e-lex-verify.md` line 109-127

### 状态

**Closed (wont-fix)** — 不修 project.toml，接受 verify-project 永远 FAIL。

---

## v0.2-001 老 Issue 路径不兼容（不可解）

### 描述

v0.2-001 阶段创建的 39 个老 issue body Spec Link 指向 `.specforge/project/v0.2-001-strategy-framework/spec-{foundation,strategy,trading}.md`。

Louke 0.7.2 工具 Lex `RE_SPEC_URL` 硬编码期望 `.louke/project/(?:specs/)?{spec_id}/spec{vol}.md`。**路径前缀不兼容，老 issue 永远 L3 FAIL**。

### 影响

一次性拉所有 Feature label 的 issue（90个）时，v0.2-001 的39个老 issue 会导致 stage 2 verify-issue 永远 FAIL。

### 尝试过的修复（均不可行）

| 方案 | 描述 | 结果 |
|------|------|------|
| A1 | `git mv` 老 spec 到 `.louke/project/specs/v0.2-001-strategy-framework/` | ~2-3小时工作量，且 acceptance.md 链接也要改 |
| A2 | 改老 issue body Spec Link 字段路径 | 实际路径不存在，link 会 broken |
| B | 跳过 record-lock，直接进 M-LOCK | ✅ **Aaron 已选** |

### 证据

> "v0.2-001 老 spec 路径 `.specforge/project/...` 不兼容 Lex 0.7+ 期望 `.louke/project/...`"  
> `maestro-v0.2-002-record-lock-blocked.md` line 18-23

### 状态

**不可解** — 工具层面无 workaround，v0.2-001 老 issue 路径问题无法在 v0.2-002-ui 项目内解决。record-lock 跳过，Aaron 显式确认。

---

## 本项目 3 个 Workaround 实施总结

| Bug | 本项目 workaround | 状态 |
|-----|------------------|------|
| #93 中文 label | 不修（wont-fix），接受 verify-issue 永远 FAIL | CLOSED wont-fix |
| #94 --branch | 升级到 louke 0.7.5 | CLOSED 修 |
| #95 project.toml | 不修（wont-fix），接受 verify-project 永远 FAIL | CLOSED wont-fix |
| v0.2-001 路径 | 跳过 record-lock（Aaron 决策） | 已知不可解 |
