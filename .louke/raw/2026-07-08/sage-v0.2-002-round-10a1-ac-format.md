---
date: 2026-07-08
session: sage-v0.2-002-round-10a1-ac-format
agents: [Maestro, Sage]
spec: v0.2-002-ui
related_issues: [#167]
status: resolved
supersedes: []
---

## Topic
AC 格式转换 (阶段 A 延伸): Lex 0.7.2 L3 期望 ### AC-N heading 格式, 阶段 A 漏改 acceptance.md 内 AC 写法

## Decision
- acceptance.md 内 - AC-N: 内容 bullet → ### AC-N (heading) + - 内容 (bullet, 下一行)
- 191 处 AC heading 转换
- nested bullet (2 空格) → 4 空格 (heading 内的延续)
- 0 处内容文字改动 (纯格式)

## Tried but abandoned
- 第一次转换 (Sage task) 返回空输出, 原因未明; 改由 Maestro 直接跑 Python 脚本完成
- 第一次 regex 误把 `### AC-N: 内容` 留在标题同行; Lex 期望 `### AC-N` 后只能空白; 修正为 `### AC-N\n- 内容`

## Open questions
- FR-0180 AC 节已加 (Round 10a), 但 spec.md FR-0180 标题与锚点的 `重复标题/锚点错乱` 已知 bug 实为文件渲染错觉 (Sage 已核实, 不存在)

## Mistakes to avoid
- Lex 默认从远端读文件, 本地修改后必须 commit + push 才能被 Lex 看到
