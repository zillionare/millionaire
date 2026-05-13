# 发布态收口执行计划

## 1. 计划定位

本文把 `.dev/specs/06-release-readiness.md` 与
`.dev/specs/three_mode_acceptance_checklist.md` 拆解为可执行阶段。

本计划不改变发布门槛：

1. `.dev/specs/00-architecture.md` 仍是最高优先级架构约束。
2. `.dev/specs/01-e2e-accuracy-contract.md` 定义 E2E 数据、stub、指标和准确性验收要求。
3. `.dev/specs/06-release-readiness.md` 定义不可降级的发布态要求。
4. `.dev/specs/three_mode_acceptance_checklist.md` 记录当前证据、缺口与放行判定。
5. 本文只负责执行排序、仓库切片、验收条件与验证命令。

当前总判定保持不变：在交易级本地 stub、风险事件中心/阻断恢复闭环、QA 级 8 条 E2E 证据补齐前，当前版本不可宣称发布就绪。

## 1.1 当前进展快照

截至 `2026-05-13` 当前工作区状态：

1. P0 已建立 `e2e + release_gate` 证据基线，`conda run -n quantide poetry run pytest -m "e2e and release_gate" tests/e2e -q` 当前结果为 `11 passed, 13 deselected`。
2. P2 的本地 gateway stub 已具备场景脚本、资产/持仓回写、qtoid/external-order-id 映射和 replay/reconnect 基础能力。
3. P3/P4/P5 的准确性主链路已落地到 `tests/e2e/backtest/test_dual_ma_accuracy.py`、`tests/e2e/paper/test_dual_ma_accuracy.py`、`tests/e2e/live/test_gateway_accuracy.py`。
4. 当前剩余发布阻塞主要集中在 P6 风险事件中心、阻断持久化/恢复，以及 P7 中仍缺失的策略发现/加载与任务恢复 QA 证据。

## 2. 依赖总览

```text
P0 证据基线与测试分层
  ↓
P1 qtoid 与交易状态一致性护栏
  ↓
P2 交易级本地 gateway stub
  ├─→ P3 backtest 发布态 E2E
  ├─→ P4 paper stub 驱动 E2E
  └─→ P5 live stub 驱动 E2E
          ↓
P6 风险事件中心、阻断、告警、恢复
          ↓
P7 QA 放行矩阵与发布 gate
```

强依赖说明：

- P1 必须早于 P4/P5/P6：所有订单、成交、告警、恢复、UI 跳转都必须回落到 `qtoid`。
- P2 必须早于 paper/live QA E2E：当前 `tests/e2e/support/gateway_stub.py` 已有基础交易和行情能力，但还缺发布态场景文件、真实样本数据绑定、乱序/断连脚本和指标 baseline。
- P6 必须在 P7 前完成：异常阻断、持续告警、二次确认、重启恢复是发布阻塞项。
- P7 只能汇总自动化证据，不能用人工确认替代缺失链路。

## 3. P0：证据基线与测试分层

### 目标

建立“现有研发回归”和“发布态 QA gate”的边界，避免用组件测试替代发布放行。

### 仓库切片

- `.dev/specs/01-e2e-accuracy-contract.md`
- `.dev/specs/three_mode_acceptance_checklist.md`
- `tests/e2e/`
- `tests/strategies/example/test_dual_ma.py`
- `tests/core/test_runtime_modes.py`
- `tests/service/test_sim_broker_paper.py`
- `tests/service/test_sim_broker_paper_lifecycle.py`
- `tests/core/test_gateway_client.py`
- `tests/core/test_gateway_broker_adapter.py`
- `tests/core/test_port_broker.py`
- `tests/config/test_runtime.py`

### 执行项

1. 为发布态 QA 新增统一标记或目录约定，例如 `pytest.mark.e2e` 下细分 `release_gate`。
2. 把 8 条强制 E2E 映射为测试用例名、负责人和证据状态。
3. 保留当前组件级回归命令，但在文档和 CI gate 中标注“不可单独放行”。

### 验收条件

- 8 条主链路均有明确测试入口：初始化、数据下载与补齐、策略发现/加载、回测运行、paper 下单到成交、live 下单到成交、异常告警与阻断、任务恢复与重启恢复。
- 每条链路都标明当前状态：`missing / partial / passing`。
- CI 或本地命令能单独运行发布态 gate，而不混淆普通单元测试。

### 验证命令

```bash
poetry run pytest --collect-only tests/e2e
poetry run pytest tests/e2e/web/test_init_wizard_flow.py tests/e2e/web/test_system_settings_flow.py
poetry run pytest tests/strategies/example/test_dual_ma.py \
  tests/core/test_runtime_modes.py \
  tests/service/test_sim_broker_paper.py \
  tests/service/test_sim_broker_paper_lifecycle.py \
  tests/core/test_gateway_client.py \
  tests/core/test_gateway_broker_adapter.py \
  tests/core/test_port_broker.py \
  tests/config/test_runtime.py
```

## 4. P1：`qtoid` 与交易状态一致性护栏

### 目标

锁定 `qtoid` 作为主体系统唯一订单主键，避免 gateway 外部订单号形成事实双主键。

### 仓库切片

- `quantide/data/sqlite.py`
- `quantide/core/runtime/gateway_broker.py`
- `quantide/core/runtime/broker_bridge.py`
- `quantide/core/runtime/port_broker.py`
- `quantide/service/sim_broker.py`
- `quantide/service/backtest_broker.py`
- `quantide/web/pages/trade_main.py`
- `tests/data/test_sqlite.py`
- `tests/core/test_gateway_broker_adapter.py`
- `tests/core/test_port_broker.py`
- `tests/service/test_sim_broker_paper.py`
- `tests/service/test_backtest_broker.py`

### 执行项

1. 审计订单、成交、撤单、查询、日志、告警上下文，确认内部 API 返回和 UI 路由均以 `qtoid` 为主。
2. 外部订单号仅保存在映射/诊断字段，例如 `foid/cid/external_order_id`。
3. 增加契约测试：gateway 返回不同外部订单号时，主体订单生命周期仍以原始 `qtoid` 闭合。
4. 增加失败测试：`qtoid` 与外部订单号映射断裂时，必须产生阻断候选事件，而不是静默重试。

### 验收条件

- 订单、成交、撤单、历史查询和 UI 操作均可用 `qtoid` 追踪。
- 外部订单号缺失或变化不会替代 `qtoid`。
- 映射断裂被上抛到风险/阻断层。
- backtest、paper、live 适配层共享同一主键语义。

### 验证命令

```bash
poetry run pytest tests/data/test_sqlite.py \
  tests/core/test_gateway_broker_adapter.py \
  tests/core/test_port_broker.py \
  tests/service/test_sim_broker_paper.py \
  tests/service/test_backtest_broker.py
poetry run ruff check quantide/data/sqlite.py quantide/core/runtime quantide/service tests/data tests/core tests/service
poetry run mypy quantide tests
```

## 5. P2：交易级本地 gateway stub

### 目标

把 `tests/e2e/support/gateway_stub.py` 扩展为由 `tests/assets/` 场景文件驱动的近真实交易环境，为 paper/live 发布态 E2E 提供共同基础。

### 仓库切片

- `tests/e2e/support/gateway_stub.py`
- `tests/e2e/support/*_session.py`
- `tests/e2e/web/`
- `quantide/core/runtime/gateway_client.py`
- `quantide/core/runtime/gateway_market.py`
- `quantide/core/runtime/gateway_broker.py`
- `quantide/core/runtime/modes.py`

### 执行项

1. 保留当前系统设置和初始化向导使用的 `/ping` 兼容路径，并补齐发布态场景装载能力。
2. 增加账户、资产、持仓、订单、成交查询接口。
3. 增加买入、卖出、撤单接口，响应必须包含主体传入的 `qtoid` 与外部映射字段。
4. 增加行情 WebSocket 或可被现有 gateway market adapter 消费的等价推送能力。
5. 增加脚本化场景装载：部分成交、撤单、废单、拒单、乱序/延迟成交回报、断连重连后的状态补推。
6. 提供测试夹具，使每条 E2E 都能声明固定剧本并复现相同状态序列。

### 验收条件

- 当前 `/ping` 相关 E2E 不回归。
- stub 能独立运行，不依赖真实 QMT/xtquant。
- stub 状态机覆盖委托进入队列、部分成交、撤单、废单、拒单、乱序/延迟回报、断连补推。
- paper 可使用 stub 提供行情、断连和异常注入；live 可使用 stub 提供交易与行情完整链路。

### 验证命令

```bash
poetry run pytest tests/e2e/web/test_init_wizard_flow.py tests/e2e/web/test_system_settings_flow.py
poetry run pytest tests/core/test_gateway_client.py tests/core/test_gateway_market.py tests/core/test_gateway_broker_adapter.py
poetry run pytest tests/e2e -k gateway
poetry run ruff check tests/e2e/support quantide/core/runtime/gateway_client.py quantide/core/runtime/gateway_market.py quantide/core/runtime/gateway_broker.py
```

## 6. P3：backtest 发布态 E2E

### 目标

证明固定输入数据下同一策略代码可以在 backtest 模式零修改运行，且结果可重复、市场约束生效、失败显著提示。

### 仓库切片

- `quantide/service/backtest_broker.py`
- `quantide/service/runner.py`
- `quantide/service/strategy_runtime.py`
- `quantide/strategies/example/dual_ma.py`
- `quantide/web/pages/strategy.py`
- `tests/assets/*.parquet`
- `tests/strategies/example/test_dual_ma.py`
- `tests/e2e/web/`

### 执行项

1. 新增发布态 backtest E2E：初始化固定数据、加载同一策略、运行回测、断言订单/成交/资产变化。
2. 将动态前复权、用户手续费配置、涨跌停、停牌规则放入同一用户场景。
3. 增加重复运行断言：相同输入生成相同结果摘要。
4. 增加数据异常/运行失败路径，断言 UI 或 API 返回显著错误提示而不是空结果。

### 验收条件

- 同一份策略代码无需 backtest 专用分支。
- 固定数据与配置下结果完全可重复。
- 手续费、涨跌停、停牌、动态前复权均被 E2E 断言覆盖。
- 失败路径可见、可诊断。

### 验证命令

```bash
poetry run pytest tests/strategies/example/test_dual_ma.py tests/service/test_backtest_broker.py
poetry run pytest tests/e2e -k "backtest or strategy"
poetry run ruff check quantide/service/backtest_broker.py quantide/service/runner.py quantide/service/strategy_runtime.py tests/e2e tests/strategies
```

## 7. P4：paper stub 驱动 E2E

### 目标

证明 `RuntimeBootstrap(mode="paper")` 能通过 stub 行情、主体本地仿真 broker 和同一策略代码完成下单到成交，并覆盖异常阻断入口。

### 仓库切片

- `quantide/core/runtime/modes.py`
- `quantide/core/runtime/gateway_market.py`
- `quantide/service/sim_broker.py`
- `quantide/service/strategy_runtime.py`
- `quantide/web/pages/trade.py`
- `quantide/web/pages/trade_main.py`
- `tests/core/test_runtime_modes.py`
- `tests/service/test_sim_broker_paper.py`
- `tests/service/test_sim_broker_paper_lifecycle.py`
- `tests/e2e/support/gateway_stub.py`
- `tests/e2e/web/`

### 执行项

1. 新增 paper E2E：装配 RuntimeBootstrap、加载策略、接收 stub 行情、主体本地撮合、写入订单/成交。
2. 增加断连、行情缺失或异常注入剧本，断言进入账户/策略级阻断候选。
3. 覆盖被阻断后新自动交易被禁止，但人工交易入口仍可见且带持续告警。
4. 覆盖阻断状态写入持久化层，为 P6 恢复测试复用。

### 验收条件

- paper 下单到成交有 QA 级 E2E 证据。
- paper 的行情、断连和异常注入来自独立 stub。
- 自动交易异常不会静默重试后继续运行。
- 阻断粒度为受影响账户/策略，不是全局停机。

### 验证命令

```bash
poetry run pytest tests/core/test_runtime_modes.py \
  tests/service/test_sim_broker_paper.py \
  tests/service/test_sim_broker_paper_lifecycle.py
poetry run pytest tests/e2e -k "paper or block or risk"
poetry run ruff check quantide/core/runtime/modes.py quantide/core/runtime/gateway_market.py quantide/service/sim_broker.py quantide/service/strategy_runtime.py quantide/web/pages/trade.py quantide/web/pages/trade_main.py tests/e2e
```

## 8. P5：live stub 驱动 E2E

### 目标

证明 live 模式不直连 `xtquant/QMT`，通过本地独立 stub 完成交易与行情完整链路，并在乱序、重连和状态不一致时进入阻断候选。

### 仓库切片

- `quantide/core/runtime/gateway_client.py`
- `quantide/core/runtime/gateway_broker.py`
- `quantide/core/runtime/gateway_market.py`
- `quantide/core/runtime/port_broker.py`
- `quantide/core/runtime/modes.py`
- `quantide/web/pages/live.py`
- `quantide/web/pages/trade_main.py`
- `tests/core/test_gateway_client.py`
- `tests/core/test_gateway_broker_adapter.py`
- `tests/core/test_port_broker.py`
- `tests/config/test_runtime.py`
- `tests/e2e/support/gateway_stub.py`
- `tests/e2e/web/`

### 执行项

1. 新增 live E2E：发现远程账户、拉取资产/持仓/订单/成交、订阅行情、买入/卖出、撤单。
2. 使用 stub 场景覆盖部分成交、拒单、废单、乱序成交回报、断连恢复补推。
3. 断言 `qtoid` 与外部订单号映射一致；断裂时进入风险事件。
4. 断言 live 路径只访问 gateway client/stub，不导入或直连 `xtquant/QMT`。

### 验收条件

- live 下单到成交有 QA 级 E2E 证据。
- 状态补推后本地订单/成交状态一致。
- 乱序或延迟回报不会破坏 `qtoid` 主线。
- 不一致、回报缺失、结构性缺失均触发阻断候选。

### 验证命令

```bash
poetry run pytest tests/core/test_gateway_client.py \
  tests/core/test_gateway_broker_adapter.py \
  tests/core/test_port_broker.py \
  tests/config/test_runtime.py
poetry run pytest tests/e2e -k "live or gateway"
poetry run ruff check quantide/core/runtime/gateway_client.py quantide/core/runtime/gateway_broker.py quantide/core/runtime/gateway_market.py quantide/core/runtime/port_broker.py quantide/web/pages/live.py quantide/web/pages/trade_main.py tests/e2e
```

## 9. P6：风险事件中心、阻断、告警、恢复

### 目标

实现并验收风险事件中心、账户/策略级阻断、顶部持续告警、关闭即解除阻断、二次确认、持久化和重启恢复。

### 仓库切片

- `quantide/data/sqlite.py`
- `quantide/core/domain/events.py`
- `quantide/core/errors.py`
- `quantide/service/strategy_runtime.py`
- `quantide/core/runtime/gateway_broker.py`
- `quantide/service/sim_broker.py`
- `quantide/web/layouts/main.py`
- `quantide/web/components/header.py`
- `quantide/web/pages/trade_main.py`
- `quantide/web/pages/live.py`
- 新增建议：`quantide/service/risk_events.py`
- 新增建议：`quantide/web/pages/risk_events.py`
- 新增建议：`tests/service/test_risk_events.py`
- 新增建议：`tests/e2e/web/test_risk_event_blocking_flow.py`

### 执行项

1. 定义风险事件数据模型：事件类型、账户、策略、状态、阻断范围、`qtoid`、外部映射、触发原因、诊断上下文、关闭信息。
2. 定义阻断状态模型：阻断账户/策略、触发事件、自动交易是否禁止、恢复来源。
3. 在 paper/live 交易异常入口接入风险事件服务。
4. 顶部持续告警读取未关闭风险事件；关闭前必须二次确认并明确提示自动交易将恢复。
5. 关闭告警与解除阻断保持同一动作；取消关闭则阻断不变。
6. 应用重启时恢复仍成立的阻断；已关闭历史事件不因重启自动重建，除非重新检测到异常。
7. 数据损坏检测接入只读诊断模式：阻断写操作、自动交易、回测执行和后台写任务，保留查看/导出/修复入口。

### 验收条件

- 当前未关闭和历史已关闭风险事件均可查看。
- 支持按账户、策略、时间、状态、事件类型查询。
- 每条事件可追踪 `qtoid`、外部订单号映射、触发原因、阻断范围、关闭信息和诊断上下文。
- 被阻断后新的自动交易被拒绝，人工交易仍允许但持续显示显著风险告警。
- 二次确认取消不会解除阻断；确认关闭会立即解除阻断并恢复原自动交易状态。
- 重启恢复语义符合 `.dev/specs/06-release-readiness.md` 第 3.4 节。
- SQLite 或 Parquet 损坏后不自动修复后继续写入。

### 验证命令

```bash
poetry run pytest tests/service/test_risk_events.py tests/e2e/web/test_risk_event_blocking_flow.py
poetry run pytest tests/e2e -k "risk or block or recovery"
poetry run pytest tests/service/test_sim_broker_paper_lifecycle.py tests/core/test_gateway_broker_adapter.py
poetry run ruff check quantide/data/sqlite.py quantide/core/domain quantide/service quantide/web tests/service tests/e2e
poetry run mypy quantide tests
```

## 10. P7：QA 放行矩阵与发布 gate

### 目标

把发布前 8 条强制 E2E 固化为单一放行命令和证据矩阵，任何缺失自动化证据都阻止发布。

### 仓库切片

- `tests/e2e/`
- `.dev/specs/three_mode_acceptance_checklist.md`
- `.github/workflows/`（如当前 CI 使用 GitHub Actions）
- `pyproject.toml`
- `tox.ini`

### 执行项

1. 为 8 条主链路建立稳定测试文件或 marker：
   - 初始化
   - 数据下载与补齐
   - 策略发现/加载
   - 回测运行
   - paper 下单到成交
   - live 下单到成交
   - 异常告警与阻断
   - 任务恢复与重启恢复
2. 增加一个发布 gate 命令，例如 `poetry run pytest -m "e2e and release_gate"`。
3. 在清单中记录每条链路的命令、测试文件、状态和最近证据。
4. CI gate 失败时禁止声称“发布前验收完成”。

### 验收条件

- 8 条主链路均为自动化 E2E，且可一键运行。
- gate 失败输出能定位到具体链路。
- `three_mode_acceptance_checklist.md` 的“当前证据状态”不再含 `暂无 QA 级 E2E`。
- 发布阻塞项全部有对应的自动化断言。

### 验证命令

```bash
poetry run pytest -m "e2e and release_gate"
poetry run pytest tests/e2e
poetry run ruff check tests/e2e
poetry run mypy quantide tests
```

## 11. 完成定义

本轮发布态收口只有在以下全部满足时才能结束：

1. P0-P7 均完成并有自动化证据。
2. `backtest / paper / live` 三种模式使用同一份策略代码零修改运行。
3. paper/live 都具备本地独立 stub 支撑的端到端自动验收。
4. `qtoid` 贯穿订单、成交、告警、日志、恢复和 UI 跳转。
5. 交易异常触发账户/策略级阻断，且不会静默继续自动交易。
6. 风险告警持续显示，关闭后可在风险事件中心追溯。
7. 重启后阻断恢复语义通过自动化验收。
8. 数据损坏后系统进入安全阻断/只读诊断路径。
9. QA 维护的 8 条发布前 E2E 全部通过。

若任何一项缺失，版本状态必须保持为“不可发布”。
