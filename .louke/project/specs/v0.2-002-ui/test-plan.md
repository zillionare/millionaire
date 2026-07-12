# Millionaire UI — Test Plan

- **Spec ID**: v0.2-002-ui
- **阶段**: M-TESTPLAN
- **范围**: `.louke/project/specs/v0.2-002-ui/spec.md` / `acceptance.md` / `story.md`
- **上游契约**: `v0.2-001-strategy-framework`
- **测试框架决策**: Python 3.13 + `pytest` / `pytest-asyncio` / `pytest-cov`; L3 使用 Playwright Python 驱动浏览器
- **覆盖目标**: 单元测试行覆盖率 ≥95%; 所有 45 个 FR/NFR 均需建立 AC → 测试层级追踪

> 注: `.louke/templates/test-plan.md` 在当前工作区未找到。本文件保留 Louke test-plan 必需结构: 测试策略、测试环境、测试数据、L1/L2/L3 层次、FR/NFR 覆盖矩阵、特殊场景、风险与执行顺序。

---

## 1. 测试目标与边界

### 1.1 目标

1. Shield 能据此准备 FastHTML UI 测试环境、fixture 数据和 L3 e2e 用户路径。
2. Devon 能据此为 UI 层纯逻辑、表单校验、路由守卫、降级状态、渲染数据适配编写 L1/L2 测试。
3. 每个 `acceptance.md` 中的 FR/NFR AC 至少被一个层级覆盖; 用户可见行为必须有 L3 路径或明确手工验收补充。
4. CI 使用 `lk agent archer ci-scan ...` 对 AC 标记与测试追踪执行闭环扫描。

### 1.2 不在本计划范围

- 不实现测试代码; Devon/Shield 后续实现。
- 不修改 `spec.md` / `acceptance.md` / `story.md`。
- 不新增 GitHub issue。
- 不进入 M-ARCH 的 architecture/interface 设计。

---

## 2. Overall Approach: 测试金字塔

### 2.1 L1 单元测试 — CI 必跑

- **框架**: `pytest >=9`, `pytest-asyncio`, `pytest-cov`, `freezegun`。
- **目标**: 覆盖纯逻辑、表单校验、状态转换、路由分流判断、可访问性属性生成、图表数据适配、toast/banner 规则。
- **Mock 边界**: mock FastHTML request/session、Tushare、qmt-gateway、时钟、任务调度器、文件系统中非 fixture 的路径。
- **覆盖率门槛**: 行覆盖率 ≥95%; 新增 UI 逻辑模块必须与源码同目录结构映射到 `tests/unit/.../test_*.py`。
- **运行预算**: PR/CI 必跑, 5 分钟内完成。

### 2.2 L2 集成测试 — CI nightly / 合并前可选

- **框架**: `pytest` + FastHTML/Starlette TestClient 或 ASGI client。
- **目标**: 启动真实 FastHTML app，使用测试数据库/临时目录，mock 外部 Tushare/qmt-gateway，验证页面渲染、表单提交、重定向、服务端返回码、HTMX/局部刷新片段。
- **外部依赖**: qmt-gateway 使用可脚本化 stub server; Tushare 使用固定 parquet/json fixture; 微信/IM/邮件只验证配置页与绑定状态，不发真实消息。
- **运行预算**: nightly 必跑; release 前必须通过。

### 2.3 L3 E2E — release 前手动触发

- **框架**: Playwright Python。
- **目标**: 启动真实 UI，浏览器执行完整用户路径: init-wizard → 登录 → dashboard → 策略/回测 → 账户 → 交易 → 系统管理 → 通知。
- **浏览器矩阵**: Chromium 必跑; FR-0411 账户隐藏额外覆盖 Firefox/WebKit; 响应式覆盖 desktop 1366x768 与 tablet 768x1024。
- **运行预算**: 手动触发或 release gate; 允许 >5 分钟。

---

## 3. 外部依赖 Mock / Stub 策略

| 依赖 | L1 策略 | L2 策略 | L3 策略 | 断言重点 |
| --- | --- | --- | --- | --- |
| FastHTML + MonsterUI | mock 组件输入/输出, 不启动服务 | 启动真实 FastHTML app, 验证 HTML/ARIA/表单 | Playwright 操作真实 DOM | 路由、布局、表单、toast/banner、可访问性 |
| Tushare | fake client 返回固定 DataFrame/Polars | fixture parquet/json, 禁止访问公网 | 使用预置数据源状态 | 数据任务、K 线、init-wizard 数据源失败/成功 |
| qmt-gateway | fake gateway adapter | stub server 支持 online/offline/fault/latency/order reject | stub gateway 随场景切换状态 | FR-0180 降级、FR-0340 网关、FR-0420 下单错误 |
| 时钟/调度 | `freezegun` 固定时间 | 测试 clock provider | 浏览器只断言相对文案/顺序 | 任务状态、告警排序、toast 自动消失 |
| 通知渠道 | fake sender | stub IM/mail/wechat binding | 不发外部消息 | 配置项、二维码 token、订阅状态 |

---

## 4. 测试数据与 Fixture

### 4.1 基础 fixture

- **用户账户**: initialized admin、uninitialized system、wrong password、changed password。
- **策略**: 内置 day/live/risk 策略、自定义策略、同名覆盖策略、被屏蔽策略、实盘运行中策略、仿真运行中策略。
- **回测**: 成功报告、运行中报告、失败报告、含 stdout/stderr 日志报告、可删除日志报告。
- **账户**: 实盘总账户、paper 虚拟账户、live 虚拟账户、风控账户、hidden 账户、offline/fault live 账户。
- **订单/成交**: 当日委托、已成交、可撤、撤单失败、超持仓卖出、gateway reject。
- **任务/数据**: 成功/失败/部分成功数据同步任务、完整性缺日/重复日/空值率超阈值、K 线小样本。
- **通知**: unread/read 告警、策略类/系统类告警、微信 token pending/bound、IM/mail disabled/enabled。

### 4.2 边界值

- 本金: `0`、负数、极大值、实盘总账户抽至负数。
- 订单: 卖出数量 > 可卖数量、数量非 100 股整数、价格为空/负数、风控账户作为手动交易目标。
- wizard: 必选步骤失败、可选步骤失败并跳过、下载子任务失败延后、重新配置禁止改密码/数据目录。
- 布局: 空列表、超过分页数、长策略名/长错误摘要、断推送后恢复。

---

## 5. 覆盖矩阵: FR/NFR → L1/L2/L3

> 记号: L1=单元; L2=FastHTML 集成; L3=Playwright e2e; `L2*` 表示存在外部交互/服务端渲染必须覆盖; `L3*` 表示用户可见必须覆盖。

| ID | AC 范围 | L1 覆盖 | L2 覆盖 | L3 覆盖 |
| --- | --- | --- | --- | --- |
| FR-0110 | AC-1~2 | 初始化状态路由选择 | `/` 与非 wizard URL 重定向 | 首次打开进入 wizard |
| FR-0120 | AC-1~2 | 密码校验/会话创建 | 登录表单成功/失败 | 登录进入主界面 |
| FR-0130 | AC-1~4 | 登出/改密校验 | 用户菜单与改密提交 | 改密后重新登录 |
| FR-0140 | AC-1~2 | deep link 保存 | 未登录保护路由 | 登录后返回原 URL |
| FR-0150 | AC-1~2 | nav/sidebar 状态 | layout HTML/localStorage hook | 折叠侧栏并刷新保持 |
| FR-0160 | AC-1~6 | 告警过滤/未读计数 | 告警列表/批量确认/详情跳转 | header alert → 列表处理 |
| FR-0170 | AC-1~5 | toast/banner 类型与时长 | 操作触发通知片段 | 成功/错误 toast 可见性 |
| FR-0180 | AC-1~23 | A/B 降级状态与禁用规则 | 503 路由、gateway offline banner | 无网关/断网关完整路径 |
| FR-0203 | AC-1~4 | 告警分组排序 | dashboard 顶部渲染/跳转过滤 | dashboard 告警分组点击 |
| FR-0201 | AC-1~2 | 账户排序/隐藏排除 | dashboard 账户区块 | 点击实盘进入 FR-0420 |
| FR-0202 | AC-1~5 | 任务排序/截断 | 任务区块/立即重试 | 查看全部跳 FR-0310 |
| FR-0010 | AC-1~4 | 策略排序/过滤/覆盖 | 策略选择器渲染 | 查找并选择策略 |
| FR-0011 | AC-1~3 | 扫描结果摘要 | 扫描按钮状态/toast | 点击扫描刷新列表 |
| FR-0012 | AC-1~3 | 屏蔽过滤规则 | 屏蔽/取消屏蔽表单 | 屏蔽后列表消失 |
| FR-0013 | AC-1~6 | 删除禁用/二次确认 | 删除自定义策略与报告 | 删除流程含运行中禁用 |
| FR-0020 | AC-1~4 | 运行时参数边界 | 表单校验/本地缓存 | 输入本金 0/负数错误 |
| FR-0040 | AC-1~7 | 启动/转入表单规则 | 回测/仿真/实盘提交 | 回测转仿真/实盘入口 |
| FR-0060 | AC-1~4 | dry-run 状态/徽章 | 切换请求与双线图数据 | 进入/退出 dry-run |
| FR-0070 | AC-1~6 | reason 分组/超额收益展示适配 | 风控事件列表/过滤 | 点击 reason 过滤列表 |
| FR-0080 | AC-1~11 | 进度状态映射 | 实时进度/失败日志片段 | 回测运行进度到完成 |
| FR-0091 | AC-1~5 | 报告排序/筛选 | 报告列表与导出链接 | 查看报告四页签 |
| FR-0092 | AC-1~3 | 删除单报告规则 | 删除确认/列表刷新 | 删除后报告消失 |
| FR-0093 | AC-1~3 | 批量删除/日志清理 | 批量操作结果 | 批量清理后空态 |
| FR-0260 | AC-1 | 聚合入口一致性 | 聚合页引用 FR-0010/0020/0040 | 策略操作主路径 |
| FR-0370 | AC-1~2 | 图表数据 schema | 图表容器/空态/tooltip 数据 | 图表可见与 hover |
| FR-0380 | AC-1 | 等价 FR-0080 映射 | 同 FR-0080 | 同 FR-0080 |
| FR-0390 | AC-1~5 | 按策略筛选/汇总 | 账户总览页渲染 | 筛选单策略账户 |
| FR-0410 | AC-1~3 | paper/live 指标适配 | 账户详情图表/热力图 | 打开账户详情 |
| FR-0411 | AC-1~8 | 隐藏前置条件/统计排除 | hide/show 请求与持久化 | 跨浏览器/设备隐藏恢复 |
| FR-0420 | AC-1~16 | 下单校验/可卖数量/离线规则 | 订单提交、撤单、gateway reject | 实盘下单 + 离线 toast |
| FR-0430 | AC-1~3 | 仿真交易规则 | 仿真交易页无辅助 | 仿真补单路径 |
| FR-0400 | AC-1~3 | 委托成交查询条件 | 三态记录列表 | 查询与筛选历史 |
| FR-0310 | AC-1~6 | 任务状态/cron 校验 | 启停/立即运行/历史 | 任务失败重试路径 |
| FR-0320 | AC-1 | 报告字段阈值标红 | 校验报告页 | 打开报告并看异常 |
| FR-0330 | AC-1~4 | 模糊查询/K 线数据 | 搜索 API + 图表片段 | 搜索股票并 hover K 线 |
| FR-0340 | AC-1~6 | 网关配置校验/状态映射 | stub gateway 检测/保存 | 修改网关后状态变化 |
| FR-0450 | AC-1~5 | 订阅配置/二维码 token | 通知配置与绑定状态 | 启用微信并切订阅 |
| FR-0460 | AC-1~7 | wizard 步骤/失败恢复 | 必选/可选步骤流转 | 首装 + 失败/跳过/补做 |
| NFR-0010 | AC-1~3 | 性能预算函数/分页规则 | 响应时间采样 | L3 记录关键页面耗时 |
| NFR-0020 | AC-1 | ARIA/role 属性生成 | axe/HTML 属性检查 | Playwright + axe spot check |
| NFR-0030 | AC-1~2 | 错误降级策略 | 部分数据失败不空白 | 断 gateway 页面仍可用 |
| NFR-0040 | AC-1~8 | 组件 token/颜色规则 | DOM class/style 检查 | 视觉 spot + screenshot |
| NFR-0050 | AC-1~4 | 局部刷新失败隔离 | 单区块失败不影响页面 | dashboard 局部失败路径 |
| NFR-0060 | AC-1~5 | 长任务状态机 | 回测/下载/扫描状态 | 长任务取消/失败/完成 |
| NFR-0070 | AC-1~5 | localStorage key 规则 | 状态读写/清除 | 刷新后侧栏/筛选保持 |

---

## 6. 跨 FR 用户路径

1. **启动与认证链路**: FR-0110 → FR-0460 → FR-0120 → FR-0150 → FR-0140。
2. **概览到交易链路**: FR-0201 账户总览 → FR-0420 实盘交易 → FR-0340 网关管理; 断开 gateway 时联动 FR-0180/FR-0170/FR-0160。
3. **策略研究链路**: FR-0010 → FR-0011 → FR-0020 → FR-0040 → FR-0080/FR-0380 → FR-0091 → FR-0370。
4. **回测转运行链路**: FR-0091 → FR-0040 转仿真/实盘 → FR-0390/FR-0410 → FR-0060 dry-run。
5. **账户隐藏链路**: FR-0411 hide/show → FR-0201/FR-0390 统计排除 → FR-0410 详情不可达/恢复。
6. **系统恢复链路**: FR-0180 A 类无网关 → FR-0340 配置网关 → FR-0180 解除 → FR-0420 下单恢复。
7. **通知链路**: FR-0450 配置订阅 → FR-0170 toast → FR-0160 告警中心 → FR-0203 dashboard 分类。

---

## 7. 特殊场景设计

### 7.1 FR-0180 功能降级

- **A 类**: L2/L3 启动时使用 fixture 标记无 gateway 配置; 断言交易/仿真入口 disabled、hover tooltip、直接 URL 返回 503、网关管理仍可用、回测仍可用。
- **B 类**: stub gateway 初始 online 后切 offline; 断言黄色 banner、告警中心链接、主内容区不空白、已加载数据保留。
- **转换**: 配置 gateway 后 A 类立即解除; gateway 检测失败只进入 B 类，不升级为 A 类。

### 7.2 FR-0411 账户隐藏

- L1 覆盖隐藏前置条件: 空闲、无未结算持仓、非风控限制、统计排除。
- L2 覆盖数据库 hidden 状态持久化与列表过滤。
- L3 在 Chromium/Firefox/WebKit 执行 hide → refresh → dashboard/account 列表排除 → show → 恢复; viewport 覆盖 desktop/tablet。

### 7.3 FR-0460 init-wizard

- 必选步骤失败: Tushare token 无效、数据目录不可写、首次下载子任务失败; 只能重试不能跳过。
- 可选步骤失败: qmt-gateway 不可达、通知渠道失败; 允许重试或跳过, 标记待处理。
- 重新进入: 从失败步骤继续; 已成功步骤不回退。
- 重新配置模式: 禁止修改管理员密码与数据目录; 完成后回主界面不重启进程。
- 顶部黄色待处理横幅: L3 可自动断言存在/关闭/重新显示; 颜色精确值作为视觉 spot 或手工验收补充。

### 7.4 FR-0420 下单与 gateway 离线

- L1 覆盖订单表单校验: 目标策略必选、风控策略不可选、卖出可卖数量、金额反算 100 股取整。
- L2 使用 gateway stub 返回 success/reject/offline; 离线时按钮置灰且点击提交显示 error toast: `网关离线, 请先恢复网关连接`。
- L3 断言离线订单不进入本地队列、不暂存、不自动发送, 当日委托列表不新增。

---

## 8. 风险评估与缓解

| 风险 | 涉及 FR/NFR | 困难原因 | 缓解 |
| --- | --- | --- | --- |
| UI 视觉颜色/布局精确断言脆弱 | FR-0150/0180/0170, NFR-0040 | CSS/MonsterUI class 可能变化 | 自动断言语义 DOM + screenshot spot; 精确视觉留手工 |
| gateway 状态切换时序 | FR-0180/0340/0420 | 真实 qmt-gateway 不稳定且不应依赖外部服务 | stub server 提供 deterministic online/offline/fault/latency |
| 推送机制未在 spec 固定为 SSE/WebSocket | FR-0160 | 技术方案留给实施阶段 | L2 只测“推送事件入口契约”; L3 测断线 UI，不绑定协议 |
| 长任务实时进度 | FR-0080/0380/0460, NFR-0060 | 时间相关、可能异步 | fake clock + 可控任务 stub; L3 只跑短链路 |
| 图表 hover 与 canvas/svg | FR-0370/0410/0330 | 图表库 DOM 结构不稳定 | L1 测数据 schema; L2 测容器和数据属性; L3 spot hover |
| 跨浏览器本地状态 | FR-0411, NFR-0070 | localStorage/session 差异 | Playwright browser matrix; 每例隔离 context |

### 8.1 自动测试难以完全覆盖的 AC

- “主界面顶部出现黄色横幅”的精确视觉效果: 自动可测 presence/role/text/link/close; 背景黄色、红色图标文字建议 screenshot + 手工验收。
- NFR-0040 中“禁止大面积红色背景”等视觉规范: 自动检查 CSS token 与 screenshot diff，最终 release 手工 spot。
- 图表美观、tooltip 细节: 自动测数据与 hover 可触达，视觉布局手工 spot。
- 微信扫码真实外部绑定: 自动测 token/状态机; 真实公众号链路需手工或独立外部环境验收。

---

## 9. 测试执行顺序与 CI 契约

1. **L1 单元测试 — PR/CI 必跑**
   - 命令建议: `pytest -q tests/unit --cov=quantide --cov-report=term-missing`
   - 预算: ≤5 分钟; 覆盖率 ≥95%。
2. **L2 集成测试 — nightly / 合并前可选**
   - 命令建议: `pytest -q tests/integration`
   - 启动真实 FastHTML app, Tushare/qmt-gateway 均为 stub/fixture。
3. **L3 e2e — release 前手动触发**
   - 命令建议: `pytest -q tests/e2e --browser chromium`
   - FR-0411/NFR-0070 增加 `--browser firefox --browser webkit`。
4. **AC 闭环扫描**
   - CI gate 使用: `lk agent archer ci-scan --spec v0.2-002-ui --tests tests`。

---

## 10. 阶段闭环检查

- [x] 45 个 FR/NFR 均在覆盖矩阵中出现。
- [x] 每个 FR/NFR 至少有 L1 覆盖策略。
- [x] 有外部交互或服务端渲染的 FR 均有 L2 覆盖策略。
- [x] 用户可见 FR/NFR 均有 L3 或明确手工补充。
- [x] FastHTML + MonsterUI / Tushare / qmt-gateway mock/stub 策略已定义。
- [x] FR-0180、FR-0411、FR-0460、FR-0420 特殊场景已单列。
- [x] Shield 可据此准备环境、fixture 和 e2e 脚本；Devon 可据此准备 L1/L2 测试。
