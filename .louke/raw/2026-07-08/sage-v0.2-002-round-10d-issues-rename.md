---
date: 2026-07-08
session: sage-v0.2-002-round-10d-issues-rename
agents: [Sage]
spec: v0.2-002-ui
related_issues: [#160, #161, #162, #163, #164, #165, #166, #167, #168, #169, #170]
status: resolved
supersedes: []
---

## Topic

Round 10d: 把 45 个 GitHub issues 中残留的 11 个 A/D 编号 issue 重命名为纯 4 位编号，并同步更新 body 里的 spec 链接 / AC 链接，让 issue 与 Round 10a/b/c 完成的 spec.md/acceptance.md 新 anchor 对齐。

背景：
- Round 10a/b/c 已完成 spec.md/acceptance.md 阶段 A 格式迁移（FR-A110 -> FR-0110, FR-D201 -> FR-0201 等）
- 但 45 个 GitHub issues 中仍残留 11 个 A/D 前缀 issue（#160~#170）
- 其他 34 个 issue（FR-0xxx + NFR-0xxx）本就使用纯 4 位编号，title + body 不动
- 本次严格只动 11 个 A/D issue，不动 spec.md/acceptance.md（那是 10a/b/c 的工作），不跑 Lex（留 10e）

## Decision

### 编号映射

**A 类 (8 个)**：
- `FR-A110` -> `FR-0110` (#160)
- `FR-A120` -> `FR-0120` (#161)
- `FR-A130` -> `FR-0130` (#162)
- `FR-A140` -> `FR-0140` (#163)
- `FR-A150` -> `FR-0150` (#164)
- `FR-A160` -> `FR-0160` (#165)
- `FR-A170` -> `FR-0170` (#166)
- `FR-A180` -> `FR-0180` (#167)

**D 类 (3 个)**：
- `FR-D201` -> `FR-0201` (#168)
- `FR-D202` -> `FR-0202` (#169)
- `FR-D203` -> `FR-0203` (#170)

### Body 链接替换规则

每个 issue body 含两个链接：
- Spec 链接: `...spec.md#fr-aXXX` -> `...spec.md#fr-0XXX` (或 `#fr-dXXX` -> `#fr-0XXX`)
- AC 链接: `...acceptance.md#ac-fr-aXXX` -> `...acceptance.md#ac-fr-0XXX` (或 `#ac-fr-dXXX` -> `#ac-fr-0XXX`)

### #167 特殊处理

#167 (FR-A180) 在 Round 10a 已被更新过 body（含 Aaron 的仲裁记录、23 条 AC 概览等），body 内链接已是 `#fr-0180` / `#ac-fr-0180` 新格式。本次只重命名 title：`[FR-A180] 功能降级` -> `[FR-0180] 功能降级`。

### 执行命令

用 `gh issue edit NUMBER --repo zillionare/millionaire --title "..." --body "..."` 批量更新。Python 脚本位于 `/tmp/rename_issues.py`。

### 更新结果

```
需要更新 11 个 issues
  #160: title + body  [FR-A110] -> [FR-0110] 启动路由分流
  #161: title + body  [FR-A120] -> [FR-0120] 单用户登录与会话
  #162: title + body  [FR-A130] -> [FR-0130] 登出与个人设置
  #163: title + body  [FR-A140] -> [FR-0140] 未登录访问重定向
  #164: title + body  [FR-A150] -> [FR-0150] 主界面布局
  #165: title + body  [FR-A160] -> [FR-0160] 告警中心入口与列表
  #166: title + body  [FR-A170] -> [FR-0170] UI 内通知 (toast / banner)
  #167: title only    [FR-A180] -> [FR-0180] 功能降级 (body 已是新格式)
  #168: title + body  [FR-D201] -> [FR-0201] 账户总览 (概览)
  #169: title + body  [FR-D202] -> [FR-0202] 数据/系统任务状态 (概览 底部)
  #170: title + body  [FR-D203] -> [FR-0203] 告警分类显示 (概览 顶部)

完成: 11 ok / 0 failed
```

### 验证

- `[FR-A` / `[FR-D` 开头 issue: **0 个** (全部已重命名)
- 11 个新 title 已生效 (#160~#170 全部用纯 4 位编号)
- 11 个 body 旧 A/D 链接全部清零 (0 个残留)
- 34 个 FR-0xxx + NFR-0xxx issue 未动 (本就是新格式)

### Spec/acceptance anchor 预检

更新前已验证 spec.md + acceptance.md 各 11 个新 anchor 全部存在（Round 10a/b/c 已写入）：
- spec.md: `fr-0110`, `fr-0120`, `fr-0130`, `fr-0140`, `fr-0150`, `fr-0160`, `fr-0170`, `fr-0180`, `fr-0201`, `fr-0202`, `fr-0203`
- acceptance.md: 对应 `ac-fr-0XXX` 各 11 个

链接不会断。

## Tried but abandoned

- **用 `gh api` 直接调 REST**：考虑过用 `gh api repos/.../issues/NUMBER -X PATCH -f title=... -f body=...`，但 `gh issue edit` 更直观且支持 `--title` + `--body` 一次性更新，选了后者。
- **逐个 issue 手动编辑**：11 个 issue 手动太慢且易错，写 Python 脚本批量处理更可靠，可重放。
- **在 10d 跑 Lex verify-issue**：原 prompt 提到"Lex 留 Round 10e"。严格遵守，本次不跑 Lex，留 Round 10e 做 stage 2 (verify-issue) + stage 3 (verify-project)。
- **修改 spec.md/acceptance.md**：本属于 Round 10a/b/c 的范围。本次严格只动 GitHub issues。

## Open questions

1. **Round 10e: Lex stage 2 (verify-issue) + stage 3 (verify-project)** - issues 重命名 + body 链接更新后，理论上 Lex verify-issue 应能全 PASS。需要跑一次确认。
   - 可能的失败点：
     - `#167` body 末尾"遗留"段落引用 `BACKEND-REVIEW-001` 和 issue `#132`，不算正式链接，应该不影响
     - `#151` (FR-0380) 和 `#145` (FR-0260) title 含 `[001-FR-380]` / `UI-FR-0010/0020/0040` 等 markdown 残留，但不属于本次范围（它们本就是 4 位编号）
2. **Round 10e 后是否还有 Round 10f**：取决于 Lex stage 2/3 是否全 PASS。若全 PASS 则可以走 record-lock 收尾；若有 fail 则需要 10f 修。

## Files

- `/tmp/rename_issues.py` - 批量重命名脚本（已执行完，临时文件）
- `/tmp/issues_before.json` - 更新前 issues 列表快照

## Notes

- 本次 commit 只 add raw 会话，不动 spec.md/acceptance.md
- Round 10a/b/c 的 spec/acceptance 改动已在 commit `86c02a6` 及之前 commit 中完成
- 项目状态: Lex stage 1 (verify-acceptance) 5/5 PASS，stage 2/3 待 10e 跑
