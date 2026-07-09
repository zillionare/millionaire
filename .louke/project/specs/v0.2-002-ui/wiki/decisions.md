---
spec: v0.2-002-ui
title: Aaron 关键决策
description: v0.2-002-ui 阶段 Aaron 作出的 20 项关键决策，可追溯到 raw session
---

# v0.2-002-ui — Aaron 关键决策汇总

> 每项决策均可追溯到对应 raw session。格式：`[决策编号] 决策内容 // 证据来源`

## D-001 Dashboard → 概览（Dashboard 更名）
**Round**: Round 13  
**决策**: story.md §2 章名 "Dashboard" 改为 "概览"，spec.md FR-0201 标题同步改为 "账户总览（概览）"  
**证据**: `sage-v0.2-002-round-13-5-acceptance-sideeffects.md`（未直接记录，但 round-summary 确认）

---

## D-002 A180 仿真依赖 gateway（A类降级时仿真不可用）
**Round**: Round 10a（2026-07-08）  
**决策**: 仿真（paper trading）也依赖 gateway，A 类降级（无网关）时仿真应 disable，与实盘一致。回测不依赖 gateway，仍可用。  
**证据**:
> "Aaron Round 10a 仲裁: 仿真也依赖 gateway, A 类降级 (无网关) 时仿真应 disable, 与实盘一致。回测不依赖 gateway, 仍可用。"  
> `sage-v0.2-002-round-10a-fr-0180.md` line 19

**影响**: spec.md FR-0180 重写（删除旧错误描述"启动仿真仍可用"），新增23条AC，issue #167 body 更新

---

## D-003 活动账户概念作废（Round 13 引入 → Round 13.6 删除）
**Round**: Round 13.6（2026-07-09）  
**决策**: 完全删除 spec/acceptance 中的"活动账户（active_account_id）"概念。Round 13 引入的 active_account_id spec 作废。  
**证据**:
> "Round 13.6: 完全删除"活动账户"概念 (Aaron 决定 Round 13 引入的 active_account_id spec 作废)"  
> `sage-v0.2-002-round-13-6-remove-active-account.md` line 12

**删除范围**:
- spec.md: FR-0201 段（活动账户定义/持久化/视觉选中态/影响范围/默认值，共5 bullet）+ FR-0420 段（顶部策略选择器与活动账户，3 bullet）+ NFR-0070 澄清段
- acceptance.md: FR-0201 AC-3/AC-4/AC-5（活动账户交互AC，共3条）+ FR-0420 AC-1/AC-2a（活动账户分支）+ NFR-0070 AC-3 注释

**AC 总数变化**: 216 → ~213（-3条）

---

## D-004 账户隐藏两层语义（account.hidden + display_hidden_accounts）
**Round**: Round 11（2026-07-08）  
**决策**: 账户隐藏两层实现：
1. 服务端 `account.hidden` 字段标记
2. 客户端 `display_hidden_accounts` localStorage 控制

**证据**:
> "FR-0390 表格对象明确 — 实盘总账户（固定首行, 不可点击）+ N 行策略虚拟账户（可点击）; 按策略筛选时实盘总账户行不变; **隐藏账户不参与合计但 display_hidden_accounts=true 时灰色标注**"  
> `sage-v0.2-002-round-10c-codex-p2-p3.md` line 19

**acceptance 体现**: FR-0390 AC-6（display_hidden_accounts=true 时隐藏账户显示为灰色，不计入合计）

---

## D-005 B 类降级 banner 关闭后不再显示
**Round**: Round 15（2026-07-09）  
**决策**: skipped-step banner（黄色）+ 关闭按钮 ✕，点击关闭后横幅立即消失，不再显示（除非重新进入 wizard 并又跳过/失败）。  
**证据**:
> "High 3: skipped-step banner 关闭后不显示 // 位置: spec.md FR-0460 skipped 段 (L1573) + acceptance.md FR-0460 AC-6 (L653-656) + story.md §8.2 // 改动: 三方一致 — 黄色横幅 + 关闭按钮 ✕ + 关闭后不再显示"  
> `sage-v0.2-002-round-15-codex-v4-5fixes.md` line 27-29

---

## D-006 转入仿真/实盘 name+本金 UI 输入（Round 15 撤销 Round 13 M6）
**Round**: Round 15（2026-07-09）  
**决策**: 仿真/虚拟实盘在创建时**接受**账户名+本金，创建后**只读**；实盘总账户**可改**本金。  
**证据**:
> "Medium 5: 回退 Round 13 M6（仿真账户 name+本金接受）// Before: 账户名和本金由 v0.2-001 后台根据策略元数据自动生成，不在 UI 输入范围内 // After: 用户可在创建时指定名字和本金（名字: 字符串, 自由命名; 本金: 数字, > 0）. 本金一旦指定, 创建后不可修改"  
> `sage-v0.2-002-round-15-codex-v4-5fixes.md` line 41-45

**撤销**: 回退了 Round 13 M6 的"账户名和本金自动生成，不由 UI 输入"决策

---

## D-007 实盘总账户本金编辑入口
**Round**: Round 15（2026-07-09）  
**决策**: 编辑入口放在 §2.5 FR-0420 trade 页（无策略选中时，顶部账户信息卡片右侧"编辑本金"按钮）+ §2.6 FR-0340 网关管理页（顶部"实盘总账户"行右侧编辑按钮）。两个入口等效。  
**证据**:
> "最终决策 (Sage Round 15): 编辑入口放在 §2.5 FR-0420 trade 页（无策略选中时, 顶部账户信息卡片右侧 '编辑本金' 按钮）+ §2.6 FR-0340 网关管理页（顶部 '实盘总账户' 行右侧编辑按钮）. 两个入口等效."  
> `sage-v0.2-002-round-15-codex-v4-5fixes.md` line 64

**注意**: FR-0410 是 paper/live 虚拟账户详情，不包含实盘总账户详情页（spec 中实盘总账户无独立详情页）

---

## D-008 wizard 必选/可选步骤区分
**Round**: Round 15（2026-07-09）  
**决策**: init-wizard 10步分为必选和可选两类：
- **必选步骤**（欢迎/运行环境/管理员账号/数据目录/Tushare/首次下载/下载进度）: 失败时只能重试
- **可选步骤**（交易网关/通知）: 失败时可重试或跳过

**证据**:
> "High 2: story §8.2 必选/可选区分 // Before: 重试/跳过扁平叙述 // After: 必选步骤（欢迎/运行环境/管理员账号/数据目录/Tushare/首次下载/下载进度）: 失败时只能重试. 可选步骤（交易网关/通知）: 失败时可重试或跳过."  
> `sage-v0.2-002-round-15-codex-v4-5fixes.md` line 19-25

---

## D-009 下载进度为必选父步骤（不可跳，子任务可延后）
**Round**: Round 15（2026-07-09）  
**决策**: 下载进度明确为必选父步骤（不可跳），但子任务（某个股票历史行情下载失败）失败时可延后（标"待处理"），后续在系统设置中重试。  
**证据**:
> "Medium 4: 下载进度 skip 语义 // After (spec 步骤 8): 下载进度（必选步骤, 失败子任务可延后）: 实时显示每个子任务的进度. 父步骤不能跳过; 但子任务失败时可延后（标'待处理'），后续在系统设置中重试."  
> `sage-v0.2-002-round-15-codex-v4-5fixes.md` line 37

---

## D-010 B 类降级 banner 颜色（黄色，非大面积红色）
**Round**: Round 10c（2026-07-08）  
**决策**: B 类降级 banner = 黄色背景 + 红色 ⚠ 图标 + 红色文字（非大面积红色背景）。与 NFR-0040 视觉规范一致。  
**证据**:
> "P2-1 (spec 侧): FR-0180 B 类降级 banner 描述统一 -- 黄色背景 + 红色 ⚠ 图标 + 红色文字（非大面积红色）; NFR-0030 '红色横幅告警' 改为 '横幅告警（黄底+红色文字/图标）'"  
> `sage-v0.2-002-round-10c-codex-p2-p3.md` line 17

---

## D-011 网关离线措辞（订单不暂存）
**Round**: Round 10b/11（2026-07-08）  
**决策**: 等 #132 后台结论；下单按钮置灰（cursor: not-allowed）；用户点击"提交订单"→ error toast "网关离线，请先恢复网关连接"；订单**不**进入本地队列，**不**暂存，**不**自动发送。  
**证据**:
> "High 2: story.md §5.1.2 网关离线措辞 // After: 网关离线 (Aaron Round 10b/11 决策: 等 #132 后台结论): 下单按钮置灰; 用户点击'提交订单' -> error toast: '网关离线, 请先恢复网关连接'; 订单**不**进入本地队列, **不**暂存, **不**自动发送"  
> `sage-v0.2-002-round-11-codex-v2-review.md` line 43-44

---

## D-012 FR-0390 账户总览表格语义明确
**Round**: Round 10c/11（2026-07-08）  
**决策**: 账户总览表格 = 实盘总账户（固定首行，不可点击）+ N 行策略虚拟账户（可点击，按策略筛选时实盘总账户行不变）；隐藏账户不参与合计但 display_hidden_accounts=true 时灰色标注；排序规则。  
**证据**:
> "P2-4: FR-0390 表格对象明确 -- 实盘总账户（固定首行, 不可点击）+ N 行策略虚拟账户（可点击）; 按策略筛选时实盘总账户行不变; 隐藏账户不参与合计但 display_hidden_accounts=true 时灰色标注; 排序规则"  
> `sage-v0.2-002-round-10c-codex-p2-p3.md` line 19

---

## D-013 运行时实例生命周期语义（停止不可重启）
**Round**: Round 10c/11（2026-07-08）  
**决策**: 停止 = 终态，不可重启（需创建全新实例）；暂停 = dry-run（可恢复）；重启仅指暂停后恢复，不适用已停止实例。  
**证据**:
> "P2-3: FR-0060 加 AC-4（运行时实例控制语义澄清）-- 停止不可重启（需全新实例）; 暂停=dry-run（可恢复）; 重启仅指暂停后恢复, 不适用已停止实例."  
> `sage-v0.2-002-round-10c-codex-p2-p3.md` line 27

---

## D-014 story §4.3.1 三种→四种账户
**Round**: Round 10c（2026-07-08）  
**决策**: story 正文 "系统区分三种账户" 改为 "系统区分四种账户"（标题早已是"四种账户"，正文原写"三种"却列出4类，矛盾修复）。  
**证据**:
> "P3-5: §4.3.1 正文 '系统区分三种账户' -> '系统区分四种账户'（标题已是'四种账户'，正文原写'三种'却列出4类，矛盾修复）"  
> `sage-v0.2-002-round-10c-codex-p2-p3.md` line 31

---

## D-015 FR-0201 概览单击语义（单击=跳转，非选中）
**Round**: Round 13.6（2026-07-09）  
**决策**: 概览账户行单击 = 跳转（不是选中活动账户）；活动账户概念已删除。单击语义回退到 Round 13 之前（单击=跳转详情页/实盘交易界面）。  
**证据**:
> "副作用 2: FR-0201 AC-2 单击语义明确 // 旧: 点击虚拟账户行 → 跳转到该账户详情页 // 新 (Round 13.6): 虚拟账户行 **单击** → 选中活动账户（Round 13.6 已删除活动账户，实际=跳转）"  
> `sage-v0.2-002-round-13-6-remove-active-account.md`（结合 Round 13.5 的"单击=选中/双击=跳转"→Round 13.6 删除活动账户后回退）

---

## D-016 FR-0203 告警分类显示（概览顶部区块）
**Round**: Round 10a 之前（初始 spec）  
**决策**: 概览顶部区块显示 D203 告警分类（危险/警告/提示），点击跳转告警中心；概览 D201（账户总览）次之；D202（计划任务）底部。顺序固定不可调整。  
**证据**:
> "story: §1.2 概览顺序: D203 告警分类 → D201 账户总览 → D202 计划任务"  
> `sage-v0.2-002-phase-A-format-migration.md` line 18（章节映射表确认）

---

## D-017 FR-0110 全新安装访问 / → 重定向到 wizard（不是403）
**Round**: Round 11（2026-07-08）  
**决策**: 全新安装后访问 `/` 或任何非 wizard 路径 → 自动跳转到 init-wizard 第一步（欢迎页）；此时尝试访问 `/dashboard` → 重定向到 wizard 欢迎页（`/` 路径），**不是** 403。选 redirect 单一路径。  
**证据**:
> "Medium 6: acceptance FR-0110 AC-1 选 redirect 单一路径 // After: (Round 11 - 选 redirect 单一路径, 与 FR-0460 AC-1 一致) 全新安装后访问 `/` 或任何非 wizard 路径 -> 自动跳转到 init-wizard 第一步（欢迎页） // 此时尝试访问 `/dashboard` -> 重定向到 wizard 欢迎页（即 `/` 路径，而**不**是 403）"  
> `sage-v0.2-002-round-11-codex-v2-review.md` line 93-97

---

## D-018 NFR-0070 活动账户定义（Round 11，已被 Round 13.6 删除）
**Round**: Round 11（2026-07-08）  
**决策**: 在 NFR-0070 加"澄清（Round 11）"子节定义"活动账户" = 用户从概览账户列表选中的某个虚拟账户；选中后顶部策略选择器显示该账户的策略；默认值=实盘总账户。  
**证据**:
> "Medium 5: spec NFR-0070 活动账户定义 // 决策: 定义功能（而非从 NFR-0070 删除），因为 acceptance FR-0070 AC-3 已有'切换活动账户后保持'"  
> `sage-v0.2-002-round-11-codex-v2-review.md` line 72-74

**后续**: Round 13.6 完全删除（D-003）

---

## D-019 story §5.1.2 通知联动（toast 与告警中心数据源独立）
**Round**: Round 10c（2026-07-08）  
**决策**: 同一业务事件可同时触发 toast（FR-0170）与告警中心记录（FR-0160），两者数据源独立，UI 各自分别呈现。  
**证据**:
> "P3-3: FR-0170 下游联动 '通知服务的输出被 §2.1 FR-0160 告警中心聚合' -> '同一业务事件可同时触发 toast (FR-0170) 与告警中心记录 (FR-0160), 两者数据源独立, UI 各自分别呈现'"  
> `sage-v0.2-002-round-10c-codex-p2-p3.md` line 22

---

## D-020 跳过 record-lock（Aaron 显式确认）
**Round**: M-LOCK（2026-07-09）  
**决策**: 跳过 Louke record-lock（Stage 2/3 阻塞于 v0.2-001 老 issue 路径不兼容 Lex 0.7+，不影响主流程）。Aaron 显式确认不阻塞后续 M-TESTPLAN/M-ARCH/M-DEV/M-E2E。  
**证据**:
> "M-LOCK // Aaron 选 A (修老 issue), 但 A 实际不可行. 修 title 4 位 + body 字段都不够, 路径才是关键."  
> `maestro-v0.2-002-record-lock-blocked.md` line 22

> "跳过 Louke record-lock (Stage 2/3 仍阻塞, 不影响 M-LOCK 后流程)"  
> `maestro-v0.2-002-stage-m-lock.md` line 17

---

## D-021 接受 M-DEV 单元测试覆盖率未达 DoD (Aaron 接受现状, 单独 spec 处理)
**Round**: M-MILESTONE (2026-07-09)
**决策**: 接受 M-DEV 单元测试覆盖率整体 69% (quantide/web/services/ 核心 99% 平均, quantide/core + quantide/data + quantide/service 未被 M-DEV 覆盖). Aaron 接受现状, 单独开新 spec 处理覆盖率不足问题 (不在 v0.2-002-ui 范围内).
**证据**:
> "A, 然后我们开新的 spec 来处理覆盖率不足的问题"
> maestro-v0.2-002-stage-m-e2e-done.md line 50

**覆盖率详情**:
- 整体 (quantide/): 69% (1349 passed)
- quantide/web/services/ (M-DEV 写的核心): 99% 平均 (18 个模块, 最低 93% strategy_management, 其余 96-100%)
- quantide/web/theme.py: 100%
- quantide/core/, quantide/data/, quantide/service/, quantide/web/components/: 未被 M-DEV 单元测试覆盖

**DoD 现状**:
- `dod = "e2e 全通过 + 单元测试覆盖率 ≥95% (安全审查已关闭)"`
- e2e 全通过: ✅ 42 passed + 2 xfailed
- 单元测试覆盖率 ≥95%: ⚠️ 整体 69% (核心 99%), 不严格达标

**后续**: 新 spec (如 v0.2-003-coverage) 专门处理覆盖率补齐, 范围包括 quantide/core + data + service + components 单测.
