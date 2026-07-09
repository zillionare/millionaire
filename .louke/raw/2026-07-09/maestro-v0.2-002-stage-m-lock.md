---
date: 2026-07-09
session: maestro-v0.2-002-stage-m-lock
agents: [Maestro, Aaron]
spec: v0.2-002-ui
related_issues: [louke #93 #94 #95, project #55-#177]
status: resolved
supersedes: [raw/2026-07-09/maestro-v0.2-002-record-lock-blocked.md, raw/2026-07-09/maestro-v0.2-002-v001-issues-migrated.md]
---

## Topic
v0.2-002-ui stage 转移: M-SPEC → M-LOCK (Aaron 2026-07-09 显式确认)

## Decision
- 更新 `.louke/project/project.toml` 的 `current_stage` 字段: `M-FOUND` → `M-LOCK`
- commit `8010527` (已 push)
- 跳过 Louke `record-lock` (Stage 2/3 仍阻塞, 不影响 M-LOCK 后流程)

## 三信号状态

- **Sage quote-check**: ✅ 0 blockers
- **Lex stage 1 (verify-acceptance)**: ✅ 5/5 PASS (215 ACs)
- **Lex stage 2 (verify-issue)**: ❌ 45 PASS / 45 FAIL (v0.2-001 老 issue, 路径不兼容 Lex 0.7+)
- **Lex stage 3 (verify-project)**: ❌ gh project item-list failed (空错误, 待查)
- **record-lock**: ❌ 跳过 (Aaron 显式确认, 不阻塞主流程)

## 阻塞项 (待 Louke 修或后续清理, 不阻塞 M-TESTPLAN)

| 项 | 状态 | 修法 |
|---|---|---|
| v0.2-001 老 spec 路径 `.specforge/project/...` 不兼容 Lex 0.7+ 期望 `.louke/project/...` | 已知 | A1: git mv 老 spec 到 `.louke/project/specs/v0.2-001-strategy-framework/` (~60 min) |
| louke #94 (--branch) | ✅ 修 (louke 0.7.5) | — |
| louke #93 (中文 label) | closed (wont-fix) | workaround: 改 feature.yml 英文 |
| louke #95 (project.toml 硬编码) | closed (wont-fix) | workaround: 用 project.toml 替代 project-info.md |
| Stage 3 gh project item-list 空错误 | 待查 | 可能是 tomli 依赖 / gh 权限 / API 限制 |
| 老 issue 39 个 title 4 位 + body 字段 | ✅ 已修 (39/39) | — |

## M-LOCK 后阶段

- M-TESTPLAN (Archer): 不依赖 record-lock 状态
- M-ARCH (Archer): 不依赖 record-lock
- M-DEV (Devon): 不依赖 record-lock
- M-E2E (Shield): 不依赖 record-lock
- M-MILESTONE (Librarian): 不依赖 record-lock

## Open questions

- 是否需要在 M-DEV 完成后回头修 v0.2-001 老 issue 路径 (A1), 让 record-lock 状态真正 PASS?
- Stage 3 空错误待查 — 可以在 M-TESTPLAN 阶段并行排查

## Mistakes to avoid

- 不要在 M-LOCK 后期待 record-lock 自动通过 (Stage 2/3 阻塞未解)
- 不要在 v0.2-002-ui 范围外花时间修 v0.2-001 老 spec (除非是 M-SPEC 收尾清理)
- 跑 `lk agent lex verify-issue` 仍会失败, 这不意味着 spec 错
EOF
