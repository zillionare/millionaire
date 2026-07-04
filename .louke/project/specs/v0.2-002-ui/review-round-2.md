# v0.2-002-ui 第二轮 Review (2026-07-04)

> **触发**: Aaron 要求评估 UI 样式/字体/色彩是否符合一般设计标准（红色为系统主题色，强调按钮文字使用红色，但不大面积使用），并对 Sage 修改后的 spec.md / acceptance.md / story.md 做新一轮 review。
>
> **范围**: spec.md (1428 行) + acceptance.md (348 行) + story.md (296 行) + UI-NFR-0040 视觉规范重点评估。
>
> **方法**: 与 Material Design / Ant Design / Bootstrap 5 / 8pt grid system / WCAG AA 通用设计标准对比；并复检上一轮 22 个问题（6S+11M+5L）的修复情况，识别 Sage 修改引入的新问题。

---

## 第一部分: UI 设计标准评估 (Aaron 提出的问题)

### 1.1 字体大小 — ✅ 符合一般设计标准

| 当前 spec 层级 | 字号        | Ant Design 对应     | Material Design 对应  | 评估                           |
| -------------- | ----------- | ------------------- | --------------------- | ------------------------------ |
| 页面标题       | 24px / 粗体 | Heading 3 (24px)    | Headline Small (24px) | ✓                              |
| 节标题         | 18px / 中粗 | Heading 5 (16-18px) | Title Large (22px)    | ✓                              |
| 段落正文       | 14px / 常规 | Body (14px)         | Body Medium (14px)    | ✓                              |
| 表格/列表      | 13px / 常规 | Table (14px)        | — (略小)              | △ 略小，但数据密集型场景可接受 |
| 辅助说明       | 12px / 浅灰 | Caption (12px)      | Label Small (11px)    | ✓                              |

**结论**: 字号层级 24/18/14/13/12 形成合理递减，符合 Ant Design/Material Design 主流规范。13px 用于表格在量化数据密集场景属常见取舍，可保留。

### 1.2 间距 — ✅ 完全符合 8pt grid system

`8px 基准网格 (4/8/16/24/32)` 是业界公认标准 (Material Design 8dp、Ant Design 8px、Bootstrap 5 $spacer 0.25rem)。**无需调整**。

### 1.3 圆角 — ✅ 符合主流

`按钮 4px / 卡片 8px / Modal 12px` 递进合理，与 Ant Design (默认 6px / 8px)、Material Design (4dp / 8dp / 12dp) 一致。

### 1.4 色彩 — ⚠️ 部分与 Aaron 决策冲突，需修正

#### 符合标准的部分
- **语义色彩 5 色** (成功绿/错误红/警告黄/提示蓝/中性灰) — 与 Ant Design / Bootstrap 5 语义色完全对齐
- **WCAG AA 对比度** — 符合可访问性国际标准

#### 与 Aaron 决策冲突的部分 ⚠️

Aaron 决策原文:
> 按钮强调时，文字使用红色这是我的决定，红色是这个系统的主题色 -- 但是，因为这种颜色太抢眼，所以不能大面积使用。

当前 [spec.md#UI-NFR-0040](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/spec.md) 第 1177-1181 行按钮规范:

```
- 主操作 (启动/确认): 实心背景色 + 白字 + 圆角
- 次操作 (取消/返回): 描边 + 文字色 + 圆角
- 危险操作 (删除/停止): 红色描边或红色背景  ← 与 Aaron 决策冲突
- 禁用: 灰色, 鼠标 cursor: not-allowed
```

**冲突点 1**: "危险操作 红色背景" → 大面积使用红色，违反 Aaron "不能大面积使用" 约束。
**冲突点 2**: "主操作 实心背景色" → 未明确颜色。按 Aaron 决策不能是红色，但 spec 没说是什么色，缺失关键信息。
**冲突点 3**: 未体现 Aaron "按钮强调时文字使用红色" 这条决策 — 当前规范完全没提到"强调文字用红色"。

#### 与 Aaron 决策冲突的延伸问题

[UI-FR-A170](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/spec.md) 第 359-364 行通知表:

```
| error | 操作失败 | toast 红色 (顶部居中) | 不自动消失 | 必须手动关闭 |
```

"toast 红色" 含义模糊: 是背景红、文字红、还是边框红？按 Aaron "红色不大面积使用" 决策，应该是**文字红/边框红/图标红**，而非背景红。spec 需明确。

### 1.5 改进建议 (UI-NFR-0040 重写建议)

```markdown
- **按钮风格**:
  - 主操作 (启动/确认): 实心背景 (中性深色或品牌色, 非红色) + 白字 + 圆角
  - 次操作 (取消/返回): 描边 + 文字色 + 圆角
  - 危险操作 (删除/停止): 红色描边 + 红色文字 (不使用红色背景, 避免大面积红色)
  - 强调按钮文字: 关键操作文字可用红色 (Aaron 决策: 红色为系统主题色)
  - 禁用: 红色描边 + 红色文字 (不使用红色背景, 避免 cursor: not-allowed
- **红色使用边界** (Aaron 决策):
  - 允许: 错误文字提示 / 状态徽章 / 危险操作描边 / 强调按钮文字 / 图标
  - 禁止: 大面积背景 (按钮背景 / Modal 背景 / banner 背景 / toast 背景)
```

UI-FR-A170 error toast 应改为: "toast: 白底 + 红色边框 + 红色文字 + 红色 ✕ 图标"。

---

## 第二部分: 上一轮问题修复复检

### 2.1 已修复 (11 项) ✅

| 编号 | 问题                                          | 修复方式                                       | 验证 |
| ---- | --------------------------------------------- | ---------------------------------------------- | ---- |
| S1   | story §1.4 告警入口位置 "中部" vs spec "右侧" | story.md 第 42 行改为 "header 中的 alert icon" | ✓    |
| S3   | 缺网关管理 FR                                 | 新增 UI-FR-0340 (spec.md 1037-1045)            | ✓    |
| S4   | 缺网关降级 FR                                 | 新增 UI-FR-A180 (spec.md 384-401)              | ✓    |
| S5   | UI-NFR-0020 键盘导航矛盾                      | 删除 "键盘导航", 仅保留 WCAG AA                | ✓    |
| S6   | UI-FR-0460 AC 矛盾 (重试 vs 跳过)             | 重写为必选项/可选项区分 (spec.md 1111-1116)    | ✓    |
| M1   | 推送机制模糊                                  | Aaron 澄清 "实施阶段决定"                      | ✓    |
| M2   | dry-run 核心行为未定义                        | "不再发出新订单" 已加 (spec.md 657)            | ✓    |
| M3   | 单日志删除重复                                | 单日志删除已删除, UI-FR-0093 简化              | ✓    |
| M4   | 联动总表不完整                                | §5 总表已补全含所有 FR                         | ✓    |
| M10  | 尾 Aaron quote 重复                           | 已删除                                         | ✓    |
| M11  | Sage default 状态                             | 改为 "⚠ pending Aaron confirm"                 | ✓    |
| L1   | FR 编号不统一                                 | 已统一 4 位                                    | ✓    |

### 2.2 未修复 (5 项) ❌

#### M5: UI-FR-0420 AC-3 速算价与 spec 不一致 ❌

[acceptance.md 第 223 行](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/acceptance.md):
```
AC-3: 下单表单参考价可选 昨收 / 5 日均线 / 实时价; 选中昨收时下方显示"±1% / ±2% / ±3%" 涨跌速算价按钮
```

但 spec.md UI-FR-0420 (第 919 行附近) 描述为 "12 档涨跌速算价"。**acceptance.md 需同步为 12 档**。

#### M6: UI-FR-A120 AC-3 仍写 "24 小时" ❌

[acceptance.md 第 29 行](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/acceptance.md):
```
AC-3: 登录成功后保持会话 24 小时不操作也不自动登出 (验证"不做超时自动登出"约束)
```

spec.md UI-FR-A120 (第 269 行) 明确写 "不做超时自动登出"。**acceptance.md "24 小时" 表述误导，应改为 "长期不操作也不自动登出"**。

#### M7: UI-FR-0450 AC-1 "5 分钟" 无来源 ❌

[acceptance.md 第 279 行](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/acceptance.md):
```
AC-1: ... 有效期例如 5 分钟
```

spec.md UI-FR-0450 未定义二维码有效期。**acceptance.md 不能引入 spec 未定义的数值**。要么 spec 补充有效期定义，要么 acceptance.md 删除 "5 分钟"。

#### M8: UI-FR-0430 AC-3 "不校验风控目标" 无来源 ❌

[acceptance.md 第 237 行](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/acceptance.md):
```
AC-3: 提供"补单"入口 ... 补单流程与实盘下单表单一致但不校验风控目标
```

spec.md UI-FR-0430 (第 991 行附近) 未提"不校验风控目标"。**acceptance.md 不能引入 spec 未定义的约束**。需要 Aaron 决策补单是否校验风控。

#### M9: UI-FR-0460 AC-2/AC-3 未同步新 spec 流程 ❌

[acceptance.md 第 292-293 行](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/acceptance.md):
```
AC-2: 按引导依次完成: 欢迎 → 运行环境 ... → 数据源 (一个或多个网关) → ...
AC-3: 某步下载失败 → ... 显示错误详情 + "重试" / "跳过" 按钮; 跳过则该步骤标记为"待处理"
```

但 spec.md UI-FR-0460 (第 1098-1116 行) 已改为:
- 流程: "5.Tushare数据源 6.交易网关(可选项)" (不是 "数据源一个或多个网关")
- 失败恢复: 区分必选项 (只允许重试) vs 可选项 (可跳过)，不是统一 "重试/跳过"

**acceptance.md AC-2/AC-3 需完全重写以匹配 spec**。

---

## 第三部分: 新问题 (Sage 修改引入 + 仍未发现)

### N1: UI-FR-D202 状态为 "⚠️" 但未重写

[spec.md 第 451-453 行](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/spec.md) UI-FR-D202 元数据:
```
| ✅ | ✅ | ⚠️ |
```

Aaron 在前一轮明确表示:
> 这一部分需要重写。策略一旦转仿真、实盘，将会是一直在运行 -- 取决于 v0.2-001 中底层设计，但应该不是由外部驱动的。

但 spec.md UI-FR-D202 内容 (第 455-470 行) **未重写**，仍保留"今日计划运行 / 未来 N 天计划 / 数据同步任务"三段内容。**需 Aaron 决策后重写**。

### N2: UI-FR-A180 功能降级不完整

[spec.md 第 384-401 行](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/spec.md) UI-FR-A180:

**缺口 1**: B 类降级期间，**运行中的实盘策略**会怎样？
- 策略是否继续运行？
- 已发出订单的成交回执如何同步？
- 策略是否应自动进入 dry-run？还是继续运行但订单暂存？

> **Aaron:** 这不是 UI 的任务。是后台应该做好的异常处理。@Maestro 应该创建 issue,提醒这部分需要 code/spec review, 关联到 https://github.com/users/zillionare/projects/7

**缺口 2**: A 类降级解除后行为未定义
- 用户配置网关后，需要刷新页面才能解除降级？还是自动解除？
- 解除后原本 disable 的入口如何恢复？

**缺口 3**: A 类与 B 类转换条件未定义
- A 类 (永久) 配置网关后是否立即变正常？还是要测试通过？
- B 类 (临时) 多久未恢复才升级为 A 类？还是永不升级？

> **Aaron:** 没必要考虑此问题。即永不升级。

### N3: UI-FR-0340 修改网关不完整

[spec.md 第 1037-1045 行](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/spec.md) UI-FR-0340:

**缺口 1**: 仅说"修改"，未说能否**添加/删除**网关。但 story.md §6.2 说 "用户可以重新配置交易网关"，story §4.3.3 描述了"接入实盘账户"流程。**spec 与 story 不一致**。

> **Aaron:** 不能删除。重新配置 -- 因为只能有一个网关。所以，如果没有配置，自然就是增加。

**缺口 2**: 未说支持**多少个网关**。init-wizard 提到"交易网关(可选项)"——单数还是复数？

> **Aaron:** 当然只有一个

**缺口 3**: 未说"测试"按钮的具体行为
- 测试什么？连接？API Key？延迟？
- 测试通过/失败的判定标准？
- 测试期间是否阻塞 UI？

### N4: UI-US-0430 与 UI-FR-0411 内部矛盾

[spec.md 第 148-152 行](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/spec.md) UI-US-0430:
```
story: 作为用户，我想创建/删除仿真账户、接入/检测实盘账户、查看账户状态（在线/离线/故障）...
```

[acceptance.md 第 213 行](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/acceptance.md) UI-FR-0411 AC-7:
```
验证 UI 无 "创建账户"/"删除账户"/"重置账户" 入口 (Aaron 限制范围)
```

**矛盾**: US 说 "创建/删除仿真账户"，FR 说 "无创建/删除入口"。

> **Aaron:** 不矛盾。没有专门、单独的创建入口。通过给删除标记，把数据保留在数据库中，但用户不可见，是常见的删除方式。

按 story.md §4.3.2/§4.3.4 实际语义: 仿真/实盘虚拟账户在"转仿真/转实盘"操作时**系统自动创建**，用户**不能**手动创建/删除。US 应改写为:
```
作为用户，我想把策略投入仿真/实盘 (系统自动创建虚拟账户)、隐藏/恢复账户、查看账户状态...
```

### N5: 上游 FR 引用路径仍指向 spec.md 索引文件 ❌

spec.md 中所有 `001-FR-XXX` 引用都指向 `../v0.2-001-strategy-framework/spec.md`，但该文件是**索引文件**，FR 实际定义在:
- spec-trading.md (FR-210/220)
- spec-strategy.md (FR-020/230/240/250/340/350/360/440/450)
- spec-foundation.md (FR-310/320/330)

**示例**: spec.md 第 441 行:
```
> - 上游: [001-FR-220](../v0.2-001-strategy-framework/spec.md) 账户归属
```
点击此链接跳到 001 spec.md 顶部，而不会跳到 FR-220 定义处。

**修复**: 所有 `001-FR-XXX` 链接需改写为对应实际文件路径，例如:
```
[001-FR-220](../v0.2-001-strategy-framework/spec-strategy.md#fr-220)
```

**附带发现**: 001 spec.md 自身索引也不一致——第 85 行说 FR-220 在 spec-trading.md，第 131 行说在 spec-strategy.md。这是 001 的 bug，需要 001 修复（不在本 review 范围）。

### N6: UI-FR-0070 N 是否可配置未明确

[spec.md UI-FR-0070](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/spec.md) (第 805 行附近) "N 日窗口（默认 N=0，即当日收盘）":

- N 是否可由用户配置？
- 配置入口在哪里？
- 配置范围是多少 (0~30? 0~90?)？
- 配置后是全局生效还是单次查询生效？

spec 未明确。需 Aaron 决策。

### N7: UI-NFR-0040 视觉规范与 Aaron 红色决策冲突

详见第一部分 1.4 节。**需重写 UI-NFR-0040 按钮规范**。

### N8: UI-NFR-0040 按钮规范不完整

- 主操作"实心背景色"未明确颜色
- "危险操作红色描边或红色背景" 中 "或" 模糊，应明确选哪个
- 缺 Aaron 决定的"按钮强调时文字使用红色"

### N9: UI-FR-A170 toast "红色" 含义模糊

[spec.md 第 359 行](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/spec.md) error toast:
```
| error | 操作失败 | toast 红色 (顶部居中) | 不自动消失 | 必须手动关闭 |
```

"红色" 指背景、文字、还是边框？按 Aaron "红色不大面积使用" 决策，应该是**文字/边框/图标**红，而非背景红。**需明确**。

### N10: 上游 FR 引用缺锚点

联动总表 (spec.md §5) 仅写 "FR-220"、"FR-230/240/250" 等，未给文件链接。读者需自行在 001 三个 spec 文件中搜索。**建议补充链接**。

### N11: UI-FR-A160 "推送机制" Aaron 澄清但未沉淀为约束

[spec.md 第 344-345 行](file:///Users/aaronyang/workspace/millionaire/.louke/project/specs/v0.2-002-ui/spec.md):
```
> **Sage:** Q-A160 未读数刷新机制: 是定时轮询 ... 还是 SSE/WebSocket 推送? 移动端是否需要同步刷新?
>> **Aaron:** 推送机制,具体哪一种机制是个实施阶段的技术问题。没有移动端。
```

Aaron 澄清了"具体机制是实施阶段决定"，但 spec 未沉淀这条**约束**: "未读数刷新必须走推送 (非轮询), 具体协议 (SSE/WebSocket) 由实施阶段决定"。建议在 UI-FR-A160 加一行约束。

---

## 第四部分: 总结

### 4.1 修复进度

- 上一轮 22 个问题: **11 修复 / 5 未修复 / 6 已不适用或合并**
- 本轮新增: **11 个 (N1~N11)**
- 总计待处理: **16 个 (5 未修复 + 11 新)**

### 4.2 UI 设计标准评估结论

| 维度             | 评估                            |
| ---------------- | ------------------------------- |
| 字体大小         | ✅ 符合主流标准                  |
| 间距 (8pt grid)  | ✅ 完全符合                      |
| 圆角             | ✅ 符合主流                      |
| 语义色彩         | ✅ 符合通用设计                  |
| WCAG AA 对比度   | ✅ 符合可访问性                  |
| **红色使用边界** | ⚠️ **与 Aaron 决策冲突，需修正** |
| **主操作按钮色** | ⚠️ **未明确，缺失关键信息**      |

### 4.3 优先级建议

**P0 (阻塞实施)**:
- N7/N8/N9: UI-NFR-0040 按钮规范 + 红色使用边界 — 与 Aaron 决策直接冲突
- N4: UI-US-0430 与 UI-FR-0411 矛盾 — spec 内部不能自相矛盾
- N1: UI-FR-D202 "⚠️" 状态需 Aaron 决策后重写

**P1 (影响实施一致性)**:
- N2: UI-FR-A180 B 类降级期间实盘策略行为
- N3: UI-FR-0340 添加/删除网关流程
- N5: 上游 FR 引用路径修复
- M5/M6/M7/M8/M9: acceptance.md 与 spec.md 同步

**P2 (待 Aaron 决策)**:
- N6: UI-FR-0070 N 是否可配置
- N11: UI-FR-A160 推送机制约束沉淀

### 4.4 给 Aaron 的建议

1. **红色使用边界**需 Aaron 明确:
   - 主操作按钮背景用什么颜色？(建议: 深色中性 / 品牌蓝)
   - 危险操作按钮: 红色描边+红字 (无红底) — 是否同意？
   - 强调按钮文字用红色 — 是否仅限"提交订单"等关键操作？

2. **UI-FR-D202 计划任务**需 Aaron 重写或确认:
   - 策略转仿真/实盘后是否"一直在运行"(非外部驱动)？
   - 如果是，"计划任务"区块还有意义吗？是否仅显示数据同步任务？

3. **N 是否可配置**: UI-FR-0070 风控超额收益 N 日窗口。

---

## 附录: 文件改动追踪

- spec.md: Sage 修改后 1428 行 (上一轮 ~1340 行, 新增 ~88 行)
- acceptance.md: Sage 修改后 348 行 (上一轮 ~340 行, 微调)
- story.md: 296 行 (S1 已修复, S2 未修复)
- 本 review: review-2026-07-04-round2.md (新建)
