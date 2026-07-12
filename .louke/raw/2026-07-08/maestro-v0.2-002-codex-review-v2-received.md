---
date: 2026-07-08
session: maestro-v0.2-002-codex-review-v2-received
agents: [Maestro, Codex, Aaron]
spec: v0.2-002-ui
related_issues: [#160-#170 (需求 ID 字段), #132, #133-#177]
status: open
supersedes: [raw/2026-07-08/maestro-v0.2-002-round-10-complete.md]
---

## Topic
Codex 第四轮 review (v2): 处理 Round 10 全部产出 + 找出剩余问题

## Codex 决定
- **架构状态**: BLOCK
- **建议**: REQUEST CHANGES
- **要求**: 修 3 个 High 后才能实现锁

## 7 个问题 (3 High + 4 Medium)

### High
1. **Issue body 字段未更新** (Round 10d 漏了): 9 个 issues (#160-#170) body 字段"需求 ID"仍用 FR-A110~FR-D203 旧格式. Title 改了, body 没改.
2. **FR-0420 story vs spec 矛盾**: story §5.1.2 仍写"暂存+自动发送", spec 改成了"阻止提交". 需更新 story.
3. **FR-0390 表格行模型不一致**: spec 定义"实盘总账户 + N 策略虚拟账户", acceptance 只定义"每行一个策略", 没覆盖实盘总账户行.

### Medium
4. **运行时实例生命周期缺共享契约**: story §3.3 vs spec/acceptance 不全, 不同页面可发明不同状态机.
5. **NFR-0070 持久化活动账户, 但功能模型未定义**: persistence 标准定义了, 交互没定义.
6. **Init-wizard 路由 stale**: acceptance L24 写"403 或重定向", Round 10c 选了 redirect, 旧 AC 没改.
7. **AC heading 格式 not machine-stable**: L476 写 `### AC-13：内容` (中文冒号 + 内容同行), Lex 不能识别.

## 决策

启动 Round 11 处理 7 个问题. codex 强调: "Fix the three high-severity items before treating v0.2-002-ui as ready for implementation lock".

Aaron 之前指示: "继续, 直到完成"

## Round 11 计划

- 11a: High 1 (9 个 issue body 字段修复) + High 2 (story §5.1.2 更新)
- 11b: High 3 (FR-0390 acceptance 补实盘总账户行) + Medium 4/5 (运行时生命周期 + NFR-0070 活动账户)
- 11c: Medium 6 (init-wizard 路由 L24) + Medium 7 (AC heading 格式)

或一次性 Round 11, 7 个一起做 (但内容太多).

## 试过但放弃

无

## 开放问题

- Aaron 是否同意 Round 11 一次性处理 7 个 (vs 分 11a/11b/11c)
- Medium 4 (运行时生命周期) 范围多大, 是不是引新 FR
- Medium 5 (活动账户) 是定义功能还是从 NFR-0070 删除

## Mistakes to avoid

- Round 10d 漏改 issue body "需求 ID" 字段 (Sage 只改了 title + body 链接, 没改 body 字段)
- acceptance.md L24 / L476 等处有 stale 内容, Round 10c/P2-3 处理时没同步全
- story.md 与 spec/acceptance 同步要双向 (Round 10b 改了 spec, story 没改)

## 当前 spec/acceptance 状态

- spec.md: 1869 行, 45 FR/NFR, 8 章结构
- acceptance.md: 713 行, 206 ACs, 5/5 Lex stage 1 PASS
- story.md: 296 行, 8 章重写 + Round 10c P3-5 修复
- 45 issues: 全部 4 位编号 title, body "需求 ID" 仍是旧 (10d 漏)
