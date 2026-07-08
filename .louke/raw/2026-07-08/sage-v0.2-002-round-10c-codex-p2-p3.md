---
date: 2026-07-08
session: sage-v0.2-002-round-10c-codex-p2-p3
agents: [Maestro, Sage]
spec: v0.2-002-ui
related_issues: []
status: resolved
supersedes: [raw/2026-07-08/sage-v0.2-002-round-10b-codex-p1-2-3-4.md]
---

## Topic
Round 10c: 处理 codex review 中的全部 P2 (5 项) + P3 (5 项) 小修

## Decision

### spec.md 改动 (P2-2/4/5, P3-1/3/4, + P2-1 spec 侧)
- P2-1 (spec 侧): FR-0180 B 类降级 banner 描述统一 -- 黄色背景 + 红色 ⚠ 图标 + 红色文字 (非大面积红色); NFR-0030 "红色横幅告警" 改为 "横幅告警 (黄底+红色文字/图标)"; banner 留待 Round 10c 注释改为 "Round 10c 已统一"
- P2-2: FR-0460 "示例参考 (Aaron 例外约定)" 改为 "代码参考说明 (Aaron Round 10c 决策)" -- 代码仅作视觉/组件风格参考, 步骤与字段以 spec/acceptance 为准, 不照搬旧 6 步代码
- P2-4: FR-0390 表格对象明确 -- 实盘总账户 (固定首行, 不可点击) + N 行策略虚拟账户 (可点击); 按策略筛选时实盘总账户行不变; 隐藏账户不参与合计但 display_hidden_accounts=true 时灰色标注; 排序规则
- P2-5: FR-0340 元数据 ⚠️ -> ✅ (Aaron Round 5 Q1=A 已决); FR-0070 元数据 ⚠️ -> ✅ (Aaron Round 5 Q2 已决)
- P3-1: US-A130 story 文案 "改昵称/密码" -> "修改密码" (与 FR/AC 一致, 不支持改昵称)
- P3-3: FR-0170 下游联动 "通知服务的输出被 §2.1 FR-0160 告警中心聚合" -> "同一业务事件可同时触发 toast (FR-0170) 与告警中心记录 (FR-0160), 两者数据源独立, UI 各自分别呈现"
- P3-4: §3 末尾 (NFR-0070 之后, --- 之前) 加 NFR 测试场景 marker -- NFR-0050/0060/0070 的 AC 跨多页, 适合 test-plan §6 端到端场景, 当前 AC 是最小可断言要求

### acceptance.md 改动 (P2-1, P2-3, P3-2, + P2-1 NFR 侧)
- P2-1: FR-0180 AC-9 改为 "黄色 banner + 红色 ⚠ 图标 + 红色文字 (非大面积红色背景)"; AC-20 改为 "背景黄色, banner 内文字+图标用红色, 满足 NFR-0040 禁止大面积红色背景"; NFR-0030 AC-2 "红色横幅" -> "横幅 (黄底+红色文字/图标)"
- P2-3: FR-0060 加 AC-4 (运行时实例控制语义澄清) -- 停止不可重启 (需全新实例); 暂停=dry-run (可恢复); 重启仅指暂停后恢复, 不适用已停止实例. **未动 spec** (避免引入未编号 FR), 仅在 acceptance 加 AC
- P3-2: FR-0460 AC-1 "/dashboard 等页面无法访问" -> "尝试访问 /dashboard -> 重定向到 wizard 欢迎页 (即 / 路径)" (选定"重定向"为单一主路径, 不用 403)

### story.md 改动 (P3-5)
- §4.3.1 正文 "系统区分三种账户" -> "系统区分四种账户" (标题已是"四种账户", 正文原写"三种"却列出 4 类, 矛盾修复)

### Lex stage 1
- commit 前验证: 5/5 PASS (206 ACs, 45 FR/NFR 双向覆盖, AC 编号连续非空)

### Commits
- 96e1a50: spec: sage round 10c (codex P2/P3) -- spec.md + acceptance.md (commit-spec 工具自动提交, 不含 story.md)
- 18891a8: spec: sage round 10c story §4.3.1 三种->四种账户 (codex P3-5) -- story.md 单独提交 (commit-spec 工具不覆盖 story.md)

## Tried but abandoned
- P2-3 初始方案考虑在 spec.md §2.3 加新 "FR-XXXX 运行时实例控制" 节, 但会引入未编号 FR (破坏 FR 编号稳定性). **放弃**, 改为仅在 acceptance.md FR-0060 加 AC-4 澄清语义, 不动 spec 结构. 与 codex "补对应 AC 或回写 story" 建议一致 (选了"补 AC"路径)
- P3-5 task 描述里 "禁止做: 不动 story.md 内容文字 (只修标题)" 与 P3-5 detail "改正文" 表面冲突. 经分析: 标题已是"四种账户" (无需改), 矛盾点在正文写"三种"却列 4 类. 按 P3-5 detail 执行 (改正文), 这是更具体且分析正确的指令

## Open questions
- quote-check 仍有 39 个 OPEN 线程 (T-001~T-039), 这些是历史决策记录的 inline discussion, 非本 round 范围. Lock 阶段 (Step 6) 才需 quote-check exit 0
- 45 issues 重命名 (Round 10d) + Lex 阶段二三 (Round 10e) 留给后续 rounds
- test-plan 未动 (P3-4 仅留 marker, 实际 NFR 端到端场景由 Archer/Round 后续处理)

## Mistakes to avoid
- `lk agent sage commit-spec` 工具只提交 spec.md + acceptance.md, **不**含 story.md. 若 round 涉及 story.md 修改, 需单独 git commit + push
- Edit 工具对含 Unicode 箭头 `→` (U+2192) 的行匹配失败 (Read 显示为 `->` 但实际是单字符). 遇到此情况用 python3 脚本做字符串替换更可靠
- 文件中 `**bold**` markdown 标记 + 全角标点 + Unicode 箭头混合时, Edit 工具 oldString 易失配; 建议先用 `python3 -c "print(repr(line))"` 确认真实字符再编辑
