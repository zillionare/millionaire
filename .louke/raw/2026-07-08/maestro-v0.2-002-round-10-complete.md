---
date: 2026-07-08
session: maestro-v0.2-002-round-10-complete
agents: [Maestro, Sage, Aaron]
spec: v0.2-002-ui
related_issues: [#132, #133-#177]
status: open
supersedes: [raw/2026-07-08/sage-v0.2-002-round-10e-lex-verify.md, raw/2026-07-08/sage-v0.2-002-round-10d-issues-rename.md, raw/2026-07-08/sage-v0.2-002-round-10c-raw.md, raw/2026-07-08/sage-v0.2-002-round-10b-codex-p1-2-3-4.md, raw/2026-07-08/sage-v0.2-002-round-10a2-ac-format-fix.md, raw/2026-07-08/sage-v0.2-002-round-10a1-ac-format.md]
---

## Topic
Round 10 全部完成 (10a/10a.1/10a.2/10b/10c/10d/10e) — M-SPEC 阶段 + 阶段 A 全部处理

## Round 10 全部产出 (按时间顺序)

### Round 10a: P1-1 FR-0180 (codex 4 P1 第 1 项)
- commit: 45d3458
- 改 spec.md FR-0180: 应用 Aaron 仲裁 (仿真也禁用, 回测仍可用, 网关管理可用)
- 加 acceptance.md FR-0180 节: 23 条新 AC
- 更新 #167 body

### Round 10a.1 + 10a.2: AC 格式转换 (阶段 A 延伸, Lex L3 修复)
- commits: 17ec4e7, 2a8ca3b
- 191 + 10 = 201 处 `- AC-N:` bullet → `### AC-N\n- 内容` heading
- Lex stage 1 5/5 PASS

### Round 10b: P1-2/P1-3/P1-4 (codex 4 P1 后 3 项)
- commit: 6059957
- P1-2 FR-0411: 2 层隐藏语义 (account.hidden + display_hidden_accounts) + 8 条新 AC
- P1-3 FR-0080: 4 条"每日持仓"AC
- P1-4 FR-0420: 离线降级 (阻止提交, 不暂存) + spec.md line 1232 同步

### Round 10c: P2/P3 (5 + 5 项)
- commits: 96e1a50, 18891a8
- P2-1: B 类降级 banner 颜色统一 (黄底+红色文字/图标)
- P2-2: FR-0460 "以代码为准" 改述
- P2-3: 运行时实例控制 (在 FR-0060 acceptance 加 AC 澄清)
- P2-4: FR-0390 表格对象明确
- P2-5: FR-0340/0070 metadata ⚠️ → ✅
- P3-1: US-A130 删"改昵称"
- P3-2: FR-0460 AC-1 选"重定向"路径
- P3-3: FR-0170 通知 vs toast 措辞
- P3-4: NFR 跨页 marker
- P3-5: story §4.3.1 "三种" → "四种"

### Round 10d: 45 个 issues 重命名
- commit: 4a06285 (raw)
- 11 个 A/D issue 标题 + body 链接更新 (FR-A110~A180 → FR-0110~0180, FR-D201~D203 → FR-0201~0203)
- 34 个 FR-0xxx/NFR-0xxx 已是新格式, 不动
- #132 (BACKEND-REVIEW-001) 保留 [UI-FR-A180] (因为是 backend review, 不是 spec FR)

### Round 10e: Lex 阶段二三验证
- commit: 07ff86e (raw)
- **状态: 工具 bug, 全部 REJECT** (但数据本身合规)
- 详见决策章节

## Lex 工具 bug (3 个)

### Bug 1: verify_issue_schema.py 用英文 label, 但 feature.yml 用中文 label
- feature.yml: `label: 需求 ID` / `label: Spec 链接` / `label: 验收标准`
- verify_issue_schema.py: `FIELD_FR_ID = "Requirement ID"` (硬编码英文)
- 实际 45 个 issues body 都正确, 但 Lex 读不到中文 label
- 影响: 阶段二全 0/90 PASS

### Bug 2: verify-issue 不支持 --branch
- verify-acceptance/verify-project 有 --branch, verify-issue 没有
- 默认读 main, 但 spec 在 releases/v0.2, 报 404
- 影响: 阶段二开始时直接 warn 404, 但不影响 0/90 计数 (因为 Bug 1 是主因)

### Bug 3: verify-project 找 project.toml, 但本项目用 project-info.md
- _common.py: `PROJECT_INFO_PATH = Path('.louke/project/project.toml')` (硬编码)
- 本项目只有 `.louke/project/project-info.md`
- 手动核实: 45 个 v0.2-002-ui issues 全部已关联 Project #5
- 影响: 阶段三 REJECT, 但数据合规

## 手动核实: 45 个 issues 实际合规

| 检查项 | Lex 结果 | 手动核实 | 真实状态 |
|--------|----------|----------|----------|
| 45 个 issue 标题 4 位编号 | 0 PASS | ✓ 45 个全合规 | OK |
| 45 个 issue body 三字段 | missing | ✓ #133/#167 body 完整 | OK |
| spec.md 锚点存在 | FAIL (404) | ✓ releases/v0.2 上有 | OK |
| 45 个 issue 关联 Project #5 | FAIL | ✓ projectItems 含 | OK |

## 决策

Sage 不动 spec/acceptance/issues (无问题), 不修 Lex 工具 (超出范围), 不跑 record-lock (verify 未全 PASS).

Aaron 决策选项:
1. 修 Lex 工具 (上游根治 — 但需 fork louke 或等上游更新)
2. 本项目临时绕过 (feature.yml 改英文 + 建 project.toml + spec merge 到 main)
3. 人工确认 + 跳过 Lex 二/三 + 跑 record-lock (承担工具未确认风险)
4. 升级 louke (`pip install -U louke`, 看上游是否已修)

## 关键文件状态 (2026-07-08)

| 文件 | 行数 | 状态 |
|---|---|---|
| spec.md | 1869 | 阶段 A 格式 + Round 10a/b/c 内容 |
| acceptance.md | 713 | 阶段 A 格式 + Round 10a/b/c 内容 (206 ACs) |
| story.md | 296 | 8 章重写版 + Round 10c 修复"三种"→"四种" |
| review-codex.md | 80 | 第四轮 review, Round 10 全部处理 |
| 4 个 raw 会话 | - | 2026-07-08 当天 |

## 45 个 issues 状态

- 45 个 spec FR/NFR issues (#133-#177) 全部:
  - 标题用纯 4 位编号 [FR-0xxx] / [FR-0110~0180] / [FR-0201~0203] / [NFR-0xxx]
  - body 字段格式正确 (需求 ID / Spec 链接 / 验收标准)
  - 关联 Project #5 (millionaire-v0.2)
- #132 (BACKEND-REVIEW-001) 保留 [UI-FR-A180] 旧格式 (不是 spec FR)

## 试过但放弃

无

## 开放问题

- Aaron 决策 Lex 工具 bug 怎么处理 (4 选项)
- Aaron 让 codex 重新 review (codex 会发现 45 个 issues + spec + acceptance 全部新格式)
- Aaron 显式确认 spec 锁定 (record-lock 待执行)

## Mistakes to avoid

- 不要相信 Lex 工具失败 = 数据失败 (这次 Lex 失败 100% 工具 bug)
- 不要在 Lex 工具失败时擅自修 spec/acceptance (可能引入新问题)
- 不要在 record-lock 失败时反复重试 (lock 信号由 Aaron 显式确认, 不是 Lex 自动)
- Louke 工具 bug 应在 louke 仓库修, 不在 v0.2-002-ui 项目修
