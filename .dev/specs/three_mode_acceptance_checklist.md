# 三模式验收清单

## 1. 文档定位

本文档用于发布前开发验收，不属于公开发布文档。

约束来源：

1. `.dev/specs/00-architecture.md`
2. `.dev/specs/05-release-readiness.md`

本清单只回答四个问题：

1. `backtest / paper / live` 三种模式在当前发布门槛下分别需要满足什么。
2. 当前代码已经有哪些自动化证据。
3. 还缺哪些关键证据，当前才不能被视为发布就绪。
4. 发布前必须补齐哪些 QA 级 E2E 才能放行。

## 2. 当前总体结论

截至当前工作区状态：

1. `backtest`：已有较强的策略级与 broker 级自动化证据，但还缺发布态要求的端到端回测验收证据。
2. `paper`：已有 runtime 装配、撮合规则和生命周期级自动化证据，但还缺基于本地独立 stub 的端到端验收，以及异常阻断语义的自动化证据。
3. `live`：已有 gateway client / broker adapter / port wrapper 级自动化证据，但还没有接近真实交易状态机的本地 stub 端到端验收。
4. 跨模式发布阻塞项仍然存在：
   - 当前 `tests/e2e/support/gateway_stub.py` 只有 `/ping`，不具备交易级 stub 能力。
   - 现有 E2E 主要集中在初始化向导和系统设置，不覆盖策略、回测、交易阻断与恢复链路。
   - 仓库内尚未形成独立的风险事件中心与阻断持久化的验收证据。

结论是：当前代码已经具备发布态架构的若干核心部件，但**尚未达到“可发布、可长期运行”的放行标准**。

## 3. 模式清单

### 3.1 backtest

#### 发布态验收目标

1. `RuntimeBootstrap` 不依赖实时行情与 gateway 也能进入回测路径。
2. 同一份策略代码不需要为回测模式做条件分支。
3. 固定输入数据下，回测结果完全可重复。
4. 回测默认使用动态前复权，并基于复权因子运行。
5. 撮合必须考虑手续费、涨跌停、停牌等市场约束；手续费由用户配置。
6. 回测订单、成交、资产变化能落到主体统一数据模型。
7. 回测失败时有显著提示，而不是静默退化。

#### 当前自动化证据

1. `tests/strategies/example/test_dual_ma.py`
   - 使用静态日线数据驱动 `BacktestRunner`
   - 验证同一策略代码产生买卖成交
   - 验证订单与成交写入 SQLite
2. `service/backtest_broker.py` 和相关测试已覆盖主体本地回测撮合主链路。

#### 当前缺口

1. 还没有一条面向发布态的 QA 级回测 E2E，证明“固定数据下结果完全可重复”。
2. 还没有把动态前复权、用户手续费配置、涨跌停和停牌规则放到同一条用户场景验收中。
3. 还没有把“回测失败显著提示”作为端到端放行项锁定。

#### 当前判定

1. `backtest` 在组件与策略级上较成熟。
2. 但在本轮发布门槛下，`backtest` 仍不能单凭现有测试被判定为“发布前验收完成”。

### 3.2 paper

#### 发布态验收目标

1. `RuntimeBootstrap(mode="paper")` 能装配实时行情适配器与主体本地仿真 broker。
2. `paper` 使用实时行情输入，但撮合和持仓变化在主体本地完成。
3. 策略代码不因 `paper` 模式而修改。
4. 自动交易异常必须触发受影响账户/策略级阻断。
5. 被阻断后，新的自动交易被禁止，但人工交易仍可进行，且持续显示风险告警。
6. 风险事件、阻断状态和恢复语义必须可持久化并在重启后正确恢复。
7. `paper` 的发布态 E2E 必须通过独立本地 stub 提供实时行情、断连与异常注入能力。

#### 当前自动化证据

1. `tests/core/test_runtime_modes.py`
   - 验证 `RuntimeBootstrap(mode="paper")`
   - 验证 gateway 市场数据适配器可被 mock 并注入仿真账户句柄
2. `tests/service/test_sim_broker_paper.py`
   - 覆盖买卖、撤单、金额/比例/目标仓位下单、涨跌停、无成交量、T+1、最小手续费等行为
3. `tests/service/test_sim_broker_paper_lifecycle.py`
   - 覆盖持久化恢复、并发账户共享行情、日终撤单、生命周期 metrics

#### 当前缺口

1. 还没有一条“策略经 `RuntimeBootstrap(mode=paper)` 运行并完成下单到成交”的 QA 级 E2E。
2. 还没有一条覆盖阻断、持续告警、关闭后二次确认、恢复自动运行的用户场景验收。
3. 当前 stub 只有 `/ping`，不能为 `paper` 提供真实的行情、断连和异常注入能力。
4. 仓库内还没有“风险事件中心”和“阻断状态持久化恢复”的现成证据。

#### 当前判定

1. `paper` 的 runtime 和仿真撮合主链路已有较强自动化基础。
2. 但它仍停留在组件级与生命周期级通过，尚未达到发布态放行标准。

### 3.3 live

#### 发布态验收目标

1. 主体不直连 `xtquant/QMT`。
2. `live` 模式通过 gateway 获取行情与交易能力。
3. 主体内部以 `qtoid` 作为唯一订单主键；外部订单号只做映射。
4. 本地独立 stub 能够提供接近真实交易的协议和状态机。
5. `live` 端到端验收必须覆盖资产/持仓/订单/成交查询、下单、撤单、行情推送、乱序回报和断连补推。
6. 交易异常必须触发账户/策略级自动阻断，并支持重启后阻断恢复。

#### 当前自动化证据

1. `tests/core/test_gateway_client.py`
   - 验证 gateway HTTP/HTTPS 到 WS/WSS URL 组装正确
2. `tests/core/test_gateway_broker_adapter.py`
   - 验证买卖、金额下单、目标仓位下单、查询资产、批量撤单等映射
3. `tests/core/test_port_broker.py`
   - 验证 gateway broker adapter 能接入正式 port 层
4. `tests/config/test_runtime.py`
   - 验证 runtime 配置优先从数据库装配，包括 gateway 配置和模式判定
5. 代码层面已经把 `qtoid` 贯穿到 SQLite 订单/成交主链路中。

#### 当前缺口

1. 还没有一条基于近真实本地 stub 的 `live` 端到端自动验收。
2. 当前 `tests/e2e/support/gateway_stub.py` 只支持 `/ping`，不能承载资产、持仓、订单、成交或 WebSocket 行情路径。
3. 还没有证明主体在 `live` 模式下：
   - 能发现远程账户
   - 能拉取远程资产、持仓、订单、成交
   - 能在 WS 行情与乱序回报下维持一致状态
   - 能在异常时触发阻断、重启后恢复阻断、关闭后二次确认并恢复运行

#### 当前判定

1. `live` 模式的架构方向与适配器边界是正确的。
2. 但当前仍只有组件级通过，距离发布态放行差距最大。

## 4. 发布前强制 E2E 清单

以下 8 条链路是本轮发布前必须由 QA 维护并自动通过的场景：

1. 初始化。
2. 数据下载与补齐。
3. 策略发现/加载。
4. 回测运行。
5. `paper` 下单到成交。
6. `live` 下单到成交。
7. 异常告警与阻断。
8. 任务恢复与重启恢复。

### 当前证据状态

1. 初始化：已有 HTTP 级 E2E，属于部分完成。
2. 数据下载与补齐：已有向导下载相关 HTTP 路径验证，但还不是完整发布态验收。
3. 策略发现/加载：暂无 QA 级 E2E。
4. 回测运行：暂无 QA 级 E2E。
5. `paper` 下单到成交：暂无 QA 级 E2E。
6. `live` 下单到成交：暂无 QA 级 E2E。
7. 异常告警与阻断：暂无 QA 级 E2E。
8. 任务恢复与重启恢复：暂无 QA 级 E2E。

## 5. 当前回归基线

当前仍可作为研发回归基线的命令集如下：

### backtest

`pytest tests/strategies/example/test_dual_ma.py`

### paper

`pytest tests/core/test_runtime_modes.py tests/service/test_sim_broker_paper.py tests/service/test_sim_broker_paper_lifecycle.py`

### live 组件级

`pytest tests/core/test_gateway_client.py tests/core/test_gateway_broker_adapter.py tests/core/test_port_broker.py tests/config/test_runtime.py`

### 现有 E2E

1. `tests/e2e/web/test_init_wizard_flow.py`
2. `tests/e2e/web/test_system_settings_flow.py`

这些命令仍然有价值，但它们只能证明“部分基础链路有效”，不能单独证明发布前验收完成。

## 6. 发布前判定建议

基于当前工作区状态，应作如下判定：

1. `backtest`：组件级通过，待补 QA 级发布态 E2E。
2. `paper`：组件级通过，待补本地 stub 驱动的端到端与阻断恢复验收。
3. `live`：组件级通过，待补近真实本地 stub 驱动的完整端到端验收。
4. 整体版本：**当前不可宣称达到发布前验收完成状态**。

当前最主要的阻塞项不是单个 bug，而是以下三类发布缺口：

1. 交易级本地独立 stub 尚未实现。
2. 风险事件中心与阻断持久化/恢复语义尚未形成验收闭环。
3. QA 级 E2E 套件还没有覆盖规定的 8 条发布前主链路。
