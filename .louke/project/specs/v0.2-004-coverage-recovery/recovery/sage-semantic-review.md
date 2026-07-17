# 基于源码的恢复合约的 Sage 语义审查

- 生产索引 SHA-256：`8410d32fb4b64c0d38ef21f947c45be7164185dcaa09f36a7061bc99b9c8bfbe`
- 生产分片清单 SHA-256：`4ec8dbdbf8eaabfe1d8a355df778ae438e03b6dc3b18b0038955ba91472cac39`
- 测试索引 SHA-256：`3d7ebc07cc8d014aab8981c025a142f1112c7d7cfb05390254de02c19da38fd0`
- 测试分片清单 SHA-256：`f48b15e808737352ad6a5c4d8da2b2a5f9b97fa3fb56a4ca2881463ec2380352`
- Devon 工作注册表 SHA-256：`bac42a69bcd6359afe16fbcdc8ae710314ad00ced431dff9c1625186cb2bd088`
- 生产闭包：13 个分片，169 个唯一的磁盘精确路径，169 个基于源码的合约，0 个伪导入 API，0 个损坏签名，0 个缺失锚点。
- 测试闭包：240 个模块，1651 个函数，1455 个对齐，196 个更新，0 个需要 Sage 合约；196 个更新函数一对一绑定到 196 个开放的 `RW-*` 项。

## 优先级与处置规则

每个候选均按以下锁定顺序审查：v0.2-001/002/003 规范+验收，然后是接口，然后是故事，然后是实际公共消费者/当前实现。较高级别的来源将相反的代码转化为实现缺陷；这不是 Aaron 的产品问题。仅在所有较高级别来源均无规定时，才使用较低级别来源。修正后的分片行仍然是规范路径合约；本审查记录每个候选为何需要或不需要 Aaron，并非通用合约覆盖层。

## 额外 55 候选解析表

| 候选 | 路径 | 解析依据 | 规范解析 |
|---|---|---|---|
| SAGE-PROD-15036E03E523 | `quantide/core/init_wizard_steps.py` | 规范 | v0.2-002 FR-0460 十步 `wizard_steps_v2` 是权威的；所消费的六步模式仅用于兼容性，不得驱动产品流程。 |
| SAGE-PROD-01435F6276F5 | `quantide/core/runtime/gateway_broker.py` | 规范 | v0.2-001 FR-050/060/070 修复了纸盘/实盘竞价和下一笔开盘语义；不可用的实时开盘数据是实现缺陷，而非将历史拍卖式定价特征化的许可。 |
| SAGE-PROD-027974B1CCDE | `quantide/data/fetchers/__init__.py` | 当前兼容性 | 显式的通配符包导入是源码定义的 Tushare 辅助函数的当前兼容性外观；导入的依赖项/私有名称被排除，不推断任何更广泛的 API。 |
| SAGE-PROD-89E180C24ABE | `quantide/notify/dingtalk.py` | 规范 | v0.2-001 FR-481 将 `ding` 消息限制为文本和 markdown `{title,text}`；不支持的格式必须被确定性拒绝，偶然的 `KeyError`/未绑定局部变量失败是缺陷。 |
| SAGE-PROD-BACFFEB485FE | `quantide/notify/mail.py` | 当前兼容性 | 现有实现和兼容性测试确立了基于发件人的 SMTP 认证；未使用的 `username` 回退不是第二种产品行为，实现/签名不匹配是修复工作。 |
| SAGE-PROD-CF608C440483 | `quantide/service/datafeed.py` | 规范 | v0.2-001 AC-010/115 要求在所有模式下使用 `1d`，在纸盘/实盘模式下使用 `30m`，并明确拒绝回测；静默地提供非 DAY 的 DAY 数据是实现缺陷。 |
| SAGE-PROD-A436A1459981 | `quantide/service/discovery.py` | 规范 | v0.2-001 FR-020 枚举元数据、诊断、非递归扫描和用户优先于内置的优先级是规范的；`StrategyLoader` 在使用处保持为兼容性/内部。 |
| SAGE-PROD-5B3A3D325D59 | `quantide/service/grid_search.py` | 当前兼容性 | 公共结果为每个成功组合一行，包含指标和参数；不存在排序保证。已废弃的小写 `sharpe` 分支不是规范的，不得与发出的 `Sharpe Ratio` DTO 相矛盾。 |
| SAGE-PROD-2272E540793C | `quantide/service/livequote.py` | 当前兼容性 | 源码负载语义将 1d 成交量/金额标识为累积快照，因此缓存更新替换这些字段；增量累加是实现缺陷。 |
| SAGE-PROD-17252C8BA6C1 | `quantide/service/metrics.py` | 当前兼容性 | 现有消费者和实现对历史不足的情况使用 `None`；保留该兼容性边界，同时非空输出仍然是指标 DataFrame 合约。 |
| SAGE-PROD-28D4861467F3 | `quantide/service/registry.py` | 接口 | v0.2-001 接口将 `portfolio_id` 定义为 UUID，因此冒号在有效标识符域之外；注册表键无需支持带冒号的任意 ID。 |
| SAGE-PROD-F85C02B60215 | `quantide/service/runner.py` | 规范 | 锁定的生命周期/资源合约要求 `on_stop` 仅调用一次，且失败后运行清理可观察；在失败后未完成经纪人/投资组合的终结处理是实现缺陷。 |
| SAGE-PROD-E6909E7D5207 | `quantide/service/sim_broker.py` | 规范 | v0.2-001 `trade_target_pct(0)` 表示在正常卖出规则下平仓目标持仓；错误的位置转发是实现缺陷。 |
| SAGE-PROD-4EBC3E5E77A8 | `quantide/service/strategy_runtime.py` | 规范 | 持久化运行时恢复必须保留安全块并暴露失败；损坏状态不得通过丢弃块而静默地安全失效。 |
| SAGE-PROD-D341CA7496AE | `quantide/service/trade_lightning.py` | 规范 | v0.2-002 FR-0420 修复了参考价格选择；v0.2-003 AC-FR0404 拒绝非法的 `price_ref`。未知值不得作为零价格回退而持久化。 |
| SAGE-PROD-DD9DA7FDD598 | `quantide/service/triple_barrier.py` | 规范 | v0.2-001 FR-013/360 锁定了公式，v0.2-003 FR-0404 使该服务保持在范围内；运行时接线是实现工作，而非产品处置或死代码决策。 |
| SAGE-PROD-2547002D3646 | `quantide/web/apis/analysis/kline.py` | 接口 | v0.2-002 接口使 `/system/stocks/{symbol}/kline` 成为规范；遗留的 `/api/v1/kline/*` 仅可作为经过测试的兼容性重定向/适配器，而非竞争 API。 |
| SAGE-PROD-6887921CC187 | `quantide/web/apis/broker.py` | 消费者 | 注册了具有真实主页/E2E 消费者的路由仍然是兼容性 API，但必须满足 v0.2-003 FR-0504 输入/状态/模式/ErrorEnvelope 规则；不完整的处理程序是缺陷。 |
| SAGE-PROD-9F9D0F1081ED | `quantide/web/auth/routes.py` | 接口 | 规范行为是 POST `/login`、POST `/logout`、安全的 `next` 和 303 目标；`/auth/*` 仅可进行兼容性适配。GET 注销和未经验证的重定向目标是缺陷。 |
| SAGE-PROD-82C6D31D5D38 | `quantide/web/components/analysis/kline_chart.py` | 规范 | v0.2-003 FR-0501 修复了构造函数输入 `chart_id/data/width/height` 和稳定的空渲染；使用其他签名的源码/测试必须更新。 |
| SAGE-PROD-C864FFF98FDA | `quantide/web/events.py` | 接口 | v0.2-002 修复了 GET `/events/stream` 和重放/快照 SSE 语义；仅 DTO 的源码意味着端点的实现缺失，而非可选发布范围。 |
| SAGE-PROD-75E42FE985B3 | `quantide/web/middleware_feature.py` | 规范 | v0.2-002 FR-0180 规定了规范的纸盘/实盘降级路由；仅匹配遗留的 `/trade/simulation` 是实现缺陷。 |
| SAGE-PROD-9821DD3FC75B | `quantide/web/middleware_init.py` | 接口 | 未初始化的请求使用 303 `/wizard`；`/init-wizard` 仅用于兼容性。当前的 302/路径行为必须收敛。 |
| SAGE-PROD-7AD9A9E9B8DB | `quantide/web/middleware.py` | 规范 | v0.2-003 FR-0504 要求 ErrorEnvelope 输出不包含敏感细节；原始回溯/异常文本绝不是生产 HTTP 行为。 |
| SAGE-PROD-8F002113F409 | `quantide/web/pages/accounts.py` | 接口 | 规范路由和确认合约为 `/accounts*`；`/system/accounts*` 仅可作为兼容性适配器，且破坏性操作必须服务器端验证确认。 |
| SAGE-PROD-C75ACF006267 | `quantide/web/pages/data_market.py` | 规范 | v0.2-003 FR-0503 将市场数据验证/更新/进度保持在范围内，要求确定性服务固件和任务隔离；存根验证/全局进度是实现缺陷。 |
| SAGE-PROD-302FAB608470 | `quantide/web/pages/history_trades.py` | 接口 | v0.2-002 FR-0400 和 `/trade/trades?from&to` 要求完整的时间范围；忽略 `end_date` 是实现缺陷。 |
| SAGE-PROD-967460246B4C | `quantide/web/pages/init_wizard.py` | 接口 | `/wizard*` 和方法表是规范的；改变状态的操作（step/download/complete/reset）不得通过 GET/HEAD 暴露。 |
| SAGE-PROD-0748D3304030 | `quantide/web/pages/live.py` | 规范 | v0.2-002 排除了本地实盘账户创建；创建墓碑不是受支持的成功端点，仅可提供非修改性兼容性/退役行为。 |
| SAGE-PROD-AB0406173054 | `quantide/web/pages/paper.py` | 接口 | 纸盘组件必须面向纸盘路由；重用提交/刷新 `/trade/live/*` 的实现是实现缺陷。 |
| SAGE-PROD-2D3B6262FDAA | `quantide/web/pages/strategy.py` | 接口 | v0.2-002 `/strategy*` 方法/DTO 是规范的，v0.2-003 使服务策略成为业务层；重叠的遗留行为必须适配而非竞争。 |
| SAGE-PROD-1390E20AAD1D | `quantide/web/pages/system/datasource.py` | 规范 | 变更同步是一种改变状态的操作，受 v0.2-003 HTTP/中间件安全规则约束；GET/HEAD 修改是实现缺陷。 |
| SAGE-PROD-23700ED1EB6D | `quantide/web/pages/system/gateway.py` | 规范 | v0.2-002 FR-0340 明确要求保存前自动测试且仅在成功后保存；直接未经测试的持久化是实现缺陷。 |
| SAGE-PROD-518824298F03 | `quantide/web/pages/system/jobs.py` | 接口 | 在规范任务合约下，任务变更使用 POST；GET/HEAD 切换/运行行为是无效的兼容性行为。 |
| SAGE-PROD-29C34A02177C | `quantide/web/pages/system/runtime_monitor.py` | 规范 | v0.2-003 要求通过状态/行/风险事件或 ErrorEnvelope 提供运行时失败原因；将异常吞入成功形式的内容是实现缺陷。 |
| SAGE-PROD-2FA210E1DBF4 | `quantide/web/pages/trade_main.py` | 接口 | v0.2-002 OrderRequest/Response 和 `/trade/order` 验证是规范的；未知 side/mode 不得进入回退分支。 |
| SAGE-PROD-AEFE0EF82EDC | `quantide/web/services/account_overview.py` | 规范 | v0.2-002 账户概览要求 `strategy_type` 过滤；该 v0.2 服务是必需的业务合约层，忽略过滤/未集成是实现缺陷。 |
| SAGE-PROD-B54910B60313 | `quantide/web/services/accounts.py` | 规范 | v0.2-002 FR-0411 修复了账户隐藏资格，包括风控限制；已声明但忽略的字段和缺失集成是缺陷。 |
| SAGE-PROD-95733CA1182E | `quantide/web/services/auth_session.py` | 规范 | v0.2-003 将 `web/services` DTO/纯策略合约保持在范围内；已发布的认证必须适配锁定的登录/会话行为，而非将其视为可选产品范围。 |
| SAGE-PROD-988B50E845F3 | `quantide/web/services/backtest_progress.py` | 规范 | v0.2-002 FR-0080/NFR-0060 要求有界进度和禁止重入；未消费的服务和超过 100 的值是实现缺陷。 |
| SAGE-PROD-76E0F28664F6 | `quantide/web/services/backtest_reports.py` | 规范 | v0.2-002 报告排序/删除/确认行为已锁定；该服务必须集成，且自身无需执行持久化删除。 |
| SAGE-PROD-B04F16F9FE6B | `quantide/web/services/dashboard.py` | 规范 | v0.2-002 FR-0201~0203 修复了仪表盘 ViewModel 行为；独立的根渲染必须消费/适配它。 |
| SAGE-PROD-798CA7E2A24E | `quantide/web/services/gateway.py` | 规范 | v0.2-002 FR-0340 使该验证器/保存前测试策略成为规范；已发布的页面绕过是实现缺陷。 |
| SAGE-PROD-D848F8E3739F | `quantide/web/services/integrity.py` | 规范 | v0.2-003 FR-0503 明确包含完整性服务/页面输出；缺少生产者/展示集成是实现工作。 |
| SAGE-PROD-A1B065322010 | `quantide/web/services/layout.py` | 规范 | v0.2-002 个人资料/密码/侧边栏持久化合约占主导地位；仅验证和缺失 localStorage/密码集成是缺陷。 |
| SAGE-PROD-29D92499D4A1 | `quantide/web/services/notifications.py` | 规范 | v0.2-002 FR-0450 要求订阅绑定/持久化行为；仅验证的实现是不完整的。 |
| SAGE-PROD-856151242B3E | `quantide/web/services/risk_events.py` | 规范 | v0.2-002 风险事件过滤和 v0.2-001 超额收益窗口占主导地位；运行时/页面 DTO 不匹配是实现缺陷。 |
| SAGE-PROD-5A3EA0494ADF | `quantide/web/services/routing.py` | 接口 | v0.2-002 路由表修复了 `/wizard`、`/login`、`/dashboard` 和安全 next 行为；策略字面量和应用路由必须收敛到该路由表。 |
| SAGE-PROD-2D8079C7B50C | `quantide/web/services/runtime_control.py` | 规范 | v0.2-002 运行时/回测/升级规则是规范的；通过一个未消费的调度模型进行集成是实现工作。 |
| SAGE-PROD-8A5063510667 | `quantide/web/services/scheduling.py` | 规范 | v0.2-002 策略调度/列表/过滤合约要求该 ViewModel 行为；缺少生产导入器是实现缺口，而非删除授权。 |
| SAGE-PROD-0BCC092FC87F | `quantide/web/services/stock_query.py` | 接口 | `/system/stocks` 搜索和 K 线路由是规范的；该 DTO/谓词模块必须支持或适配这些路由，而非独立的产品 API。 |
| SAGE-PROD-D105BD52BCFB | `quantide/web/services/strategy_management.py` | 规范 | v0.2-002 FR-0010~0013 和 v0.2-003 FR-0504 使该策略成为规范；已发布的 `/strategy` 分歧是实现工作。 |
| SAGE-PROD-FF6EA2D19774 | `quantide/web/services/tasks.py` | 规范 | v0.2-002 任务管理和 v0.2-003 系统页面合约占主导地位；`/system/jobs` 必须适配而非使该服务仅为测试所用。 |
| SAGE-PROD-60A64D86FC7A | `quantide/web/services/trade_history.py` | 接口 | v0.2-002 `/trade/orders` 和 `/trade/trades` 过滤器（包括 `from/to`）是规范的；页面必须消费/适配该过滤器合约。 |
| SAGE-PROD-DDE49EED52E7 | `quantide/web/services/trade.py` | 接口 | v0.2-002 OrderRequest 整手/策略验证是规范的；已发布的绕过它的订单处理程序是实现缺陷。 |

## 解析计数

- 由锁定规范/验收解析：**33**
- 由接口解析：**16**
- 由故事解析：**0**
- 由实际公共消费者解析：**1**
- 由当前兼容性行为解析：**5**
- 升级为新的 Aaron 决策：**0**
- 总共额外候选：**55**

## 最终 Aaron 决策集

在优先级审查后，没有额外候选需要用户可观察的产品选择。Aaron 于 2026-07-13 将确切最终集——`AD-01` 至 `AD-06`——解析为**保留**。该解析不批准删除、豁免、隔离、重定向或发明替换行为。

## 规范测试追踪与 M-DEV 绑定

修正后的测试索引/分片已物化所有函数处置；无需外部通用覆盖层。1651 个函数中的每一个都至少有一个符合规范的 AC 引用。最终分布为 1455 个对齐和 196 个更新，质量发现为 87 个不完整、61 个自证、41 个仅导入、3 个伪造、2 个冲突和 2 个规范缺口。

`recovery/devon-work-items.json` 是规范的 M-DEV 输入。其 196 个唯一的开放 `RW-*` 记录一对一的绑定到 196 个更新函数 ID。一个工作项仅在以下情况下才算完成：具有来自同一可追溯修订版的 AC 派生的 Red、Green 和完整隔离套件/每文件门控证据，或被双向链接的替换项所取代（该替换项携带相同的函数 ID、AC 引用和证据义务）。GitHub 问题/列表完成本身不等于完成定义，且没有更新绑定授权删除。

## Aaron 保留决议 — 2026-07-13

Aaron 将最终六个决策候选解析为**保留**。修正后的分片行仍然是管辖当前实现的合约。必须为当前实现合约添加测试，而非发明行为。每一行需要：引用该当前行为的失败 Red 测试；在隔离/确定性下断言相同行为的 Green 测试；通过 `--timeout` 的绿色相同修订版完整套件运行；`percent_covered >=80.0`；无覆盖技巧或广泛排除。未批准任何豁免。

| ID | 状态 | 决策 | 批准人 | 批准时间 | 修正分片证据 | 当前实现合约含义 | 所需证据 |
|---|---|---|---|---|---|---|---|
| AD-01 | 已解决 | 保留 | Aaron | 2026-07-13 | `prod-f4c5b6766c15`；`admin_routes.py:14-294,779-783` | 默认应用使管理路由保持未注册状态；显式 `include_admin=True` 保留编码的 GET/POST 注册器、当前角色守卫不对称、HTML/303 回退以及无事务清理。 | 针对该启用/禁用行为的 Red；相同行为的隔离确定性 Green；带 `--timeout` 的绿色完整套件；文件 `>=80.0%`。 |
| AD-02 | 已解决 | 保留 | Aaron | 2026-07-13 | `prod-2222692b50e2`；`forms.py:51-727` | 登录/资料和受门控的遗留渲染器保留其编码的 FastHTML 字段/操作/错误；该模块不注册路由，不执行任何认证决策/持久化。 | 针对当前渲染输出的 Red；相同输出的隔离确定性 Green；带 `--timeout` 的绿色完整套件；文件 `>=80.0%`。 |
| AD-03 | 已解决 | 保留 | Aaron | 2026-07-13 | `prod-5793dc5849e8`；`repository.py:5-209` | 当前查找/哈希/认证/CRUD/搜索/列表/计数、`last_login` 更新、最后一个管理员拒绝和编码的异常回退保持不变。 | 针对当前仓库结果的 Red；相同结果的隔离确定性存储 Green；带 `--timeout` 的绿色完整套件；文件 `>=80.0%`。 |
| AD-04 | 已解决 | 保留 | Aaron | 2026-07-13 | `prod-478f19f91ad5`；`auth/utils.py:8-48` | 当前令牌长度/随机字母表、源邮箱正则、密码结果/消息、用户名清理、负长度空令牌和传播类型/正则错误保持不变。 | 针对这些当前值/错误的 Red；相同行为的确定性随机性 Green；带 `--timeout` 的绿色完整套件；文件 `>=80.0%`。 |
| AD-05 | 已解决 | 保留 | Aaron | 2026-07-13 | `prod-5c4b6a15a6b7`；`core/utils.py:7-40` | 五个纯辅助函数保持严格的 8/14 字符解析、零填充格式化、分钟秒 `00` 和当前的 `ValueError`/`AttributeError` 边界。 | 针对这些转换/错误的 Red；相同行为的隔离确定性 Green；带 `--timeout` 的绿色完整套件；文件存在于清单中且 `>=80.0%`。 |
| AD-06 | 已解决 | 保留 | Aaron | 2026-07-13 | `prod-da64e6c5652e`；`analysis.py:15-74`；`app_factory.py:409` | 认证后的 `GET /analysis` 保持当前 HTTP 200 HTML 退役通知，带可选的会话头状态，无分析数据 I/O。 | 针对该当前响应的 Red；相同响应的隔离确定性品牌/会话 Green；带 `--timeout` 的绿色完整套件；文件 `>=80.0%`。 |

最终 Aaron 决策集现在为六个已解决的保留决策和零个未解决决策。`coverage-waivers.json` 保持为空注册表。