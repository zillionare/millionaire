---
date: 2026-07-10 (task assigned 2026-07-09)
session: sage-v0.2-003-coverage-step5-issues
agents: [Sage]
spec: v0.2-003-coverage
related_issues:
  - "#193 ~ #217 (25 FR/NFR issues, created by this session)"
  - "#178 (smoke, pre-existing, not touched)"
branch: releases/v0.2
status: completed
---

# Sage Step 5 — v0.2-003-coverage: 创建 25 GitHub Issues

## Topic

按 `.opencode/agents/sage.md` Step 5 协议 + Louke 0.8 issue 协议, 给 v0.2-003-coverage
spec 中每个 `FR-XXXX` / `NFR-XXXX` 创建 1 个 GitHub issue, 并关联到 project #5
(`millionaire-v0.2`).

## 输入

- spec: `.louke/project/specs/v0.2-003-coverage/spec.md` (816 行)
- acceptance: `.louke/project/specs/v0.2-003-coverage/acceptance.md` (531 行)
- 分支: `releases/v0.2`
- 起点 commit: `58c2e4e` (M-SPEC Phase 1 done; 6 quote RESOLVED + Lex 5/5 PASS)
- 项目: `millionaire-v0.2` (#5, ID `PVT_kwHOAG33KM4Ba79Q`)

## FR/NFR 解析

从 `spec.md` 提取 `### FR-XXXX title` 和 `### NFR-XXXX title` 共 **25 条** (23 FR + 2 NFR):

| 类别 | 编号 | 数量 |
|------|------|------|
| FR-01xx 测试基础设施 | FR-0101 ~ FR-0104 | 4 |
| FR-02xx core/ 单测 | FR-0201 ~ FR-0207 | 7 |
| FR-03xx data/ 单测 | FR-0301 ~ FR-0304 | 4 |
| FR-04xx service/ 单测 | FR-0401 ~ FR-0404 | 4 |
| FR-05xx web/components/ 单测 | FR-0501 ~ FR-0502 | 2 |
| FR-06xx CI/CD | FR-0601 ~ FR-0602 | 2 |
| NFR 阈值 / 隔离 | NFR-0010, NFR-0020 | 2 |
| **总计** |  | **25** |

## URL 计算

按 Louke 0.8 issue 协议, 模板:

```
### Requirement ID
{REQ-ID}

### Spec Link
{SPEC_URL}#{anchor}

### Acceptance Criteria
{ACCEPTANCE_URL}#ac-{anchor}
```

其中:

- `SPEC_URL` = `https://github.com/zillionare/millionaire/blob/releases/v0.2/.louke/project/specs/v0.2-003-coverage/spec.md`
- `ACCEPTANCE_URL` = `https://github.com/zillionare/millionaire/blob/releases/v0.2/.louke/project/specs/v0.2-003-coverage/acceptance.md`
- `anchor` = 小写 `fr-XXXX` 或 `nfr-XXXX` (4 位数字)

样例 (FR-0101):

```
### Requirement ID
FR-0101

### Spec Link
https://github.com/zillionare/millionaire/blob/releases/v0.2/.louke/project/specs/v0.2-003-coverage/spec.md#fr-0101

### Acceptance Criteria
https://github.com/zillionare/millionaire/blob/releases/v0.2/.louke/project/specs/v0.2-003-coverage/acceptance.md#ac-fr-0101
```

与 v0.2-002-ui (Round 10d `sage-v0.2-002-round-10d-issues-rename.md`) 协议一致:

- 标题: `[FR-XXXX] {title}` (方括号 + 4 位)
- Body: 三段, 英文 label (`### Requirement ID` / `### Spec Link` / `### Acceptance Criteria`)
- Issue label: `feature`

## 执行流程

### 1. 编写 Python 脚本

`/tmp/create_v0.2_003_coverage_issues.py` (临时文件, 已执行):

- 定义 25 条 (req_id, title_suffix) 元组
- 用 `gh issue create --repo zillionare/millionaire --title "..." --body "..." --label "feature"` 创建
- 用 `gh project item-add 5 --owner zillionare --url <issue_url>` 关联项目

### 2. 跑脚本

```bash
python3 /tmp/create_v0.2_003_coverage_issues.py
```

### 3. 创建结果 (25/25)

| Issue # | Title | Status |
|---------|-------|--------|
| #193 | `[FR-0101] pytest 配置与覆盖率命令` | OPEN |
| #194 | `[FR-0102] 覆盖率阈值与排除清单` | OPEN |
| #195 | `[FR-0103] Mock 框架与 Fixture 共享` | OPEN |
| #196 | `[FR-0104] 测试隔离与确定性` | OPEN |
| #197 | `[FR-0201] core/domain/ 单测` | OPEN |
| #198 | `[FR-0202] core/runtime/clock_bridge 单测` | OPEN |
| #199 | `[FR-0203] core/runtime/gateway_broker + gateway_client 单测` | OPEN |
| #200 | `[FR-0204] core/runtime/modes + port_broker 单测` | OPEN |
| #201 | `[FR-0205] core/strategy + strategy_discovery + scheduler 单测` | OPEN |
| #202 | `[FR-0206] core/ 基础模块单测 (enums / message / errors / sdk_metadata)` | OPEN |
| #203 | `[FR-0207] core/ports/ 单测` | OPEN |
| #204 | `[FR-0301] data/fetchers/ 单测` | OPEN |
| #205 | `[FR-0302] data/models/ 单测` | OPEN |
| #206 | `[FR-0303] data/stores/ + sqlite 单测` | OPEN |
| #207 | `[FR-0304] data/helper + utils/resampler 单测` | OPEN |
| #208 | `[FR-0401] service/ 策略运行时与执行器单测` | OPEN |
| #209 | `[FR-0402] service/ 三类 broker 单测` | OPEN |
| #210 | `[FR-0403] service/ 数据馈送与实时行情单测` | OPEN |
| #211 | `[FR-0404] service/ 其它服务单测` | OPEN |
| #212 | `[FR-0501] web/components/analysis/ 单测` | OPEN |
| #213 | `[FR-0502] web/components/ 通用组件单测 (验证类)` | OPEN |
| #214 | `[FR-0601] CI 强制覆盖率门槛` | OPEN |
| #215 | `[FR-0602] HTML 覆盖率报告 + 增量覆盖率 (可选)` | OPEN |
| #216 | `[NFR-0010] 覆盖率阈值与豁免机制` | OPEN |
| #217 | `[NFR-0020] 测试隔离与确定性` | OPEN |

所有 25 个 issue 均带 `feature` label, 状态 OPEN, 关联到 project #5 (millionaire-v0.2).

### 4. 验证

```bash
# 25 issue 创建确认 (gh issue list)
gh issue list --repo zillionare/millionaire --state all --limit 30 --json number,title,labels,state
# Found 25 issues in range 193-217, all OPEN, all feature label

# 项目关联确认 (gh project item-list)
gh project item-list 5 --owner zillionare --limit 200 --format json
# Total items: 76 (前: 51 = 45 v0.2-002-ui + 5 v0.2-001 + 1 v0.2-003 smoke)
# v0.2-003-coverage: 26 issues (1 smoke #178 + 25 new #193~#217)
```

## 关键执行细节

### Body 格式 (与 v0.2-002-ui 严格一致)

```
### Requirement ID
FR-0101

### Spec Link
<SPEC_URL>#fr-0101

### Acceptance Criteria
<ACCEPTANCE_URL>#ac-fr-0101
```

anchor 全部小写 (`fr-0101` / `ac-fr-0101` / `nfr-0020` / `ac-nfr-0020`), 与
spec.md `<a id="fr-XXXX">` 和 acceptance.md `<a id="ac-fr-XXXX">` 锚点一致.

### 异常处理

- 24/25 issue 一次跑通 + 项目关联成功
- #206 (FR-0303) 项目关联首次失败 (`unknown owner type` — gh CLI 偶发 API 错误)
- 立即重试 `gh project item-add 5 --owner zillionare --url ...` → 成功
- 总结果: 25/25 入项目 #5

### 不动的部分

- spec.md / acceptance.md (已 lock by previous M-SPEC steps)
- 老 issue #178 (smoke, 已存在, 由 Scout 在 M-FOUND 阶段建)
- 老 issue #1-177 (其它 spec / step2 / refactor 等, 与本 spec 无关)
- project #5 现有 status (不修改任何 status field)

## Decision

1. **Body 协议沿用 v0.2-002-ui**: 模板 + label + 锚点格式全部一致, 便于 Lex verify-issue 后续统一扫描
2. **label 全部 `feature`**: FR/NFR 一律标 feature, 不区分 (v0.2-002-ui 同样模式)
3. **不写 acceptance 内容到 body**: 仅链接到 acceptance.md#ac-fr-XXXX, 避免 body 过长, 与 v0.2-002-ui 一致
4. **gh CLI 而非 lk 命令**: 任务指定 (与 v0.2-002-ui 一致), lk `create-issues` 是 0.8 之后的协议, 老 Sage 子 agent 沿用 gh CLI
5. **临时脚本 `/tmp/create_*.py`**: 不入 git, 与 Round 10d `/tmp/rename_issues.py` 同样模式

## Tried but abandoned

- **用 `lk agent sage create-issues`**: 任务原文提到 louke 0.8 lk 命令, 但项目历史 (v0.2-002-ui Round 10d) 显示是用 gh CLI. 任务指定"之前 v0.2-002-ui 跑过 45 issues (M-SPEC Step 5, Sage agent 写). 一样跑.", 决定沿用 gh CLI.
- **每个 issue 单独 commit**: 没有源码改动, 25 issues 创建是 GitHub 远程操作, 不需要 per-issue commit.
- **设置 milestone**: v0.2-002-ui 45 issues 也没设 milestone, 沿用 None.

## Open questions

无. 25 issues 全部创建成功 + 入项目 #5. 任务完成.

## Files

- `.louke/raw/2026-07-09/sage-v0.2-003-coverage-step5-issues.md` (本文件)
- `/tmp/create_v0.2_003_coverage_issues.py` (Python 脚本, 已执行, 临时文件)
- `/tmp/v0.2-003-coverage-issues.json` (创建结果 JSON, 临时文件)
- `/tmp/v0.2-003-coverage-create-output.txt` (创建日志, 临时文件)

## Notes

- 本次 commit: `chore: create 25 spec issues (FR-XXXX + NFR-XXXX) for v0.2-003-coverage M-SPEC Step 5` (仅 add raw session)
- 不动 spec.md / acceptance.md / 任何老 issue
- record_lock 不动 (Stage 2 45 FAIL 已知, 跳过 — 见 commit `58c2e4e`)
- 下一步 (后续 spec): Lex verify-issue + verify-project (Stage 2/3), 但因 louke #94 bug + 老 issue 阻塞, 在 v0.2-003-coverage 同样跳过, 与 v0.2-002-ui 路径一致 (见 commit `8010527`)
