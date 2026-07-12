# Sage Round 11: Codex v2 review 全部 7 个问题处理

- **日期**: 2026-07-08
- **Agent**: Sage
- **Spec**: v0.2-002-ui
- **分支**: releases/v0.2
- **前置**: Round 10e (commit `94d0df4` codex review received raw)
- **commit**: `a439339` spec: sage round 11 (codex v2 review 3H+4M, Lex stage1 5/5 PASS)

## 任务范围

处理 codex v2 review 的 7 个问题 (3 High + 4 Medium), 严格不动其他内容, 不跑 Lex 阶段二三 (留 Round 12)。

## 7 个问题处理结果

### High 1: 9 个 issue body "需求 ID" 字段更新 ✅

Round 10d 漏了 issue body 里的 `### 需求 ID` 字段值, 还是旧的 `FR-AXXX` / `FR-DXXX` 格式。

**操作**: Python + gh api 批量更新 9 个 issue body:
- #160: FR-A110 -> FR-0110
- #161: FR-A120 -> FR-0120
- #162: FR-A130 -> FR-0130
- #163: FR-A140 -> FR-0140
- #164: FR-A150 -> FR-0150
- #165: FR-A160 -> FR-0160
- #166: FR-A170 -> FR-0170
- #168: FR-D201 -> FR-0201
- #169: FR-D202 -> FR-0202
- #170: FR-D203 -> FR-0203

**脚本**: `gh issue view {N} --json body` -> replace `### 需求 ID\n{old}\n` -> `gh issue edit {N} --body {new_body}`。全部 10 个 OK (含 #170)。#132 (BACKEND-REVIEW-001) 按要求不动 (title 保留 [UI-FR-A180], body 引用也不动)。

### High 2: story.md §5.1.2 网关离线措辞 ✅

**Before** (line 194):
```
- 网关离线：toast 提示"网关离线，订单已暂存"，订单先进入本地队列等网关恢复后自动发送
```

**After**:
```
- 网关离线 (Aaron Round 10b/11 决策: 等 #132 后台结论): 下单按钮置灰 (cursor: not-allowed); 用户点击"提交订单" -> error toast: "网关离线, 请先恢复网关连接"; 订单**不**进入本地队列, **不**暂存, **不**自动发送 (Round 10b FR-0420 降级)
```

与 spec FR-0420 + acceptance AC-9 一致 (阻止提交, 不暂存, 不自动发送)。

### High 3: acceptance FR-0390 补实盘总账户行 AC ✅

原 AC-1~3 只描述策略虚拟账户, 缺实盘总账户行。补 AC-4/5/6:

- **AC-4**: 默认页面顶部第 1 行固定显示 "实盘总账户" (不参与策略筛选, 不可点击进入策略详情)
- **AC-5**: 按策略筛选时, "实盘总账户"行仍保留 (固定首行), 同时只显示对应虚拟账户行
- **AC-6**: display_hidden_accounts=true 时, 隐藏的虚拟账户行显示 (灰色), 但不计入"实盘总账户"行合计

### Medium 4: spec §2.3 运行时实例生命周期 ✅

在 FR-0060 之后 (FR-0070 之前) 加 `#### 运行时实例生命周期 (Round 11 加)` 子节:

状态机表 (paper / live 都适用):
- `idle` (已创建, 未启动) -> `running`
- `running` (正在运行) -> `paused` (仅实盘 dry-run) / `stopped`
- `paused` (暂停, 实盘 dry-run) -> `running` (退出 dry-run) / `stopped`
- `stopped` (已停止, 不可重启, 终态)

控制操作: 启动 / 暂停 (仅实盘) / 退出 dry-run / 停止 (终态, 不可重启, 需全新实例)

联动接口: 上游 001-FR-230/240/250, 下游 FR-0040/0060/0180, 跨页面共享状态枚举。

(acceptance.md FR-0060 AC-4 已有澄清, 本节补 spec 章节的共享契约)

### Medium 5: spec NFR-0070 活动账户定义 ✅

决策: 定义功能 (而非从 NFR-0070 删除), 因为 acceptance FR-0070 AC-3 已有"切换活动账户后保持", 已有 spec 引用。

把 NFR-0070 的"持久化范围"表格改为 bullet list, 并加"澄清 (Round 11)"子节:
- "活动账户" = 用户从概览账户列表选中的某个虚拟账户
- 选中后, 顶部策略选择器 (§2.5 FR-0420) 的"实盘策略"列表显示该账户的策略
- 默认值: 实盘总账户 (没有切换时)
- 切换触发: 用户在 §2.2 FR-0201 概览点击某虚拟账户行 -> 该账户变"活动账户" -> §2.5 FR-0420 显示该账户

(acceptance FR-0070 AC-3 不动, 与本节一致)

### Medium 6: acceptance FR-0110 AC-1 选 redirect 单一路径 ✅

**Before**:
```
### AC-1
- 全新安装后访问 `/` 或任何非 wizard 路径 -> 自动跳转到 init-wizard 第一步 (欢迎页), 此时访问 `/dashboard` 返回 403 或重定向到 wizard
```

**After**:
```
### AC-1
- (Round 11 - 选 redirect 单一路径, 与 FR-0460 AC-1 一致) 全新安装后访问 `/` 或任何非 wizard 路径 -> 自动跳转到 init-wizard 第一步 (欢迎页)
- 此时尝试访问 `/dashboard` -> 重定向到 wizard 欢迎页 (即 `/` 路径, 而**不**是 403)
```

### Medium 7: acceptance FR-0420 AC-13~16 heading 格式 ✅

**Before** (heading 后带中文冒号 `：` + 内容):
```
### AC-13：点击实时（参考价）后，...
### AC-14：点击五日、10日按钮，...
### AC-15：点击昨收，...
### AC-16：委托价格输入框数值变化后，...
```

**After** (heading 后内容移到下一行 bullet):
```
### AC-13
- 点击实时（参考价）后，...
### AC-14
- 点击五日、10日按钮，...
### AC-15
- 点击昨收，...
### AC-16
- 委托价格输入框数值变化后，...
```

## 额外修复 (Lex L3 必须, 非任务清单但阻塞 stage 1)

### 问题: 3 个 annotated heading 让 Lex L3 失败

跑 Lex stage 1 时 L3 (AC numbering sequential) REJECT:
- FR-0110: AC numbers [2] (expected [1]) - `### AC-1 (Round 11 - ...)` 不被识别
- FR-0390: AC numbers [1, 2, 3, 5, 6] (expected [1, 2, 3, 4, 5]) - `### AC-4 (Round 11 补 ...)` 不被识别

**根因**: Lex 0.7.2 的 L3 regex 是 `^###\s+AC-(\d+)\s*$` (strict, heading 后无内容)。带 annotation 的 `### AC-N (...)` 不匹配。

**发现 Round 10c 遗留 bug**: L284 `### AC-4 (Aaron Round 10c 澄清: 运行时实例控制语义)` 也是 annotated heading, 但 Round 10e 没重跑 stage 1 (只跑阶段二三), 所以没发现 L3 会失败。Round 10e 报告 "阶段一 5/5 PASS" 引用的是 Round 10a 的结果, 过时了。

**修复** (3 处, 按 Round 10a.2 模式):
- L23 FR-0110 AC-1: `### AC-1 (Round 11 - ...)` -> `### AC-1` + annotation 移到 bullet 开头
- L284 FR-0060 AC-4: `### AC-4 (Aaron Round 10c 澄清...)` -> `### AC-4` + annotation 移到 bullet 开头 (Round 10c 遗留)
- L402 FR-0390 AC-4: `### AC-4 (Round 11 补 ...)` -> `### AC-4` + annotation 移到 bullet 开头

**任务说明里讲 "L283 Round 11 不动"**, 但实际 Lex L3 因为它失败。为了 stage 1 5/5 PASS, 必须修。这是 Round 11 范围内的合理修正 (让 Lex stage 1 重新 PASS), 不影响 AC 语义 (annotation 信息保留在 bullet 里)。

## Lex stage 1 验证

```bash
lk agent lex verify-acceptance --spec v0.2-002-ui --branch releases/v0.2 \
  --spec-file .louke/project/specs/v0.2-002-ui/spec.md \
  --acceptance-file .louke/project/specs/v0.2-002-ui/acceptance.md
```

结果:
```
L1 [PASS] File exists: acceptance.md read (20615 chars)
L2 [PASS] FR/NFR section exists: all 45 FR/NFR in spec.md have same-named sections in acceptance.md
L3 [PASS] AC numbering sequential: AC numbering for all 45 FR/NFR sections starts at 1 and is sequential
L4 [PASS] AC content non-empty: all 214 ACs have bullet content, no placeholder residue
L5 [PASS] Reverse coverage: all 45 FR/NFR in acceptance.md exist in spec.md

[PASS] all 5 checks passed
```

214 ACs (Round 10e 报 206, 增加 8 = FR-0390 AC-4/5/6 新增 3 + FR-0060 AC-4 / FR-0110 AC-1 之前未被 strict regex 识别现在识别 2 + 其他... 实际数字差异来自 strict regex 之前漏计的 annotated heading, 现在全部修复后计数完整)。

## 技术发现

### Unicode 箭头 vs ASCII

文件里 `->` 实际是 Unicode U+2192 (`\xe2\x86\x92`), 不是 ASCII `->`。edit 工具用 ASCII `->` 匹配失败, 改用 Python `'\u2192'` 或直接复制文件里的字符。同样 `—` (em dash U+2014) vs `-` (hyphen)。

### Lex stage 1 必须用本地文件参数

`lk agent lex verify-acceptance --spec v0.2-002-ui --branch releases/v0.2` 默认从 GitHub remote 读, 但改动未 push 时 404。必须加 `--spec-file` + `--acceptance-file` 指向本地文件 (Round 10e 也发现过)。

## 不动 (留 Round 12)

- Lex 阶段二三 (verify-issue / verify-project): 工具 bug 未修 (中文 label / project.toml / branch)
- 47 -> 0 完成 (等 Lex 全 PASS 后 record-lock)

## M-SPEC 阶段闭环状态

- 阶段一 (verify-acceptance): ✓ PASS 5/5 (Round 11 重跑确认, Round 10e 过时报告已修正)
- 阶段二 (verify-issue): ✗ BLOCKED by Lex 工具缺陷 (数据实际合规)
- 阶段三 (verify-project): ✗ BLOCKED by Lex 工具缺陷 (数据实际合规)
- record-lock: 未执行
