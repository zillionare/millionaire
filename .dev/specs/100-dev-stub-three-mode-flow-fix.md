# 100 Dev Stub 三模式流程修复计划

## 1. 目标

本计划修复 `QUANTIDE_ENABLE_DEV_STUBS=1` 开发态下的三模式流程缺口，使本地 Tushare stub 与 gateway stub 不只服务自动化测试，也能支撑一次真实 UI 路径的模拟上线验证。

完成后，应能在不接入真实 qmt-gateway 的情况下，通过本地 stub 跑通：

1. 数据侧：初始化、股票列表、历史行情、回测输入。
2. 回测侧：生成可转入仿真/实盘的回测报告。
3. 仿真侧：从回测报告转入本地 `PaperBroker`，进入 `/trade/simulation` 查看账户与运行状态。
4. 实盘侧：从回测报告转入 gateway broker，进入 `/trade/live` 查看 stub gateway 暴露的账户、资产、持仓与订单状态。

本文是 `.dev/specs/01-e2e-accuracy-contract.md` 的 bug 修复补充，不替代 01。01 继续定义发布态准确性、固定数据、baseline 和 release gate；本文补齐 01 未覆盖的开发态 UI 手工闭环和三模式一致性落地要求。

## 2. 当前状态

### 2.1 已经具备

1. `tests/e2e/support/tushare_stub.py` 可以用 fixture-backed fetcher 替代真实 Tushare。
2. `tests/e2e/support/gateway_stub.py` 可以启动本地 HTTP/WebSocket gateway stub，提供 `/ping`、鉴权、资产、持仓、订单、成交、下单、撤单和 `/ws/quotes`。
3. `QUANTIDE_ENABLE_DEV_STUBS=1` 可以在进程内启动 Tushare stub 与 gateway stub，并通过 effective settings 覆盖运行时 gateway 配置。
4. 现有 release gate 已覆盖部分 backtest、paper、live 准确性链路。

### 2.2 暴露的问题

1. 回测报告中的“转仿真”“转实盘”按钮仍可能 disabled。
2. 点击部分“实盘运行 / 仿真 / 实盘”导航时可能进入不存在的路由，例如 `/strategy/live`。
3. 系统维护页测试本地 stub 地址通过，不代表当前运行时已经使用该地址。
4. 现有 `test_dev_stub_mode` 只证明 stub 能启动和查询，不证明真实 UI 流程可走通。
5. 之前“测试通过”的结论如果被解释为“功能齐全”，属于过度外推；正确结论应是“已纳入 release gate 的准确性用例在其范围内通过”。

## 3. 对 01-e2e 的修订、更正、补充

### 3.1 修订

01 中的 gateway stub 不应被理解为“只能在测试函数中直接调用的假对象”。只要它满足 gateway 协议，应用层在配置后就不应区分它是真实 gateway 还是 stub gateway。

gateway stub 的限制应定义在数据和脚本层：

1. 它使用固定 fixture/scenario，而不连接真实 QMT。
2. 它只能重放或脚本化有限行情、订单回报和资产状态。
3. 它的撮合、成交、拒单、撤单、断连和补推由 scenario 控制。
4. 它不证明真实 gateway 已兼容全部生产场景。

### 3.2 更正

01 的准确性测试不能替代开发态 UI 验收。后续汇报应区分：

1. `release_gate accuracy passing`：固定数据、固定策略、固定 gateway 脚本下的交易与指标正确。
2. `dev-stub manual flow passing`：开启 stub 后，真实 Web UI 能从策略、回测、转仿真、转实盘一路走到交易页面。

### 3.3 补充

01 应补充三模式一致性落地口径：

1. 同一固定场景下，backtest、paper、live 必须复用同一策略代码、同一标的、同一策略参数、同一触发时间和同一可见行情窗口。
2. 在 stub 控制的发布态场景中，三模式的策略输入和策略决策必须可比对。
3. 三模式最终成交结果可以按各自 baseline 校验；live 若故意覆盖部分成交、拒单或撤单差异，必须在 scenario/baseline 中显式声明。
4. 真实生产 live 不要求与 backtest/paper 成交结果完全一致，但要求策略 API 和订单跟踪语义一致。

## 4. 关键技术决策

### D100-01 Gateway Stub 协议同构

当 gateway stub 被配置为 gateway 时，应用不应通过业务逻辑区分“真 gateway”和“stub gateway”。差异只存在于数据来源、scenario 能力和开发态提示。

实现含义：

1. `GatewayClient`、`GatewayBrokerAdapter`、`GatewayMarketDataAdapter` 应只依赖协议，不依赖 stub 标记。
2. UI gating 不能因为 endpoint 是 stub 而降级或禁用。
3. dev-stub 模式可以显示“当前为 stub 数据”，但不能改变交易链路的判断语义。

### D100-02 Tushare Stub 与 Gateway Stub 职责分离

Tushare stub 负责数据输入，gateway stub 负责实时行情与交易协议。

实现含义：

1. 回测和数据下载依赖 Tushare stub。
2. 转实盘依赖 gateway stub。
3. 转仿真不应强依赖 gateway broker；它需要 runtime、market data 和本地 `PaperBroker`。
4. 开发态组合开关可以同时启动两者，但测试和 UI 文案必须说明各自职责。

### D100-03 Effective Settings 优先

运行时、按钮 gating 和交易页面应以 `get_settings()` 的 effective settings 为准。系统维护页的持久化配置是下一次普通运行的配置，不一定等同于当前 dev-stub 进程的有效配置。

实现含义：

1. dev-stub 模式下必须显示 effective gateway URL。
2. 手工测试表单地址通过时，只能说明该表单地址可连通。
3. 若要让新持久化配置驱动 runtime，需要重启或显式 rebootstrap；本计划不要求实现在线 rebootstrap。

### D100-04 三模式一致性是策略输入与决策一致，不是生产成交一致

三模式一致性应校验策略层输入、时间边界、参数和决策。成交层在 controlled stub 场景中按 baseline 比对，在真实 live 中允许由真实交易回报产生差异。

## 5. Bug / 功能点清单

| 编号    | 类型         | 当前表现                                          | 修改意见                                                                                     |
| ------- | ------------ | ------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| B100-01 | Bug          | “转仿真”按钮被 gateway 可用性阻塞                 | 将 paper 可用性从 gateway broker 中解耦，改为 runtime + market data + backtest run 可用      |
| B100-02 | Bug          | “转实盘”按钮在 stub gateway 可用时仍可能 disabled | 以 effective runtime 中的 gateway broker/live account 判断 live 可用性，并给出明确不可用原因 |
| B100-03 | Bug          | `/strategy/live` 导航 404                         | 改为 `/trade/live`，并保留 `/strategy/live -> /trade/live` 重定向                            |
| B100-04 | Bug          | 系统维护连接测试通过但运行时未使用该地址          | 在 dev-stub 模式显示 effective gateway URL，并区分表单测试地址与当前运行地址                 |
| B100-05 | Coverage Gap | `test_dev_stub_mode` 未覆盖真实 UI 转换流程       | 增加 dev-stub UI E2E，覆盖策略页按钮、modal、转仿真、转实盘和交易页访问                      |
| B100-06 | Coverage Gap | release gate 结果被误读为功能齐全                 | 在验收文档和测试命名中区分 accuracy gate 与 manual flow gate                                 |
| B100-07 | Contract Gap | 三模式一致性没有独立测试矩阵                      | 增加 parity 测试，比较三模式策略输入、时间边界、交易意图和 baseline 结果                     |

## 6. 实施任务分解

### T100-01 修复导航入口

修改点：

1. 将策略菜单中的“实盘运行”从 `/strategy/live` 改为 `/trade/live`。
2. 增加 `/strategy/live` 的 303 重定向，避免旧链接继续 404。
3. 检查 header 与 sidebar 中所有交易入口，确保指向已挂载路由。

测试：

1. 增加布局/导航测试，断言 `/trade/live`、`/trade/simulation` 返回非 404。
2. 增加 `/strategy/live` 重定向测试。

### T100-02 拆分转仿真与转实盘 gating

修改点：

1. 将策略页 action cell 的单一 `gateway_available` 拆成 `paper_available` 与 `live_available`。
2. `paper_available` 只依赖 runtime、market data 和可用 backtest run。
3. `live_available` 依赖 gateway broker/live account。
4. 修改不可用提示文案，让用户能区分“仿真 runtime 不可用”和“实盘 gateway 不可用”。

测试：

1. paper 可用、live 不可用时，“转仿真”可点击，“转实盘” disabled。
2. paper 不可用、live 可用时，“转实盘”可点击，“转仿真” disabled。
3. 二者都可用时两个按钮均可点击。
4. 二者都不可用时分别显示正确原因。

### T100-03 明确 dev-stub effective runtime

修改点：

1. 系统维护 gateway 页面增加 dev-stub 提示区。
2. 显示当前进程 effective gateway URL、是否 fixture-backed、是否覆盖持久化配置。
3. 保持保存配置行为不变，不在本任务中实现在线 runtime rebootstrap。

测试：

1. dev-stub 开启时页面显示 effective gateway URL。
2. dev-stub 关闭时页面不显示 stub 覆盖提示。
3. 保存持久化 gateway 配置后，提示仍能说明当前进程有效配置来源。

### T100-04 补强 dev-stub UI E2E

修改点：

1. 扩展 `tests/e2e/web/test_dev_stub_mode.py`。
2. 从真实 HTTP 页面路径验证策略页、转仿真、转实盘、交易页入口。
3. 不只断言 status code，还要断言按钮、modal、账户/资产区块和关键提示。

测试路径：

1. `GET /strategy/`。
2. 回测报告 action cell 中“转仿真”存在且可点击。
3. `GET /strategy/backtest/{portfolio_id}/deploy/paper/modal` 返回确认 modal。
4. `POST /strategy/backtest/{portfolio_id}/deploy/paper` 成功生成 paper runtime 或明确返回可验证结果。
5. `GET /trade/simulation` 非 404/403。
6. gateway broker 可用时，live modal 可打开。
7. `GET /trade/live` 非 404/403。

### T100-05 增加三模式 parity 测试

修改点：

1. 新增 `tests/e2e/three_mode/test_dual_ma_parity.py` 或等价测试入口。
2. 使用 01 中 `dual_ma_2024` 场景。
3. 比较三模式策略输入、时间边界、可见历史窗口和首个交易意图。
4. 对成交、资产、指标使用各自 baseline 校验。

测试：

1. backtest/paper/live 均使用 `DualMAStrategy`。
2. 标的均为 `000001.SZ`。
3. 触发时间均为 `09:30`。
4. 策略只能看到上一交易日及以前完整日线。
5. 三模式在相同市场事实下生成一致交易意图。

### T100-06 更新验收文档表述

修改点：

1. 在 `three_mode_acceptance_checklist.md` 中新增 dev-stub manual flow 证据状态。
2. 将“release gate 通过”表述限定在 accuracy gate 范围。
3. 明确缺口不能被 status code、页面文字或单个 stub 查询替代。

测试：

1. 文档检查无需运行代码测试。
2. 相关自动化测试名称和文档状态保持一致。

## 7. No-do

本计划不做以下事情：

1. 不连接真实 Tushare。
2. 不连接真实 qmt-gateway/QMT。
3. 不要求真实生产 live 与 backtest/paper 成交结果完全一致。
4. 不实现在线 runtime rebootstrap；修改 gateway 持久化配置后仍可要求重启生效。
5. 不把 dev-stub 模式变成生产功能。
6. 不用页面 `200`、包含文字、资产大于 0 等低质量断言替代交易级校验。
7. 不扩大本轮到风险事件中心、阻断持久化和任务恢复；这些仍由 release readiness 后续计划处理。

## 8. 关键校验数据

### 8.1 配置数据

1. 环境变量：`QUANTIDE_ENABLE_DEV_STUBS=1`。
2. effective gateway URL：当前进程自动启动的 `http://127.0.0.1:<port>/qmt`。
3. persisted gateway URL：`AppState.gateway_*` 中保存的配置，可与 effective URL 不同。
4. feature status：`backtest=true`、`simulation=true`、`live_trading=true`。

### 8.2 Tushare Stub 数据

1. 股票列表包含 `000001.SZ`。
2. 股票列表数量与 fixture 一致，当前约 5433。
3. 日线切片覆盖 `2024-01-02` 到 `2024-05-31`。
4. `adjust=116.713`、`is_st=false`、`up_limit/down_limit` 存在。

### 8.3 Gateway Stub 数据

1. `/qmt/ping` 返回 200。
2. 初始资产符合 scenario，默认可用 `total=100000.0`、`cash=100000.0`。
3. `/qmt/ws/quotes` 保持连接并支持 ping/pong。
4. 订单以 `qtoid` 闭合生命周期。
5. 成交后现金、持仓、冻结资金、总资产与 scenario/baseline 一致。

### 8.4 三模式 Parity 数据

1. 策略：`DualMAStrategy`。
2. 标的：`000001.SZ`。
3. 起始日期：`2024-01-02`。
4. 截止日期：`2024-05-31`。
5. 触发时间：`09:30`。
6. 参数：`fast=5`、`slow=10`、`invest=100000`、`initial_cash=200000`、`commission=0.0005`。
7. 可见历史窗口：上一交易日及以前完整日线。
8. baseline：订单、成交、现金、持仓、市值、总资产、收益、年化收益、最大回撤、Sharpe ratio。

## 9. 验收标准

本计划完成后，必须满足：

1. `QUANTIDE_ENABLE_DEV_STUBS=1 uvicorn quantide.app:app --reload` 启动后，开发态页面能明确显示 effective gateway stub 状态。
2. 回测报告中“转仿真”不再被 gateway broker 缺失错误阻塞。
3. gateway broker 可用时，“转实盘”可打开确认 modal 并提交。
4. `/trade/simulation`、`/trade/live`、`/strategy/live` 均不再出现 404；其中 `/strategy/live` 应重定向到真实交易入口。
5. dev-stub E2E 覆盖至少一条从回测报告转仿真的 UI 路径。
6. live stub E2E 覆盖至少一条从 gateway stub 查询资产/持仓/订单或提交订单的 UI/API 路径。
7. 三模式 parity 测试能证明同一固定场景下策略输入和策略决策一致。
8. 文档和测试报告不再把 accuracy gate passing 描述为“功能齐全”。

## 10. 建议执行顺序

1. 修复导航 404。
2. 拆分转仿真/转实盘按钮 gating。
3. 增加 dev-stub effective gateway 页面提示。
4. 扩展 `test_dev_stub_mode` 为 UI 流程级 E2E。
5. 增加三模式 parity 测试。
6. 更新验收清单中的证据状态。
