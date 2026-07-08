评审人: Codex
评审日期: 2026-07-08
范围: spec.md (1860 行) + acceptance.md (441 行) + story.md (296 行)
方法: 独立通读 3 份核心文档；抽样 UI-FR-A180 / 0080 / 0411 / 0420 / 0460 / 0340；核对 001 上游 spec、GitHub issues #167/#156/#155/#159/#141/#132 与现有 quantide/web/pages/... 实现意图；最后才阅读前三轮 review 去重。

总体评价
当前文档的章节覆盖和 FR 列表已经比较完整，页面构图也显著多于前三轮版本；但仍有几处会直接影响 Devon 实施方向和 Shield 验收口径。最大风险不是 "spec 太长"，而是关键 FR 的跟踪链路里出现了局部反向语义：尤其是无网关降级、账户隐藏、回测报告页签、离线订单暂存。

严重问题 (P1, 阻塞实施)
UI-FR-A180 无网关降级把能力开关写反，且 issue/AC 都无法兜底。

位置: story.md:L282-L284 明确说未配置交易网关时 "仿真和实盘功能都不可用"、用户只能回测研究；spec.md:L503-L505 又说禁用实盘/仿真和 "策略转仿真、回测按钮"；spec.md:L523 反过来说 "启动回测" disabled、"启动仿真"仍可用；acceptance.md:L437-L441 没有独立 A180 AC；GitHub #167 正文写 "验收标准: 无"。
上游证据: v0.2-001/spec-trading.md:L155-L161 说 qmt-gateway 仅 live/paper 使用；v0.2-001/spec-strategy.md:L436-L442 说回测走历史日线 parquet。因此正确方向应是: 回测可用；paper/live 和转仿真/转实盘不可用。
修复建议: 重写 A 类降级为 "仅禁用仿真/实盘相关入口和路由；保留回测入口"；为 UI-FR-A180 增加专属 AC；同步更新 #167。
UI-FR-0411 把账户隐藏状态从数据库语义降级成 localStorage/UI 标记，破坏 story 的账户生命周期约束。

位置: story.md:L137-L141 / story.md:L155-L159 要求隐藏账户前账户空闲且无未结算持仓，隐藏状态需要记录且不参与合计；spec.md:L1141-L1146 写 "数据库状态不变"、只通过 localStorage 记住 "是否显示隐藏账户"；acceptance.md:L241-L245 同样没有空闲/未结算持仓断言。
风险: 如果只做浏览器本地标记，换浏览器或清 localStorage 后隐藏账户会重新参与概览/账户总览，和 "不参与各类合计统计" 冲突。
修复建议: 区分两类状态: account.hidden 服务端/数据库字段，以及 "显示已隐藏账户" 的 localStorage UI 偏好；补 AC: 非空闲或有未结算持仓时隐藏失败、隐藏后不参与 D201/0390 合计、换浏览器仍保持隐藏。
回测报告的 "每日持仓" 已在 story/spec 中定义，但 acceptance 没有任何可验收断言。

位置: story.md:L69-L73 定义回测报告包含 "概览 / 每日成交 / 每日持仓 / 日志"；spec.md:L963-L967 再次定义 "每日持仓: 回测区间内每日的持仓快照, 可按日期跳转"；acceptance.md:L172-L178 只覆盖进度、概览、每日成交、日志，遗漏每日持仓。
代码旁证: quantide/web/pages/strategy.py:L2779-L2880 已有 positions_panel / positions_body。
修复建议: 在 UI-FR-0080 AC 中补一条 "每日持仓" 页签验收: 日期分组、字段、按日期跳转/过滤、空持仓占位。
UI-FR-0420 的 "网关离线订单暂存并自动发送" 是交易安全行为，但 001 没有订单队列契约，且 #132 明确还在等后台 review。

位置: story.md:L190-L194 与 spec.md:L1223-L1226 写网关离线时订单进入本地队列并恢复后自动发送；acceptance.md:L261-L263 直接要求断开 qmt-gateway 后下单进入本地队列。
上游证据: 001 只定义手工交易归属 (spec-trading.md:L103-L110) 和网关断开通知事件 (spec-trading.md:L377-L394)，没有 pending order 队列、过期、撤销、重放、幂等、风控再校验等规则。GitHub #132 也把 B 类降级期间实盘策略/订单行为列为 P1 后台待 review。
修复建议: 在后台契约确定前，不应让 UI AC 要求自动暂存并发送实盘订单。可临时改为 "阻止提交 + error toast + 保持表单"，或把队列行为降级为 pending/open issue，不进入 v0.2-002-ui 验收。
中等问题 (P2, 一致性/完整性)
B 类网关断开横幅颜色与交互冲突。

位置: UI-FR-A180 B 类降级用黄色 warning banner (spec.md:L531-L540)；UI-NFR-0030 要实盘策略详情页顶部出现红色横幅 (spec.md:L1575-L1576, acceptance.md:L393-L394)；UI-NFR-0040 又禁止大面积红色背景 (spec.md:L1602-L1605)。
修复建议: 统一为黄色 warning banner + 红色文字/图标或明确哪些场景用 error 样式；同步 NFR-0030 AC。
UI-FR-0460 "无 mockup，以代码为准" 会和 10 步验收流程冲突。

位置: spec.md:L1507-L1518 / acceptance.md:L351-L363 是 10 步流程；spec.md:L1534-L1538 又要求下游直接读 init_wizard.py。当前代码 quantide/web/pages/init_wizard.py:L393-L421 是 6 步元数据，把 gateway 与数据下载分组方式也不同。
修复建议: 把这段改成 "代码仅作为视觉/组件风格参考，步骤与字段以 spec/acceptance 为准"，或补一个轻量 ASCII/表格构图避免实施者按旧代码步骤实现。
运行时实例的暂停/终止/重启没有完整落到 FR/AC。

位置: story.md:L79-L87 和 spec.md:L127 提到暂停、终止、重启；spec.md:L863-L865 / acceptance.md:L147-L150 只覆盖停止；UI-FR-0060 只覆盖实盘 dry-run 进入/退出。
修复建议: 明确 "停止=终止且不可重启"、"dry-run=暂停实盘且可恢复"、paper 是否有暂停/恢复入口；补对应 AC 或回写 story 删除未实现语义。
账户总览 UI-FR-0390 的表格对象表述不一致。

位置: spec.md:L1097-L1099 说默认展示实盘总账户 + 全部虚拟账户，但同一句又说 "每个运行中策略一行"；acceptance.md:L226-L228 只断言所有运行中策略一行，没有实盘总账户行。
修复建议: 明确 /accounts 是否包含实盘总账户行；如果包含，应定义其点击行为和筛选行为；如果不包含，删除 spec 中 "实盘总账户"。
编号与 AC 引用规则仍未完全可机器跟踪。

位置: acceptance.md:L10-L14 说完整 AC 引用为 AC-FRXXXX-YY，但正文全是每节内 AC-1；FR 编号同时存在 0010、A110、D203。GitHub issue 标题使用 [FR-A180]，不是 UI-FR-A180 或 AC-FRA180-01。
修复建议: 明确定义 ID grammar: 允许 [0-9]{4} 与 [A-Z][0-9]{3}；每条 AC 增加稳定锚点或显式完整 ID，例如 AC-FR-A180-01 / AC-NFR-0070-03。
UI-FR-0340 / UI-FR-0070 元数据状态与正文 resolved 状态不一致。

位置: spec.md:L1356-L1360 UI-FR-0340 "是否已决定" 仍是 ⚠️，但 spec.md:L1405-L1416 已写 Aaron Round 5 Q1=A 且 resolved；spec.md:L898-L903 UI-FR-0070 也仍是 ⚠️，但 spec.md:L926-L932 已 resolved。
修复建议: 元数据表改为 ✅，否则 issue/project 看板会误以为仍待决策。
轻微问题 (P3, 建议改进)
spec.md:L70-L72 UI-US-A130 仍写 "改昵称/密码"，但 FR/AC 已明确不支持改昵称 (spec.md:L337-L340, acceptance.md:L35-L38)。建议回写 US 文案为 "修改密码"。
acceptance.md:L23 对未初始化访问 /dashboard 写 "403 或重定向到 wizard"，这是两个不同用户体验。建议选一个主路径，另一个作为兼容实现而非 AC。
spec.md:L481-L484 写通知服务输出被告警中心聚合，容易把 toast 服务和告警事件源混为一谈。建议改成 "同一业务事件可同时触发 toast 与告警中心记录"。
acceptance.md:L411-L414 / L419-L423 的 NFR AC 跨多个页面，适合作为 test-plan 场景，但每个 FR 的局部失败/长任务恢复还需要最小本地 AC，否则实施阶段容易只做一个样例页面。
story.md:L131-L134 标题写 "四种账户"，正文却说 "系统区分三种账户" 后列出四类账户。建议改成 "四种账户"，避免后续账户模型引用时产生歧义。
与前 3 轮 review 的对比
重叠问题:
UI-FR-A180 不完整在 round-2 已被关注过；本次新增判断是: 当前文本不仅缺 AC，还把 "回测可用、仿真/实盘不可用" 写反。
账户管理/隐藏语义与 story 冲突在第一轮和第二轮出现过；本次新增判断是: 当前文档修成了 "可隐藏"，但把真正隐藏状态错误地落到 localStorage/UI 标记。
运行时暂停/重启入口在第一轮 L5 提过；当前版本仍未完全解决。
FR 编号/聚合 FR 是前三轮反复提到的问题；我认为保留聚合 FR 可接受，但 AC/issue 的完整 ID 仍需统一。
新发现:
UI-FR-0080 "每日持仓" 缺 AC。
UI-FR-0420 离线订单暂存/自动发送缺 001 后台契约，且与 #132 的待 review 状态冲突。
UI-NFR-0030 与 UI-FR-A180 对网关断开 banner 的颜色/严重级别冲突。
UI-FR-0460 "以代码为准" 与当前代码 6 步、spec/AC 10 步之间存在实施歧义。
Aaron 已决策但有疑虑的:
acceptance.md:L441 说 UI-FR-A180 无专属 AC "Round 9 未补专属 AC, 接受现状"。我不建议接受：A180 已有独立 issue #167，且承担路由拦截/入口禁用/降级解除关键行为，间接 AC 覆盖不到。
既有 review-round-4.md 倾向 "仿真不依赖网关"。我认为需要重新核对，因为 story §8.4 和 001 FR-300 都指向 paper/live 依赖 gateway，至少 v0.2-002-ui 不能同时保留两个方向。
给 Aaron 的建议
先让 Sage 修 UI-FR-A180: 明确无网关时能力矩阵，并补专属 AC + 更新 #167。
账户隐藏要拆成服务端隐藏状态与浏览器显示偏好两层，补隐藏前置条件 AC。
在 UI-FR-0080 补 "每日持仓" 验收；这是 story/spec 都已承诺的报告页签。
在 #132 后台结论出来前，不要把实盘离线订单暂存列为 UI-FR-0420 必验收 AC。
对 init-wizard 说明加一句 "代码只作视觉模板，步骤/字段以 spec 和 acceptance 为准"，避免 Devon 按旧 6 步代码实现。
