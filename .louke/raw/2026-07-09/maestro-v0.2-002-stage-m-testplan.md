---
date: 2026-07-09
session: maestro-v0.2-002-stage-m-testplan
agents: [Maestro, Archer]
spec: v0.2-002-ui
related_issues: [project #132-#177]
status: resolved
supersedes: [raw/2026-07-09/maestro-v0.2-002-stage-m-lock.md]
---

## Topic
v0.2-002-ui stage 转移: M-LOCK → M-TESTPLAN (Archer 2026-07-09 完成 test-plan)

## Decision
- Archer subagent 写 test-plan.md (commit `50bb6c9`, 231 行, 45/45 FR/NFR 覆盖)
- 更新 `project.toml`: `current_stage` M-LOCK → M-TESTPLAN
- Lex stage 1 仍 5/5 PASS (Archer 不动 spec/acceptance, 只新增 test-plan)
- 准备启动 M-ARCH (Archer 设计 architecture.md)

## Archer M-TESTPLAN 产出

- `.louke/project/specs/v0.2-002-ui/test-plan.md` (231 行)
- 45/45 FR/NFR 覆盖矩阵
- 外部依赖 mock: FastHTML + MonsterUI (stub) / Tushare (fixture) / qmt-gateway (stub)
- 风险 6 项 (视觉颜色断言 / gateway 状态时序 / SSE vs WebSocket / 异步长任务 / 图表 hover / 跨浏览器状态)
- raw session: `.louke/raw/2026-07-09/sage-v0.2-002-m-testplan-archer.md`

## Open questions

- M-ARCH 后是否需要修 v0.2-001 老 issue 路径 (让 record-lock 状态真正 PASS)?
- Stage 3 gh project item-list 空错误待查
- M-DEV 完成后回头跑 record-lock?

## Mistakes to avoid

- 不要在 M-TESTPLAN 阶段改 spec/acceptance (Archer 已确认不动)
- 不要跳过 M-ARCH 直接 M-DEV (architecture 是关键设计)
- Lex stage 2/3 仍阻塞 — 不要让 M-ARCH 涉及老 issue (architecture 应仅 v0.2-002-ui 范围)
