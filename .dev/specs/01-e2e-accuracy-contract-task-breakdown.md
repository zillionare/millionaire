# E2E 准确性契约任务拆分

## 1. 文档定位

本文档将 `.dev/specs/01-e2e-accuracy-contract.md` 拆解为可执行的模块级子任务，用于指导后续实现、测试和 release gate 接入。

约束关系如下：

1. `.dev/specs/00-architecture.md` 是最高优先级架构约束。
2. `.dev/specs/01-e2e-accuracy-contract.md` 是准确性、测试数据、stub 行为和验收标准的权威来源。
3. `.dev/tasks.md` 是执行状态的统一入口；本文件保留任务拆分和模块边界，不作为进度真值来源。
4. 本文档只拆分实施任务，不替代原契约。
5. 运行命令时使用 conda 环境 `quantide`，例如 `conda run -n quantide poetry run pytest ...`。

## 2. 模块划分

本次工作拆为 10 个模块：

| 模块 | 责任边界 | 主要落点 |
| --- | --- | --- |
| M0 资产目录与 manifest | 固定测试数据的目录、schema、hash、场景索引 | `tests/assets/`、`tests/assets/manifest.*` |
| M1 数据质量校验 | 固定市场数据的完整性、合法性和可复核性 | `tests/assets/`、`tests/data/` |
| M2 Tushare stub | 替代真实 Tushare，支持正常返回和异常注入 | `tests/e2e/support/`、`quantide/data/fetchers/` |
| M3 Gateway stub | 替代 qmt-gateway，支持行情、订单、成交、查询、异常脚本 | `tests/e2e/support/gateway_stub.py` |
| M4 场景定义 | 三模式场景文件、baseline 文件和人工复核说明 | `tests/assets/scenarios/`、`tests/assets/baselines/` |
| M5 Backtest 准确性 | example 双均线回测的订单、资产、指标校验 | `quantide/service/runner.py`、`quantide/service/backtest_broker.py` |
| M6 Paper 准确性 | 实时行情驱动下本地仿真 broker 的撮合、资产、风险校验 | `quantide/service/sim_broker.py`、`quantide/service/strategy_runtime.py` |
| M7 Live 准确性 | gateway 协议链路、qtoid 生命周期、补推恢复校验 | `quantide/core/runtime/`、`quantide/service/qmt_broker.py` |
| M8 指标与误差 | 收益、年化、回撤、Sharpe、胜率、手续费的公式和误差规则 | `quantide/service/metrics.py`、`tests/service/test_metrics.py` |
| M9 Release gate | `e2e and release_gate` 标记、失败诊断和证据汇总 | `tests/e2e/`、`.dev/specs/three_mode_acceptance_checklist.md` |

## 3. M0 资产目录与 manifest

### 3.1 目录结构任务

- [ ] 建立 `tests/assets/market/`，承载交易日历、股票列表、日线、复权因子、涨跌停和 ST 数据。
- [ ] 建立 `tests/assets/scenarios/`，承载 backtest、paper、live 的场景 YAML。
- [ ] 建立 `tests/assets/baselines/`，承载机器可读 baseline JSON。
- [ ] 明确现有 fixture 到新目录的映射关系，不在第一阶段删除旧文件。
- [ ] 为 `2024_bars_ext_cols.parquet` 建立场景切片说明，锁定 `000001.SZ`、2024-01-02 到 2024-05-31。

### 3.2 manifest 任务

- [ ] 设计 manifest schema：文件路径、逻辑名称、schema、行数、日期范围、资产集合、内容 hash。
- [ ] 为每个 market 文件登记字段类型和唯一键。
- [ ] 为每个 scenario 登记依赖的数据文件和 baseline 文件。
- [ ] 为 baseline 登记生成来源、计算公式版本和人工复核状态。
- [ ] 提供 manifest 加载器，避免测试中散落硬编码路径。

### 3.3 验收

- [ ] 能从 manifest 反查每条 release gate 测试使用的数据文件。
- [ ] 任一 fixture 内容漂移时，测试能报出文件名、旧 hash、新 hash。
- [ ] manifest 不依赖真实 token、网络、当前日期或外部服务。

## 4. M1 数据质量校验

### 4.1 市场数据 schema 校验

- [ ] 校验日线字段至少包含 `asset, frame, open, high, low, close, volume, amount, adjust, is_st, up_limit, down_limit`。
- [ ] 校验 `asset + frame` 唯一。
- [ ] 校验 OHLC 关系合法：`low <= open/close <= high`。
- [ ] 校验 `volume`、`amount` 非负。
- [ ] 校验 `up_limit >= down_limit`，且关键交易日有涨跌停字段。

### 4.2 场景覆盖校验

- [ ] 校验交易日历覆盖每个 scenario 的起止日期。
- [ ] 校验股票列表包含 scenario 中所有证券。
- [ ] 校验日线、复权、涨跌停和 ST 数据可按 `asset + frame` 对齐。
- [ ] 校验 `000001.SZ` demo 场景窗口内 `is_st=false`、`adjust=116.713`。
- [ ] 增加缺失字段、重复行、越界日期的失败样例。

### 4.3 验收

- [ ] 数据质量测试失败时定位到文件、字段、日期、证券。
- [ ] 数据质量测试纳入普通测试集，并作为 release gate 的前置依赖。

## 5. M2 Tushare Stub

### 5.1 接口能力任务

- [ ] 实现 `trade_cal`，从固定交易日历返回指定区间。
- [ ] 实现 `stock_basic` 或项目当前使用的股票列表接口，返回固定股票列表。
- [ ] 实现 `daily`，返回指定证券和日期区间的 OHLCV。
- [ ] 实现 `adj_factor`，返回复权因子。
- [ ] 实现 `stk_limit`，返回涨跌停价格。
- [ ] 实现 `stock_st` 或等价 ST 查询能力，标准化缺失 ST 为 `false`。

### 5.2 行为与异常任务

- [ ] 支持按日期区间过滤。
- [ ] 支持按证券过滤。
- [ ] 支持返回空数据。
- [ ] 支持限流、认证失败、网络失败、字段缺失异常注入。
- [ ] 记录每次调用的接口名和参数，用于断言没有越界请求。
- [ ] 提供测试 fixture 注入 stub，避免真实 Tushare 被调用。

### 5.3 下载 E2E 任务

- [ ] 将初始化下载 E2E 改为读取 Tushare stub。
- [ ] 断言下载后的 Parquet 行数、日期范围、证券集合与 manifest 一致。
- [ ] 断言关键日期行情、复权、涨跌停和 ST 字段与源 fixture 一致。
- [ ] 增加重复运行幂等测试。
- [ ] 增加断点重试测试，确保不重复写入、不错误覆盖。

### 5.4 验收

- [ ] CI 中无 token、无网络时测试通过。
- [ ] 真实 Tushare 不会在 release gate 中被调用。
- [ ] 失败信息能指出越界请求或字段差异。

## 6. M3 Gateway Stub

### 6.1 场景脚本加载任务

- [ ] 从 `tests/assets/scenarios/*.yml` 读取初始资产、初始持仓、行情流、订单脚本和异常脚本。
- [ ] 支持同一 scenario 在 paper 和 live 中复用行情事实。
- [ ] 将 stub 当前硬编码行为收敛为可配置状态机。
- [ ] 为订单、成交、资产、持仓查询提供可复核快照。

### 6.2 协议能力任务

- [ ] 支持资产查询。
- [ ] 支持持仓查询。
- [ ] 支持订单查询。
- [ ] 支持成交查询。
- [ ] 支持买入、卖出、撤单。
- [ ] 支持行情 WebSocket 或测试内等价推送。
- [ ] 支持最小登录或鉴权流程。
- [ ] 支持 `qtoid` 与外部订单号映射。

### 6.3 交易状态任务

- [ ] 支持委托确认。
- [ ] 支持全部成交。
- [ ] 支持部分成交。
- [ ] 支持撤单成功。
- [ ] 支持撤单失败。
- [ ] 支持拒单。
- [ ] 支持废单。
- [ ] 支持乱序回报。
- [ ] 支持延迟回报。
- [ ] 支持断连重连和状态补推。

### 6.4 验收

- [ ] 每次成交后现金、持仓、冻结资金、总资产与 scenario 一致。
- [ ] 乱序和补推不会造成重复成交或资产重复扣减。
- [ ] `qtoid` 丢失或映射断裂时能触发阻断。

## 7. M4 场景定义与 baseline

### 7.1 通用场景 schema

- [ ] 定义 scenario YAML schema：目标、模式、数据文件、策略、参数、时间范围、手续费、滑点、撮合规则。
- [ ] 定义预期订单 schema：`qtoid`、信号日、交易日、方向、数量、价格、状态。
- [ ] 定义预期成交 schema：成交金额、费用、成交后现金、持仓、市值、总资产。
- [ ] 定义预期指标 schema：总收益、年化收益、最大回撤、Sharpe、交易次数、胜率、手续费。
- [ ] 定义异常脚本 schema：断连、乱序、拒单、字段缺失、限流。

### 7.2 Demo 场景任务

- [ ] 创建 `dual_ma_2024.yml`，覆盖 `000001.SZ` 双均线准确性场景。
- [ ] 创建 `dual_ma_2024.backtest.json`，记录 14 笔交易、每日资产序列和指标。
- [ ] 创建 `dual_ma_2024.paper.json`，复用交易事实并加入 paper 风险事件期望。
- [ ] 创建 `dual_ma_2024.live.json`，复用交易事实并加入 gateway 回报期望。
- [ ] 在场景说明中记录外部 oracle 来源：`scripts/demo_e2e_accuracy_contract.py`。

### 7.3 验收

- [ ] 测试名可追溯到 scenario 文件。
- [ ] scenario 文件可追溯到 market fixture 和 baseline。
- [ ] baseline 文件可由独立脚本重新生成，并能人工复核关键交易。

## 8. M5 Backtest 准确性

### 8.1 策略信号任务

- [ ] 固定使用 `quantide/strategies/example/dual_ma.py`。
- [ ] 校验 09:30 只能看到上一交易日及以前的完整日线。
- [ ] 校验 `fast=5`、`slow=10` 的金叉和死叉日期。
- [ ] 校验信号日与交易日偏移关系。

### 8.2 撮合与资产任务

- [ ] 校验订单按下一交易日 open 成交。
- [ ] 校验买入股数按 `floor(invest / (up_limit * (1 + commission)) / 100) * 100` 计算。
- [ ] 校验卖出全部可用持仓。
- [ ] 校验每笔成交后的现金、持仓、市值、总资产。
- [ ] 修复或约束空仓日期重新出现历史持仓市值的问题。
- [ ] 校验多次运行结果完全一致。

### 8.3 测试落点

- [ ] 新增 `tests/e2e/backtest/test_dual_ma_accuracy.py`。
- [ ] 必要时补充 `tests/service/test_runner.py`。
- [ ] 必要时补充 `tests/service/test_backtest_broker.py`。
- [ ] 测试同时比较交易表、每日资产序列和指标 baseline。

### 8.4 验收

- [ ] 14 笔交易与 spec 14.4 完全一致。
- [ ] 期末总资产为 `203259.114000`。
- [ ] 总收益、年化收益、波动率、Sharpe、最大回撤与 spec 14.5 一致。

## 9. M6 Paper 准确性

### 9.1 正常路径任务

- [ ] RuntimeBootstrap 能进入 `paper` 模式并使用同一份策略代码。
- [ ] gateway stub 推送固定行情。
- [ ] 策略接收行情后发出订单。
- [ ] 本地仿真 broker 按同一行 `open` 撮合。
- [ ] 校验买入成交、卖出成交、现金、持仓、资产和收益。

### 9.2 风险与恢复任务

- [ ] 覆盖涨停、跌停或无成交量导致未成交。
- [ ] 覆盖异常注入后自动交易阻断。
- [ ] 覆盖重启后阻断状态恢复。
- [ ] 覆盖重复行情或重复回报不会重复成交。

### 9.3 测试落点

- [ ] 新增 `tests/e2e/paper/test_dual_ma_accuracy.py`。
- [ ] 必要时补充 `tests/service/test_sim_broker_paper.py`。
- [ ] 必要时补充 `tests/service/test_strategy_runtime.py`。

### 9.4 验收

- [ ] paper 模式与 backtest 使用同一策略源码。
- [ ] paper 成交事实与 `dual_ma_2024.paper.json` 一致。
- [ ] 风险阻断能被测试稳定复现。

## 10. M7 Live 准确性

### 10.1 正常路径任务

- [ ] gateway stub 提供初始资产和持仓。
- [ ] gateway stub 推送行情。
- [ ] 策略或测试动作提交买入、卖出。
- [ ] gateway stub 返回委托确认、成交回报和查询结果。
- [ ] 主体系统使用 `qtoid` 闭合订单生命周期。

### 10.2 异常路径任务

- [ ] 覆盖全部成交。
- [ ] 覆盖部分成交后撤单。
- [ ] 覆盖拒单或废单。
- [ ] 覆盖回报乱序。
- [ ] 覆盖断连重连与补推。
- [ ] 覆盖 `qtoid` 映射断裂触发阻断。

### 10.3 测试落点

- [ ] 新增 `tests/e2e/live/test_gateway_accuracy.py`。
- [ ] 必要时补充 `tests/core/test_gateway_broker_adapter.py`。
- [ ] 必要时补充 `tests/core/test_gateway_client.py`。
- [ ] 必要时补充 `tests/core/test_gateway_market.py`。

### 10.4 验收

- [ ] 外部订单号只作为映射和诊断字段。
- [ ] 主体订单、成交、资产、持仓均围绕 `qtoid` 断言。
- [ ] 无真实 QMT、无真实 qmt-gateway 时 release gate 通过。

## 11. M8 指标与误差规则

### 11.1 指标公式任务

- [ ] 明确总收益公式。
- [ ] 明确年化收益公式和年化天数。
- [ ] 明确最大回撤公式。
- [ ] 明确 Sharpe ratio 公式和无风险收益率。
- [ ] 明确胜率公式。
- [ ] 明确手续费总额聚合规则。
- [ ] 明确金额类精确到分、比率类 `1e-6` 误差。

### 11.2 单元测试任务

- [ ] 扩展 `tests/service/test_metrics.py`，覆盖固定资产序列。
- [ ] 使用 `dual_ma_2024` 每日总资产序列作为端到端指标样例。
- [ ] 增加空序列、单日序列、全现金、清仓后资产不漂移的边界测试。
- [ ] 指标失败时输出指标名、预期值、实际值、误差。

### 11.3 验收

- [ ] E2E 与 metrics 单测使用同一套误差规则。
- [ ] 指标 baseline 记录公式、年化天数、无风险收益率和输入序列。

## 12. M9 Release Gate

### 12.1 标记与命令任务

- [ ] 为准确性 E2E 增加 `@pytest.mark.e2e`。
- [ ] 为发布 gate 场景增加 `@pytest.mark.release_gate`。
- [ ] 确保 `conda run -n quantide poetry run pytest -m "e2e and release_gate" tests/e2e` 可运行。
- [ ] 确保 release gate 不访问真实 Tushare、真实 gateway、QMT、xtquant、网络或当前日期。

### 12.2 失败诊断任务

- [ ] baseline 文件漂移时输出文件名和 hash 差异。
- [ ] 订单差异时输出 `qtoid`、日期、方向、数量、价格、状态。
- [ ] 成交差异时输出成交金额、费用、现金、持仓、资产。
- [ ] 指标差异时输出指标名、预期值、实际值、误差。
- [ ] 数据差异时输出文件、asset、frame、字段。

### 12.3 证据更新任务

- [ ] 更新 `.dev/specs/three_mode_acceptance_checklist.md`，记录当前证据、缺口和放行判定。
- [ ] 更新 release readiness 文档中准确性 gate 的状态。
- [ ] 将 demo 脚本输出与自动化测试结果关联。

### 12.4 验收

- [ ] release gate 至少覆盖 backtest、paper、live 三条场景。
- [ ] release gate 覆盖数据级、交易级、资产级和指标级断言。
- [ ] release gate 失败能定位到具体日期、订单、成交、资产或指标。

## 13. 建议实施顺序

1. M0：建立 assets 目录、manifest schema 和 fixture 映射。
2. M1：补齐数据质量测试，先把固定数据可信度锁住。
3. M8：把指标公式和误差规则用单测固定下来。
4. M4：落地 `dual_ma_2024` scenario 和 baseline。
5. M5：实现 backtest 准确性 E2E，优先暴露并修复资产序列问题。
6. M2：实现 Tushare stub，并将数据下载 E2E 升级为数据级断言。
7. M3：扩展 gateway stub 为 scenario 驱动状态机。
8. M6：实现 paper 准确性 E2E。
9. M7：实现 live 准确性 E2E。
10. M9：接入 release gate，并更新证据文档。

## 14. 第一批最小可交付

第一批任务只做 backtest 准确性闭环，避免同时展开 paper/live 导致排查面过大。

- [ ] `tests/assets/manifest.yml`：登记 `2024_bars_ext_cols.parquet`、`baseline_calendar.parquet` 和 demo 切片。
- [ ] `tests/assets/scenarios/dual_ma_2024.yml`：记录策略、参数、时间范围、手续费、撮合规则。
- [ ] `tests/assets/baselines/dual_ma_2024.backtest.json`：记录 14 笔交易、每日资产序列和指标。
- [ ] `tests/data/test_assets_manifest.py`：校验 manifest 和固定数据质量。
- [ ] `tests/service/test_metrics.py`：补齐 demo 指标公式测试。
- [ ] `tests/e2e/backtest/test_dual_ma_accuracy.py`：校验交易、资产序列和指标。
- [ ] 修复回测资产序列在清仓后重新出现历史持仓市值的问题。

第一批完成标准：

1. `conda run -n quantide poetry run pytest tests/data/test_assets_manifest.py tests/service/test_metrics.py tests/e2e/backtest/test_dual_ma_accuracy.py` 通过。
2. `conda run -n quantide poetry run pytest -m "e2e and release_gate" tests/e2e/backtest` 通过。
3. backtest 的交易表、每日资产序列、最终指标均与 baseline 一致。

## 15. 依赖关系

```text
M0 assets manifest
  -> M1 data quality
  -> M4 scenario/baseline
  -> M5 backtest accuracy
  -> M9 release gate

M0 assets manifest
  -> M2 tushare stub
  -> data download e2e
  -> M9 release gate

M4 scenario/baseline
  -> M3 gateway stub
  -> M6 paper accuracy
  -> M7 live accuracy
  -> M9 release gate

M8 metrics
  -> M5 backtest accuracy
  -> M6 paper accuracy
  -> M7 live accuracy
  -> M9 release gate
```

## 16. 暂不纳入范围

以下事项不作为本次任务拆分的必需项：

1. 真实 Tushare 在线回归。
2. 真实 QMT 或真实 qmt-gateway 联调。
3. 多资产、多策略、大规模性能压测。
4. 历史版本迁移和兼容逻辑。
5. UI 样式与前端交互改造。

这些事项可以在 release gate 准确性闭环建立后，再按单独 spec 拆分。
