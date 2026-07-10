---
date: 2026-07-09
session: sage-v0.2-003-coverage-quotes-resolved
agents: [Maestro]
spec: v0.2-003-coverage
related_issues: [louke #97]
status: resolved
---

## Topic
Sage M-SPEC 6 inline-discussion quotes 标 [RESOLVED] (Aaron IDE review + 默认答案)

## Decision
- T-001: 等 Aaron review (自身, 6 quote 标后 RESOLVED)
- T-002: FR 编号用 `FR-XXXX` (与 v0.2-002-ui 一致, louke 0.8 兼容)
- T-003: 阈值确认 (整体 ≥95%, 单模块 ≥80%)
- T-004: pytest 配置沿用 pyproject.toml (不引入 pytest.ini)
- T-005: NFR-0010 豁免仅 `__init__.py` 空文件 + 临时豁免流程
- T-006: ≥95% 必达, NFR-0010 豁免管理个别不可达

## 验证
- quote-check: is_ready=True, 0 blockers
- Lex stage 1: 5/5 PASS (25 FR/NFR, 178 AC)
- commit + push OK

## 后续
- Step 4: 加 anchor (spec.md + acceptance.md)
- Step 5: 创建 25 GitHub issues (英文 label)
- Step 6: record-lock
