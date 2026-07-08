---
date: 2026-07-08
session: sage-v0.2-002-round-10b-codex-p1-2-3-4
agents: [Maestro, Sage]
spec: v0.2-002-ui
related_issues: [#132, #167]
status: resolved
supersedes: [raw/2026-07-08/sage-v0.2-002-round-10a2-ac-format-fix.md]
---

## Topic
Round 10b: 处理 codex 4 P1 中的 P1-2/P1-3/P1-4 (P1-1 已在 Round 10a 处理)

## Decision
- P1-2 FR-0411: 拆 2 层 (account.hidden 服务端 + display_hidden_accounts localStorage), 8 条新 AC
- P1-3 FR-0080: 加 4 条 AC (每日持仓)
- P1-4 FR-0420 AC-9: 网关离线降级 (阻止提交, 不暂存, 不自动发送, 等 #132)
- 同时改 spec.md line 1232 (FR-0420 提交反馈) 保持一致
- Lex stage 1: 5/5 PASS (206 ACs)

## Open questions
- #132 后台结论未出, FR-0420 离线降级为临时方案
- account.hidden 字段契约需核实 001-FR-220

## Mistakes to avoid
- Sage 子 agent 报告"open question"中提到 "Codex 其他 P1 (UI-FR-A180 能力开关写反)" — 这是 P1-1, 已在 Round 10a 处理, 不是遗留项
