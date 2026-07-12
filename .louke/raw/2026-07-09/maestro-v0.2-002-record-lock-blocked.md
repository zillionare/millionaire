---
date: 2026-07-09
session: maestro-v0.2-002-record-lock-blocked
agents: [Maestro, Aaron]
spec: v0.2-002-ui
related_issues: [louke #93 #94 #95, project #55-#93 v0.2-001, #132-#177 v0.2-002]
status: open
supersedes: [raw/2026-07-08/maestro-v0.2-002-record-lock-state.md, raw/2026-07-09/maestro-v0.2-002-v001-issues-migrated.md]
---

## Topic
v0.2-002-ui record-lock 三信号:
- Stage 1 verify-acceptance: ✅ 5/5 PASS (215 ACs)
- Stage 2 verify-issue: ❌ 45 PASS / 45 FAIL
- Stage 3 verify-project: ❌ gh project item-list failed (空错误)
- record-lock: ❌ REJECT

## 阻塞 #1: v0.2-001 老 spec 路径不兼容 Lex 0.7+

v0.2-001 老 issue body 的 Spec Link 是 `.specforge/project/v0.2-001-strategy-framework/spec-{foundation,strategy,trading}.md`. Louke 0.7.2 工具 Lex `RE_SPEC_URL` 硬编码期望 `.louke/project/(?:specs/)?{spec_id}/spec{vol}.md`. **路径前缀不兼容, 老 issue 永远 L3 FAIL**.

Aaron 选 A (修老 issue), 但 A 实际不可行. 修 title 4 位 + body 字段都不够, 路径才是关键.

## 已做的修复 (但被路径阻塞)

1. ✅ 修 title 4 位: 39/39 `[FR-0010]` `[NFR-0060]` 等
2. ✅ 改 body label 英文: 39/39 `### Requirement ID` / `### Spec Link` / `### Acceptance Criteria`
3. ❌ 路径 `.specforge/...` → Lex 期望 `.louke/project/...` — 不能改 Lex 源码 (workaround 不能改 louke)

## 阻塞 #2: louke #94 (--branch 不支持)

Stage 2 跑 `lk agent lex verify-issue` 不支持 --branch, 走 main 报 404 warn. 已有 bug report https://github.com/zillionare/louke/issues/94, Aaron 等修.

## 阻塞 #3: Stage 3 gh project item-list failed

空错误. louke 子进程用 tomli 解析 project.toml, 但 lk venv 没装 tomli (我已装但仍报空错误, 原因待查).

## 选项 (等 Aaron 决策)

| 选项 | 描述 | 影响 |
|---|---|---|
| **A1** | 把 v0.2-001 老 spec 从 `.specforge/project/...` 移 (git mv) 到 `.louke/project/specs/v0.2-001-strategy-framework/...` | 39 老 issue 修路径, 可能让 stage 2 全 PASS. 但 v0.2-001 spec 内容本身也要改 (acceptance.md 链接等), 工作量 ~2-3 小时 |
| **A2** | 改老 issue body 的 Spec Link 字段, 把 `.specforge/project/` 改成 `.louke/project/specs/v0.2-001-strategy-framework/` | 同 A1 但不动 spec 文件, 也不改实际路径. 但实际路径不存在, link 会 broken |
| **B** | 跳过 record-lock, 直接进 M-LOCK + M-TESTPLAN | record-lock 是 lock 状态, 不 lock 也不阻塞 M-SPEC 工作流 |
| **C** | 跳过 Stage 2/3 老 issue 范围 (Lex 加 spec 过滤, 让 v0.2-001 不检查) | 工具改不了, 等 Louke 修 |

我倾向 **B**: 3 信号 Stage 1 已 PASS, Stage 2/3 阻塞于工具和路径, 不是数据问题. 走 M-LOCK 时人工确认 + record-lock, 或跳过 record-lock (M-LOCK 状态由 Aaron 显式给).

## Open questions

- Aaron 是否等 #94 修后再 record-lock
- A1/A2 大改动是否值得
- B 接受: 跳过 record-lock, 直接进 M-TESTPLAN
EOF
