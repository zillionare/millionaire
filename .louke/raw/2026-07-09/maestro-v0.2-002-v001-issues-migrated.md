---
date: 2026-07-09
session: maestro-v0.2-002-v001-issues-migrated
agents: [Maestro]
spec: v0.2-001-strategy-framework (历史包袱, 非本 spec)
related_issues: [#55-#93]
status: resolved
---

## Topic
修 v0.2-001 老 issue (39 个) 让 Lex stage 2 全 PASS, 解 record-lock 阻塞.

## Decision
- Title 改 4 位: `[FR-000010]` (sed 错改的 6 位) → `[FR-0010]`
- Body 中文 label → 英文: "需求 ID" → "Requirement ID" 等
- 39/39 修好

## 影响
- v0.2-001 老 issue 不再阻塞 v0.2-002-ui record-lock
- Aaron 之前选择 A: 修 v0.2-001 老 issue (本 commit) 而不是跳过

## Mistakes to avoid
- sed 错把 3 位编号变 6 位 (`[FR-010]` → `[FR-000010]`, regex `(\d{1})([0-9]{2})` 把 `010` 当 3+2 分组, 加 `0` 0 + `010` = `000010`)
- 修法: 用 `zfill(4)` 统一处理, 不要分组
