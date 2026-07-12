# Codex 复核请求: v0.2-002-ui (Round 12)

## 项目背景
- 项目: Millionaire (量化交易平台, Python)
- Spec: v0.2-002-ui (Millionaire UI 前端)
- 仓库: github.com/zillionare/millionaire
- 当前分支: `releases/v0.2`
- 工作目录: `/Users/aaronyang/workspace/millionaire`

## M-SPEC 阶段已完成 (待 review 验证)

| 阶段 | commit | 状态 |
|---|---|---|
| M-FOUND | b40cd47..4a9cb59 | ✅ |
| 阶段 A (格式迁移) | 34119c3 | ✅ |
| Round 10 (codex v1 review) | 45d3458..c6415d5 | ✅ |
| Round 11 (codex v2 review) | a439339..f6731e6 | ✅ |
| Lex stage 1 | 5/5 PASS (214 ACs) | ✅ |
| Lex stage 2/3 | 工具 bug 阻塞 (中文 label / project.toml / --branch) | ⚠ |

## 这次 review 的范围 (4 个核心文件 + 3 个历史 review)

1. `.louke/project/specs/v0.2-002-ui/spec.md` (1869 行, 8 章, 45 FR/NFR)
2. `.louke/project/specs/v0.2-002-ui/acceptance.md` (713 行, 214 ACs, `### AC-N` heading 格式)
3. `.louke/project/specs/v0.2-002-ui/story.md` (296 行, 8 章)
4. 45 个 GitHub issues #133-#177 (通过 `gh issue list --repo zillionare/millionaire --state all --limit 100 --json number,title,body` 查)

**历史 review 文件 (作为上下文, 不需要重新提相同问题)**:
- `review-codex.md` (你第一轮 review, 4 P1 + 5 P2 + 5 P3, 已处理于 Round 10)
- `review-2026-07-04-independent.md` (GLM-5.2 review)
- `review-round-2.md` / `review-round-3.md` / `review-round-4.md` (其他匿名 reviewer)
- `review-codex-v0.2-002-ui-2026-07-08.md` (你第二轮 review, 3H + 4M, 已处理于 Round 11)

**raw 会话** (Round 10/11 决策记录):
- `.louke/raw/2026-07-08/maestro-v0.2-002-round-10-complete.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-10a1-ac-format.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-10a2-ac-format-fix.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-10b-codex-p1-2-3-4.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-10c-raw.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-10d-issues-rename.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-10e-lex-verify.md`
- `.louke/raw/2026-07-08/maestro-v0.2-002-codex-review-v2-received.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-11-codex-v2-review.md`

## 评审方法 (独立)

1. 通读 4 个核心文件
2. 抽样 3-5 个复杂 FR (如 FR-0180 无网关降级 / FR-0411 账户隐藏 / FR-0080 每日持仓 / FR-0460 init-wizard / FR-0420 实盘交易) 评估可实施性
3. 检查 spec ↔ acceptance ↔ issue 三方对齐
4. 抽样 5-10 个 issue body, 验证 schema 合规 (需求 ID / Spec 链接 / 验收标准字段)
5. 抽样 AC, 验证可被测试断言
6. 关注之前 review 没提的盲点

## 这次 review 重点

### 验证 Round 11 7 个问题真解决 (3H+4M)

| # | 问题 | 验证方法 |
|---|---|---|
| **H1** | 9 个 issue body "需求 ID" 字段 (FR-A110~A180 → FR-0110~0180, FR-D201~D203 → FR-0201~0203) | 查 #160-#170 body 确认 |
| **H2** | story §5.1.2 网关离线 (阻止提交, 不暂存) | 查 story line 188-195 措辞 |
| **H3** | FR-0390 表格行模型 (实盘总账户 + N 策略虚拟账户) | 查 spec FR-0390 + acceptance AC-4/5/6 |
| **M4** | 运行时实例生命周期 (状态机表) | 查 spec §2.3 子节 |
| **M5** | NFR-0070 活动账户定义 | 查 spec NFR-0070 |
| **M6** | init-wizard 路由 (redirect 单一路径) | 查 acceptance FR-0110 AC-1 |
| **M7** | AC heading 格式 (machine-stable) | 查 acceptance FR-0420 AC-13~16 |

### 关注 Round 11 引入的新问题

- Round 11 加的状态机表 (§2.3 运行时实例生命周期) 是否与 spec.md 其他章节一致
- Round 11 改的 NFR-0070 活动账户定义是否引入新语义
- Round 11 改的 story §5.1.2 是否与 spec/acceptance 完全一致

### 关注 M-SPEC 阶段整体可实施性

- spec 描述是否够明确, Devon 实施时不需猜测
- AC 是否可被 QA 验证
- 45 个 issues 能否作为实施单元 (issue 标题 + body 描述 + spec 锚点)

## 输出格式

写到 `review-codex-v0.2-002-ui-2026-07-08-round3.md` (同目录)

格式同前两轮:
- **Recommendation**: REQUEST CHANGES / APPROVE
- **Architectural status**: BLOCK / GO (与之前 v2 的 ARCHITECTURAL STATUS: BLOCK 对比)
- **Summary** (2-3 句话)
- **High Severity** (阻塞实施锁, 必修)
- **Medium Severity** (一致性/完整性)
- **Low Severity** (细节)
- **Positive Checks** (好的发现)
- **Final Recommendation**

## 重要约束

- **独立 review**: 不要直接相信 raw 会话里的结论, 独立判断
- **不要修改 spec.md / acceptance.md / story.md**: 只产出 review 文件
- **可以引用之前 review**: 标注 "类似 review-codex.md §X 的观察" 即可, 不要重复
- **Lex 工具 bug 已知**: 3 个工具 bug (中文 label / project.toml / --branch) 已知, 不需要列, 但**手动核实**数据 (用 gh 命令)

## 验证命令 (供参考, 自行调整)

```bash
# spec / acceptance / story 状态
cd /Users/aaronyang/workspace/millionaire
wc -l .louke/project/specs/v0.2-002-ui/{spec,acceptance,story}.md
git log --oneline -20

# 45 个 issues 标题格式
gh issue list --repo zillionare/millionaire --limit 50 --state open --json number,title --jq '.[] | "\(.number) \(.title)"'

# 验证 9 个 issue body 字段 (Round 11 High 1 修复)
for n in 160 161 162 163 164 165 166 168 169 170; do
  gh issue view $n --repo zillionare/millionaire --json body --jq '.body' | head -8
  echo "---"
done

# Lex stage 1 (本地)
~/.louke/venv/bin/python3 -m louke._tools.verify_acceptance --offline \
  --spec-file .louke/project/specs/v0.2-002-ui/spec.md \
  --acceptance-file .louke/project/specs/v0.2-002-ui/acceptance.md 2>&1 | head -10

# spec.md 章节结构
grep -E "^#{1,3} " .louke/project/specs/v0.2-002-ui/spec.md | head -30
```

## 评审后回报

- 关键发现 (High / Medium)
- 是否 APPROVE
- 如果 REQUEST CHANGES, 列最关键 1-3 项要修

---

**这是第 3 轮 codex review。前两轮发现了真问题, 这次重点确认 Round 11 是否真解决, 以及 M-SPEC 阶段是否准备好 lock.**
