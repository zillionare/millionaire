---
date: 2026-07-09
session: maestro-v0.2-003-coverage-stage-1-fix
agents: [Maestro, GPT-5.5, Sage]
spec: v0.2-003-coverage
related_issues: [v0.2-003 #193-#217]
status: in_progress
---

## Topic
v0.2-003-coverage Stage 1 (verify-acceptance) 修复 — spec.md FR/NFR 2 级 → 3 级 (louke 工具兼容)

## Decision
- GPT-5.5 review 改写 spec.md 用表结构 (line 62-71 列出 FR 范围) + User Story 段, 不用 `### FR-XXXX` 标题
- 0.8 lex verify-acceptance 期望 `### FR-XXXX` 4 位 3 级标题
- sed 改 `## FR-` / `## NFR-` → `### FR-` / `### NFR-` (只 FR/NFR, 不动其他 2 级标题如 范围, 用户故事)
- 重跑 verify-acceptance 5/5 PASS

## 后续
- stage 2/3 跳过 (老 v0.2-001 issue 路径不兼容, 同 v0.2-002-ui)
- record_lock 跳过, 显式确认 current_stage=M-SPEC
- 启 M-TESTPLAN (Archer 写 test-plan.md)
- 然后 M-ARCH (Archer 写 architecture.md + interfaces.md)
- 然后 M-DEV (Devon 写业务导向单测, 不为覆盖率)
- 最后 M-E2E + M-MILESTONE
