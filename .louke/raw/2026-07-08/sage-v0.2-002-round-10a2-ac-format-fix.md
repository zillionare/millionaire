---
date: 2026-07-08
session: sage-v0.2-002-round-10a2-ac-format-fix
agents: [Maestro, Sage]
spec: v0.2-002-ui
related_issues: []
status: resolved
supersedes: [raw/2026-07-08/sage-v0.2-002-round-10a1-ac-format.md]
---

## Topic
acceptance.md AC format fix Round 2: 处理 `### AC-N (annotation):` 格式

## Decision
- 10 处 ### AC-N (xxx 注释): 内容的 AC heading 转为标准格式 `### AC-N\n- 内容`
- Lex 阶段一 5/5 PASS
- 201 ACs 全部正确识别, 编号连续

## Root cause
- Round 10a.1 的 regex `^(### AC-(\d+)):\s*(.+?)$` 不匹配带 `(annotation)` 的 AC heading
- FR-0160/0340/0460 等几处 AC heading 用了 "(Aaron Round X 决策沉淀)" 等注释
- 3 个 FR 报 AC 跳号 (缺 5, 缺 3, 缺 2/3/4)

## Fix
- 强化 regex: `^(### AC-(\d+))(?:\s*\([^)]*\))?\s*:\s*(.+?)$`
- 把 `(annotation)` 作为可选, 不再要求紧跟冒号

## Open questions
- 阶段 A + Round 10a.1 + 10a.2 完成后, Lex 阶段一 5/5 PASS
- 下一步: Round 10b (P1-2/P1-3/P1-4), 然后 10c (P2/P3), 然后 10d (45 issues), 然后 10e (Lex 阶段二/三)

## Mistakes to avoid
- Lex 默认从远端读文件, 本地修改后必须 commit + push 才能被 Lex 看到
- Lex L3 期望 `### AC-N` 后只能空白, 不能有内容 (即使空注释也不行)
