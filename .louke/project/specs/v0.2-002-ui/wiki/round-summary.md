---
spec: v0.2-002-ui
title: Round 总结
description: Phase A + Round 10a~15 + M-SPEC→M-E2E 各阶段详细总结
---

# v0.2-002-ui — 各 Round 总结

## Phase A: 格式迁移（2026-07-08）

### 任务
将 v0.2-002-ui spec.md/acceptance.md 从旧格式（UI-FR-A110 / A/D 字母编号 / 旧 inline-discussion 协议）迁移到 Louke 0.7.2 Lex 期望格式。

### 改动
- `UI-FR-A110` → `FR-0110`（A→01xx）
- `UI-FR-D201` → `FR-0201`（D→02xx）
- `UI-NFR-0010` → `NFR-0010`（drop UI-）
- 锚点重编号（`fr-a110` → `fr-0110` 等）
- 删 16 条旧 `> 状态:` 协议行
- 修复 `**Speaker:**` → `**Speaker**:`（colon outside）
- 修复 `**Aaron:*` → `**Aaron**:`（typo）

### 结果
- spec.md: 38 FR + 7 NFR = **45** FR/NFR（was 0，Lex 现在能检测到）
- acceptance.md: **44** FR/NFR（A180 在"No Acceptance"）
- `lk discuss --check-ready`: 37 threads，T-001~T-037（全部 open，历史遗留）
- Lex verify-acceptance: **spec 45 FR/NFR 检测到**（重大进展）

### 未解决（Phase A 范围外）
1. A180（FR-0180）无专属 AC 节 → Round 10a 处理
2. acceptance.md 用 `- AC-N:` bullet 而非 `### AC-N` heading → Phase B
3. 37 threads 需加 `[resolved]` 标记 → content work

### 证据

> "Phase A mechanical format conversion to Louke 0.7.2 Lex-expected format"  
> `sage-v0.2-002-phase-A-format-migration.md`

---

## Round 10a — FR-0180 仲裁 + 23 条 AC 新增（2026-07-08）

### 任务
修复 FR-0180（原 A180）无网关降级内容矛盾，应用 Aaron 仲裁"如果 gateway 没有连接，那么仿真就不可用"。

### 关键决策（D-002）
> "Aaron Round 10a 仲裁: 仿真也依赖 gateway, A 类降级 (无网关) 时仿真应 disable, 与实盘一致。回测不依赖 gateway, 仍可用."

### 改动
1. spec.md FR-0180：删旧错误描述（"启动仿真仍可用"），新增回测可用、仿真/实盘入口 disable
2. acceptance.md：新增 FR-0180 独立 AC 节（23条AC，分4组：A类8条/B类4条/转换规则4条/UI表现7条）
3. issue #167 body 更新（A180→FR-0180，链接同步）

### 结果
- Lex stage 1 L2 REJECT（A180 在"No Acceptance"）→ 新增 AC 节后修复
- commit `45d3458`

### 证据

> `sage-v0.2-002-round-10a-fr-0180.md`

---

## Round 10b — Codex P1~P4（部分）

### 任务
codex 第 1 轮 review P1~P4。

### 主要改动
- FR-0180 B 类降级 banner 颜色统一（黄色背景+红色⚠+红色文字）
- 其他 P1~P4 问题修复

### 证据

> `sage-v0.2-002-round-10b-codex-p1-2-3-4.md`（已被 Round 10c supersedes）

---

## Round 10c — Codex P2/P3 5项小修（2026-07-08）

### 5项改动

| # | 改动 | 内容 |
|---|------|------|
| P2-1 | B类banner颜色统一 | 黄底+红色文字/图标（非大面积红色） |
| P2-2 | wizard示例参考措辞 | "代码参考说明"替代"例外约定" |
| P2-4 | FR-0390表格语义明确 | 实盘总账户固定首行+隐藏账户规则 |
| P2-5 | 元数据标记 | FR-0340/FR-0070 ⚠️→✅ |
| P3-1 | story修改密码措辞 | "改昵称/密码"→"修改密码" |
| P3-3 | 通知联动语义 | toast与告警中心数据源独立 |
| P3-4 | NFR测试场景marker | §3末尾加marker |
| P3-5 | story四种账户 | 正文"三种"→"四种" |

### 关键决策（D-010, D-012, D-013, D-014, D-019）

### 额外：FR-0060 AC-4 运行时实例语义
> "停止不可重启（需全新实例）；暂停=dry-run（可恢复）；重启仅指暂停后恢复，不适用已停止实例"  
> `sage-v0.2-002-round-10c-codex-p2-p3.md` line 27

### 结果
- commit `96e1a50`（spec+acceptance）+ `18891a8`（story.md）
- Lex stage 1: 5/5 PASS（206 ACs）

### 证据

> `sage-v0.2-002-round-10c-codex-p2-p3.md`

---

## Round 10d — 11个Issue A/D编号重命名（2026-07-08）

### 任务
把 45 个 GitHub issues 中残留的 11 个 A/D 前缀 issue 重命名为纯 4 位编号。

### 8个A类 + 3个D类
- `FR-A110`→`FR-0110` (#160) ... `FR-A180`→`FR-0180` (#167)
- `FR-D201`→`FR-0201` (#168) ... `FR-D203`→`FR-0203` (#170)

### 结果
- 0个 `[FR-A` / `[FR-D` 残留
- 11个 body 旧 A/D 链接全部清零
- commit `4a06285`

### 证据

> `sage-v0.2-002-round-10d-issues-rename.md`

---

## Round 10e — Lex 阶段二/三验证 + Bug 发现（2026-07-08）

### Lex 结果
- **stage 1**: 5/5 PASS（Round 10a 新增 AC 节后修复 A180 L2 问题）
- **stage 2 (verify-issue)**: 0/90 PASS → 发现 3 个 Louke 工具 bug（#93/#94/#95）
- **stage 3 (verify-project)**: REJECT（project.toml 缺失）

### 3个Louke工具Bug
1. **#93**: 中文 label 不支持（wont-fix）
2. **#94**: `--branch` 不支持（后由 louke 0.7.5 修）
3. **#95**: `project.toml` 硬编码（wont-fix）

### record-lock
未执行（verify 未全 PASS）

### 证据

> `sage-v0.2-002-round-10e-lex-verify.md`

---

## Round 11 — Codex v2 Review 7个问题（2026-07-08）

### 7个问题

| 级别 | 问题 | 处理 |
|------|------|------|
| H1 | 9个issue body "需求ID"字段仍是旧A/D格式 | Python+gh api批量更新 |
| H2 | story §5.1.2 网关离线措辞 | 改为不暂存（Aaron Round 10b/11决策） |
| H3 | acceptance FR-0390缺实盘总账户行AC | 新增AC-4/5/6 |
| M4 | spec运行时实例生命周期 | 加子节（Round 11） |
| M5 | NFR-0070活动账户定义 | 加澄清子节 |
| M6 | FR-0110 AC-1 redirect单一路径 | 选redirect（不是403） |
| M7 | FR-0420 AC-13~16 heading格式 | 改为heading后内容移下一行 |

### Lex stage 1 重验
**5/5 PASS**（214 ACs）

### 关键发现
> "Round 10e 报告'阶段一 5/5 PASS'是过时的"（引用的是 Round 10a 结果，未重跑）  
> `sage-v0.2-002-round-11-codex-v2-review.md` line 131

### 证据

> `sage-v0.2-002-round-11-codex-v2-review.md`

---

## Round 12 — Codex Recheck 第4轮（2026-07-08）

### 任务
codex 第 4 轮复核。

### 证据

> `sage-v0.2-002-round-14-codex-recheck4.md`（Round 14 prompt 启动）

---

## Round 13 — Codex v3 Review（2026-07-08）

### 任务
处理 codex v3 review 3 High + 4 Medium。

### 证据

> `sage-v0.2-002-round-13-codex-v3.md`

---

## Round 13.5 — Acceptance副作用修复（2026-07-08）

### 3个副作用

| # | 副作用 | 处理 |
|---|--------|------|
| 1 | NFR-0070 AC-3仍说"活动账户持久化" | 删AC-3，改AC-4/5/6→AC-3/4/5 |
| 2 | FR-0201 AC-2跳转vs AC-3选中冲突 | 单击=选中（高亮+pointer），双击=跳转 |
| 3 | FR-0420 AC-1+AC-2a合并 | AC-1合并，AC-2a删除 |

### Lex stage 1
**5/5 PASS**（216 ACs after NFR-0070 -1 numeric）

### 关键发现
> "第一次commit把'(Round 13.5 修订)'注释写到 `### AC-N` 标题行 → Lex L3 REJECT（严格正则不匹配带括号的标题）→ 修复commit把注释移到首个bullet"  
> `sage-v0.2-002-round-13-5-acceptance-sideeffects.md` line 63-66

### 证据

> `sage-v0.2-002-round-13-5-acceptance-sideeffects.md`

---

## Round 13.6 — 删除活动账户（D-003）（2026-07-09）

### 任务
完全删除"活动账户"概念（Round 13 引入的 active_account_id spec 作废）。

### 删除范围
- spec.md: 5处（FR-0201整段/FR-0420整段/NFR-0070澄清/章节映射表/glm提示）
- acceptance.md: 4处（FR-0201 AC-2回退/AC-3~5删/FR-0420 AC-1/NFR-0070注释）

### 结果
- `grep "活动账户\|active_account"` → **0 结果** ✓
- commit `513c95e`
- AC: 216 → ~213（-3）

### 关键决策（D-003）

### 证据

> `sage-v0.2-002-round-13-6-remove-active-account.md`

---

## Round 14 — Codex 第4轮复核启动（2026-07-08）

### 任务
启动 codex 第 4 轮复核（Round 13+13.5 后）。

### 证据

> `sage-v0.2-002-round-14-codex-recheck4.md`

---

## Round 15 — Codex v4 5个修复（2026-07-09）

### 5个改动

| # | 级别 | 改动 |
|---|------|------|
| H2 | High | story §8.2 必选/可选区分 |
| H3 | High | skipped-step banner关闭后不显示（D-005） |
| M4 | Medium | 下载进度skip语义（必选父步骤/子任务可延后）（D-009） |
| M5 | Medium | 回退Round 13 M6（仿真账户name+本金接受）（D-006） |
| L6 | Low | stale引用修复（活动账户残留） |

### 关键决策（D-006, D-007, D-008, D-009）

### 实盘总账户本金编辑入口（D-007）
> "编辑入口放在 §2.5 FR-0420 trade页（无策略选中时，顶部账户信息卡片右侧'编辑本金'按钮）+ §2.6 FR-0340 网关管理页（顶部'实盘总账户'行右侧编辑按钮）"  
> `sage-v0.2-002-round-15-codex-v4-5fixes.md` line 64

### 证据

> `sage-v0.2-002-round-15-codex-v4-5fixes.md`

---

## M-SPEC → M-LOCK（2026-07-09）

### Stage 转移
- **M-SPEC**: spec lock（8 rounds codex review + Lex stage 1 5/5 PASS）
- **M-LOCK**: Aaron显式确认 lock（跳过 record-lock）

### record-lock 阻塞
1. v0.2-001 老issue路径不兼容 Lex 0.7+（不可解）
2. #94（--branch，已在 louke 0.7.5 修）
3. #93/#95（wont-fix）

### 证据

> `maestro-v0.2-002-stage-m-lock.md`

---

## M-TESTPLAN（2026-07-09）

### 产出
- `test-plan.md`（231行，45/45 FR/NFR覆盖）
- commit `50bb6c9`

### 风险项（test-plan §6）
1. 视觉颜色断言（跨浏览器/主题）
2. gateway状态时序（本地gateway vs 远程QMT）
3. SSE vs WebSocket（选型未最终确认）
4. 异步长任务（回测/下载进度）
5. 图表hover交互（Playwright断言）
6. 跨浏览器/标签页localStorage状态

### 证据

> `maestro-v0.2-002-stage-m-testplan.md` + `sage-v0.2-002-m-testplan-archer.md`

---

## M-ARCH（2026-07-09）

### 产出
- `architecture.md`（327行，4个mermaid图，8章模块）
- `interfaces.md`（294行，62路由，39个001-FR引用，7个schema）
- commit `91edba6`

### 技术栈
- FastHTML + MonsterUI + Tushare + qmt-gateway
- 错误处理 + 降级架构
- 安全模型（单用户，本地部署）

### 证据

> `maestro-v0.2-002-stage-m-arch.md`

---

## M-DEV（2026-07-09）

### Devon 产出
- 15个新commit（12 green + 3 refactor）
- 累计31个v0.2-002-ui commits
- 346 passed（单元测试）
- 新增模块覆盖率全部≥95%

### 15个新做FR/issue

| # | Issue | 模块 |
|---|-------|------|
| 1 | #161 FR-0120 | auth_session.py |
| 2 | #145 FR-0260 | scheduling.py |
| 3 | #151 FR-0380 | backtest_charts.py |
| 4 | #171 NFR-0010 | nfr_responsive.py |
| 5 | #172 NFR-0020 | nfr_accessibility.py |
| 6 | #173 NFR-0030 | nfr_error_degradation.py |
| 7 | #174 NFR-0040 | nfr_visual.py |
| 8 | #175 NFR-0050 | nfr_partial_refresh.py |
| 9 | #176 NFR-0060 | nfr_long_task.py |
| 10 | #177 NFR-0070 | local_storage.py |
| 11 | #150 FR-0370 | backtest_charts.py（续） |
| 12-14 | #161/#174/#177 | 3个refactor commit |

### 不在范围
- 现有大页面（home.py/accounts.py/strategy.py/init_wizard.py）视觉重构
- L2集成测试/L3 Playwright e2e

### 证据

> `sage-v0.2-002-m-dev-devon.md`

---

## M-E2E（2026-07-09）

### Shield 产出
- `tests/e2e/`（smoke/paper/gateway/live_smoke scaffold）
- commit `227f99d`

### 测试结果
- e2e_paper: 4个新测试，35 passed + 2 xfailed
- e2e_gateway: 3个新测试，7 passed
- e2e_live_smoke: 1个 scaffold（Windows+QMT真机，默认deselect）

### 兼容性修复
- `daily_bars` fixture loading
- `VirtualClock.advance_to_next_frame()` date frame normalization

### 证据

> `sage-v0.2-002-m-e2e-shield.md` + `maestro-v0.2-002-stage-m-e2e-done.md`

---

## M-MILESTONE 完成状态

| 项目 | 状态 |
|------|------|
| spec.md | 1908行，45 FR/NFR，locked |
| acceptance.md | 761行，215 AC，locked |
| test-plan.md | 231行，45/45覆盖 |
| architecture.md | 327行，4 mermaid |
| interfaces.md | 294行，62路由 |
| Lex stage 1 | ✅ 5/5 PASS |
| record-lock | ❌ 跳过（v0.2-001路径不兼容） |
| M-DEV commits | 31个（含15个本次） |
| 单元测试 | 346 passed，≥95%覆盖 |
| e2e测试 | 42 passed + 2 xfailed |
| wiki | index/decisions/lex-bugs/round-summary |
