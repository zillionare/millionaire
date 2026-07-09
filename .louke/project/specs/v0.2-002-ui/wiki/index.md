---
spec: v0.2-002-ui
title: v0.2-002-ui Wiki 索引
description: 知识蒸馏索引 — v0.2-002-ui spec 全局概览、时间线、Lex状态
---

# v0.2-002-ui Wiki — 知识蒸馏索引

## Spec 概览

- **Spec ID**: v0.2-002-ui (用户界面与交互)
- **Spec 大小**: spec.md 1908 行 / acceptance.md 761 行
- **结构**: 8 章，45 FR/NFR（38 FR + 7 NFR），215 AC
- **上游**: v0.2-001-strategy-framework（策略框架/调度/数据/SDK）
- **创建日期**: 2026-06-17
- **状态**: M-MILESTONE 完成

## 章节结构

| 章节 | 内容 | 主要 FR |
|------|------|---------|
| §1.1 系统壳层与认证 | 启动路由/登录/主界面布局/告警中心入口/UI内通知 | FR-0110~0170 |
| §1.2 概览 | Dashboard 三区块（D203告警→D201账户→D202任务） | FR-0201~0203 |
| §1.3 策略 | 策略管理/回测/仿真与实盘/风控触发事件 | FR-0010~0013/0020/0040/0060~0093/0260/0370/0380 |
| §1.4 账户 | 账户总览/paper+live/账户管理 | FR-0390/0410/0411 |
| §1.5 交易 | 实盘/仿真交易界面/委托成交 | FR-0400/0420/0430 |
| §1.6 系统管理 | 任务调度/网关/数据校验/K线 | FR-0310/0320/0330 |
| §1.7 事件通知 | 微信二维码/IM/邮件订阅 | FR-0450 |
| §1.8 系统配置 | init-wizard 首次安装/失败恢复/重新配置 | FR-0460 |
| §3 NFR | 响应性/可访问性/错误降级/视觉规范/局部刷新/长任务/本地持久化 | NFR-0010~0070 |

## 时间线

| 日期 | 事件 | 关键产出 |
|------|------|---------|
| 2026-06-17 | spec v0.2-002-ui 起草 | 8章结构，45 FR/NFR |
| 2026-07-03 | story.md 重写 + kilo 归类重编号 | 270行，8章 |
| 2026-07-08 Phase A | 格式迁移（UI-FR-A110→FR-0110 等） | 11个A/D issue 重命名 |
| 2026-07-08 Round 10a | FR-0180 仲裁（仿真依赖gateway，A类降级时仿真不可用） | 新增23条AC |
| 2026-07-08 Round 10b | 网关离线措辞修正（订单不暂存） | — |
| 2026-07-08 Round 10c | codex P2/P3 5项小修（B类banner颜色等） | — |
| 2026-07-08 Round 10d | 11个issue A/D编号重命名 | #160~#170 全部4位编号 |
| 2026-07-08 Round 10e | Lex verify阶段二/三（发现3个工具bug） | 阶段一 5/5 PASS |
| 2026-07-08 Round 11 | codex v2 review 7个问题 | Lex stage 1 重验 5/5 PASS |
| 2026-07-08 Round 12 | codex recheck 第4轮 | — |
| 2026-07-08 Round 13 | codex v3 review（3 High + 4 Medium） | — |
| 2026-07-08 Round 13.5 | acceptance副作用修复（活动账户AC冲突） | — |
| 2026-07-09 Round 13.6 | 删除活动账户概念（Round 13引入作废） | — |
| 2026-07-09 Round 14 | codex 第4轮复核启动 | — |
| 2026-07-09 Round 15 | codex v4 5个修复（必选/可选区分等） | — |
| 2026-07-09 M-LOCK | Aaron显式确认 lock（跳过record-lock） | current_stage→M-LOCK |
| 2026-07-09 M-TESTPLAN | Archer 写 test-plan.md（231行，45/45覆盖） | commit 50bb6c9 |
| 2026-07-09 M-ARCH | Archer 写 architecture.md（327行）+ interfaces.md（294行） | commit 91edba6 |
| 2026-07-09 M-DEV | Devon 15个新commit，346 passed，≥95%覆盖率 | 累计31个v0.2-002-ui commits |
| 2026-07-09 M-E2E | Shield e2e测试（e2e_paper 35passed/e2e_gateway 7passed） | commit 227f99d |
| 2026-07-09 M-MILESTONE | Librarian 蒸馏wiki知识 | — |

## Lex 三信号状态

| 信号 | 状态 | 说明 |
|------|------|------|
| Lex stage 1 (verify-acceptance) | ✅ 5/5 PASS | 215 AC 全部合规 |
| Lex stage 2 (verify-issue) | ❌ 45 PASS / 45 FAIL | v0.2-001老issue路径不兼容Lex 0.7+ |
| Lex stage 3 (verify-project) | ❌ gh project failed | 空错误待查 |
| record-lock | ❌ 跳过 | Aaron显式确认，不阻塞主流程 |

## Louke 工具 Bug 状态

见 [lex-bugs.md](./lex-bugs.md)

## Wiki 子页面

- [decisions.md](./decisions.md) — Aaron 关键决策汇总（15项）
- [lex-bugs.md](./lex-bugs.md) — Louke 工具 bug 及 workaround（3项）
- [round-summary.md](./round-summary.md) — 各 round 总结（Phase A + Round 1~15 + M-SPEC→M-E2E）

## 不动

- ❌ spec/acceptance/test-plan/architecture/interfaces（M-SPEC 已 lock）
- ❌ 45 个 issues（M-SPEC 已 lock）
- ❌ `.louke/project/project.toml`（current_stage 已由 Aaron/Maestro 自己改）
- ❌ v0.2-001 老 issue 路径（Louke 0.7+ 不兼容，无解）
