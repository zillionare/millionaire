---
date: 2026-07-08
session: sage-v0.2-002-round-13-codex-v3
agents: [Maestro, Sage, Aaron]
spec: v0.2-002-ui
related_issues: []
status: resolved
supersedes: [raw/2026-07-08/sage-v0.2-002-round-12-codex-recheck.md]
---

## Topic
Round 13: codex 第 3 轮 review 7 个问题 (1H+5M+1L) 全部处理

## Decision
- 7 项全部按 Aaron 决策实施
- Lex stage 1 5/5 PASS (215 ACs, Round 11 207 +8)

## 7 项处理

| # | 项 | 处理 | commit |
|---|---|---|---|
| High 1 | FR-0390 acceptance 行模型 | 5 条 AC 重写 | f93223e |
| Medium 2 | NFR-0070 活动账户 | 移到 FR-0201/FR-0420 | f93223e |
| Medium 3 | story §3.3 仿真暂停 | 改"只能停止" | f93223e |
| Medium 4 | story §8 数据源 | Tushare+网关分开 | f93223e |
| Medium 5 | NFR-0060 进度模型 | 拆 5/5b/5c | f93223e |
| Medium 6 | story §4.3.2 转入字段 | name/本金 移 001 | f93223e |
| Low 7 | FR-0420 trade 按钮颜色 | 金融域例外声明 | f93223e |

## Round 13 引入的 3 个副作用 (待 Round 13.5 修)

1. **NFR-0070 AC-3 仍说"活动账户持久化"** — 与 NFR-0070 范围新定义 (3 项, 无活动账户) 矛盾
2. **FR-0201 AC-2 跳转详情 vs AC-3 选中活动账户** — 单击行为语义冲突 (需明确: 单击=选中, 双击=跳转)
3. **FR-0420 AC-2a vs AC-1** — AC-1"买入" 按钮置灰与 AC-2a 列表显示 在无活动账户时需协调

## Open questions
- Aaron 是否需要让 codex 第 4 轮 review (Round 14)
- 3 个副作用是先修还是让 codex 找
- Round 14 决策: codex 仍 REQUEST CHANGES, 还是 APPROVE

## Mistakes to avoid
- Sage 范围严格"不动 acceptance" 留下副作用, Round 14 应一并处理
- Codex review 准确: "Fix the FR-0390 row model first, then close the medium contract gaps" — 都做了
- Louke 工具 bug 仍未修, Lex stage 2/3 阻塞