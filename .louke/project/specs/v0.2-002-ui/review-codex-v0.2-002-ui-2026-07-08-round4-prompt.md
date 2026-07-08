# Codex 复核请求: v0.2-002-ui (Round 14, 第 4 轮)

## 项目背景
- 项目: Millionaire (量化交易平台, Python)
- Spec: v0.2-002-ui (Millionaire UI 前端)
- 仓库: github.com/zillionare/millionaire
- 当前分支: `releases/v0.2`
- 工作目录: `/Users/aaronyang/workspace/millionaire`
- 最新 commit: `ad62534` (Round 13.5 fix AC heading format)

## M-SPEC 阶段已完成 (待 4 轮 review 验证)

| 阶段 | commit | 状态 |
|---|---|---|
| M-FOUND | b40cd47..4a9cb59 | ✅ |
| 阶段 A (格式迁移) | 34119c3 | ✅ |
| Round 10 (codex v1 review) | 45d3458..c6415d5 | ✅ |
| Round 11 (codex v2 review) | a439339..f6731e6 | ✅ |
| Round 13 (codex v3 review) | f93223e..8395665 | ✅ |
| Round 13.5 (副作用修复) | 4deb1f5..ad62534 | ✅ |
| Lex stage 1 | 5/5 PASS (214 numeric + 2 letter-suffix ACs) | ✅ |
| Lex stage 2/3 | 工具 bug 阻塞 (3 个 Louke bug) | ⚠ |

## 这次 review 的范围 (4 个核心文件 + 3 个历史 review + raw)

1. `.louke/project/specs/v0.2-002-ui/spec.md` (1869 行, 8 章, 45 FR/NFR)
2. `.louke/project/specs/v0.2-002-ui/acceptance.md` (~22274 字节, 214+ ACs, `### AC-N` heading 格式)
3. `.louke/project/specs/v0.2-002-ui/story.md` (296 行, 8 章)
4. 45 个 GitHub issues #133-#177 (通过 `gh issue list --repo zillionare/millionaire` 查)

**历史 review (4 轮 codex + 1 轮 GLM-5.2 + 3 轮匿名)**:
- `review-codex.md` (第 1 轮, 4P1+5P2+5P3, 已处理于 Round 10)
- `review-2026-07-04-independent.md` (GLM-5.2)
- `review-round-2.md` / `review-round-3.md` / `review-round-4.md` (匿名)
- `review-codex-v0.2-002-ui-2026-07-08.md` (第 2 轮, 3H+4M, 已处理于 Round 11)
- `review-codex-v0.2-002-ui-2026-07-08-round3.md` (第 3 轮, 1H+5M+1L, 已处理于 Round 13 + 13.5)

**raw 会话** (Round 10-13.5 决策记录):
- `.louke/raw/2026-07-08/maestro-v0.2-002-round-10-complete.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-10a1-ac-format.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-10a2-ac-format-fix.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-10b-codex-p1-2-3-4.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-10c-raw.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-10d-issues-rename.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-10e-lex-verify.md`
- `.louke/raw/2026-07-08/maestro-v0.2-002-codex-review-v2-received.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-12-codex-recheck.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-13-codex-v3.md`
- `.louke/raw/2026-07-08/sage-v0.2-002-round-13-5-acceptance-sideeffects.md`

## 评审方法 (独立)

1. 通读 4 个核心文件
2. 抽样 3-5 个复杂 FR (如 FR-0180 / FR-0201 / FR-0390 / FR-0411 / FR-0420 / FR-0460) 评估可实施性
3. 检查 spec ↔ acceptance ↔ issue 三方对齐 (重点 FR-0390 两套模型已合并, FR-0201 单击行为明确, FR-0420 无活动账户行为)
4. 验证 Round 13 + 13.5 真的解决了 Round 13 提的 7 个问题 + 3 个副作用
5. 找新问题 (重点 story vs spec 一致性: story §3.3 / §8 / §4.3.2 都改了)
6. 抽样 5-10 个 issue body 验证 schema 合规

## 重点验证

### Round 13 7 个问题真解决 + Round 13.5 3 个副作用真修

| # | 项 | 验证 |
|---|---|---|
| **High 1** | FR-0390 acceptance 重写 | 查 spec.md + acceptance.md FR-0390, 应统一为"实盘总账户首行 + N 策略虚拟账户行" |
| **Medium 2** | NFR-0070 活动账户移到 FR-0201/FR-0420 | 查 NFR-0070 (无活动账户) + FR-0201 AC-2 (单击=选中) + FR-0420 AC-1 (无活动账户时列表显示+按钮置灰) |
| **Medium 3** | story §3.3 仿真只能停止 | 查 story line 80 措辞 |
| **Medium 4** | story §8 Tushare+网关分开 | 查 story line 264 措辞 |
| **Medium 5** | NFR-0060 进度模型拆 3 项 | 查 acceptance NFR-0060 AC-5/5b/5c |
| **Medium 6** | story §4.3.2 简化 | 查 story §4.3.2 (name/本金 移 001) |
| **Low 7** | FR-0420 trade 按钮例外声明 | 查 spec §2.5 FR-0420 加的"交易按钮颜色例外"段 |
| 副作用 1 | NFR-0070 AC-3 删活动账户 | 查 acceptance NFR-0070 (应 5 AC, 不含活动账户) |
| 副作用 2 | FR-0201 单击=选中, 双击=跳转 | 查 acceptance FR-0201 AC-2 |
| 副作用 3 | FR-0420 AC-1 协调 | 查 acceptance FR-0420 AC-1 (启动时按活动账户分支) |

### 关注 M-SPEC 整体可实施性

- spec 描述是否够明确, Devon 实施时不需猜测
- AC 是否可被 QA 验证
- 45 个 issues 能否作为实施单元
- **M-SPEC 阶段是否准备好 lock**

## 输出格式

写到 `review-codex-v0.2-002-ui-2026-07-08-round4.md` (同目录, 后缀 -round4)

格式同前几轮:
- **Recommendation**: REQUEST CHANGES / APPROVE
- **Architectural status**: BLOCK / GO (这次重点关注是否 GO)
- **Summary** (2-3 句话)
- **High Severity** (阻塞实施锁, 必修)
- **Medium Severity** (一致性/完整性)
- **Low Severity** (细节)
- **Positive Checks** (好的发现)
- **Final Recommendation**

## 重要约束

- **独立 review**: 不要直接相信 raw 会话里的结论, 独立判断
- **不要修改 spec.md / acceptance.md / story.md / issues**: 只产出 review 文件
- **可以引用之前 review**: 标注 "类似 review-codex-v0.2-002-ui-2026-07-08.md §X 的观察" 即可, 不要重复
- **Lex 工具 bug 已知**: 3 个工具 bug (中文 label / project.toml / --branch) 已知, 不需要列, 但**手动核实**数据 (用 gh 命令)

## 验证命令 (供参考, 自行调整)

```bash
cd /Users/aaronyang/workspace/millionaire

# spec / acceptance / story 状态
wc -l .louke/project/specs/v0.2-002-ui/{spec,acceptance,story}.md
git log --oneline -20

# 45 个 issues 标题格式
gh issue list --repo zillionare/millionaire --limit 50 --state open --json number,title --jq '.[] | "\(.number) \(.title)"'

# Lex stage 1 (本地)
~/.louke/venv/bin/python3 -m louke._tools.verify_acceptance --offline \
  --spec-file .louke/project/specs/v0.2-002-ui/spec.md \
  --acceptance-file .louke/project/specs/v0.2-002-ui/acceptance.md 2>&1 | head -10

# 关键章节
grep -E "^#{1,3} " .louke/project/specs/v0.2-002-ui/spec.md | head -30
grep -E "^## " .louke/project/specs/v0.2-002-ui/acceptance.md | head -50
```

## 评审后回报

- 关键发现 (High / Medium)
- **是否 APPROVE** (M-SPEC 阶段是否准备好 lock)
- 如果 REQUEST CHANGES, 列最关键 1-3 项要修

---

**这是第 4 轮 codex review. 前 3 轮发现真问题, 这次重点是验证 13+13.5 全部产出 + M-SPEC 阶段 lock 决策.**
