# E2E 准确性与数据契约

## 1. 文档定位

本文档定义 quantIDE 发布态 E2E 的准确性标准、测试数据契约、stub 行为和人工复核材料要求。它回答一个核心问题：固定输入数据下，系统不仅要“跑得通”，还必须证明策略、撮合、资产、收益和风险指标是正确的。

约束关系如下：

1. `.dev/specs/00-architecture.md` 仍是最高优先级架构决议文档。
2. 本文档是测试准确性、测试数据和 E2E 结果验收的权威约束。
3. `.dev/specs/06-release-readiness.md` 定义发布态门槛；本文档细化其中“全自动 E2E 回归”的数据和结果要求。
4. `.dev/specs/three_mode_acceptance_checklist.md` 负责记录当前证据、缺口与放行判定，不替代本文档。

本文档优先约束 `tests/e2e/`、`tests/assets/`、本地 Tushare stub、本地 gateway stub、回测/仿真/实盘 E2E 文档和 release gate。

## 2. 核心原则

量化交易项目的测试目标不是证明代码没有抛异常，而是证明固定市场数据、固定策略、固定撮合规则下的交易过程和最终指标正确。

发布态 E2E 必须满足以下原则：

1. 使用可审计的真实市场样本数据，不使用随机构造行情替代发布 gate。
2. 所有外部数据源和交易网关在 CI 中都由本地 stub 提供。
3. stub 从 `tests/assets/` 读取固定数据，不能在 release gate 中访问真实 Tushare、真实 qmt-gateway、QMT 或 xtquant。
4. 策略结果必须和一个可复核基准比较，至少包括交易时点、成交价格、资产变化、收益率、年化收益、最大回撤、Sharpe ratio。
5. 每条发布态 E2E 都必须有同目录或 spec 中的场景说明，说明输入数据、交互流程、预期交易、预期资产与指标。
6. 基准结果必须可重复生成、可人工复核，并以机器可读文件提交到仓库。

## 3. 测试数据契约

### 3.1 数据目录

发布态 E2E 的固定数据统一放在 `tests/assets/` 下。允许继续保留现有 Parquet fixture，但必须为发布 gate 补齐结构化 manifest。

推荐目录结构如下：

```text
tests/assets/
  market/
    calendar.parquet
    stocks.parquet
    daily_bars.parquet
    adjust_factor.parquet
    limit_price.parquet
    st_info.parquet
  scenarios/
    dual_ma_2024.yml
    paper_fill_2024.yml
    live_gateway_2024.yml
  baselines/
    dual_ma_2024.backtest.json
    dual_ma_2024.paper.json
    dual_ma_2024.live.json
```

当前已有文件可以逐步迁移或映射：

1. `baseline_calendar.parquet` 对应交易日历。
2. `2024_bars.parquet` 和 `bars_2021_2024.small.parquet` 对应日线行情。
3. `2024_adjust_factor.parquet` 对应复权因子。
4. `2024_limit_price.parquet` 对应涨跌停价格。
5. `2024_st_info.parquet` 对应 ST 状态。

### 3.2 数据来源要求

测试数据必须来自真实市场数据快照。允许来源包括：

1. 从真实 Tushare 下载后脱敏、裁剪并固化到 `tests/assets/`。
2. 从公开研报、公开行情文件或其它可合法使用的数据源裁剪后固化。
3. 从外部回测平台导出的、可人工复核的结果数据。

禁止事项：

1. 发布 gate 不得在运行时访问真实 Tushare。
2. 发布 gate 不得依赖网络可用性、账号 token、Tushare 积分、交易时段或当前日期。
3. 发布 gate 不得使用随机价格序列证明策略指标正确。

### 3.3 数据质量检查

每个数据集进入 release gate 前必须有数据完整性测试：

1. 交易日历覆盖场景要求的起止日期。
2. 股票列表包含场景中出现的所有证券。
3. 日线行情包含 `asset, frame, open, high, low, close, volume, amount, adjust, is_st, up_limit, down_limit`。
4. 每条行情的 OHLC 关系合法。
5. 停牌日、涨跌停日、ST 状态和复权因子在场景关键日期可被明确复核。
6. 数据文件有 schema、行数、日期范围和内容 hash 记录。

## 4. 本地 Tushare Stub

### 4.1 目标

本地 Tushare stub 用于替代真实 Tushare API，使初始化、数据下载、数据补齐和数据校验 E2E 在 GitHub Actions 与本地环境中完全一致。

### 4.2 行为要求

Tushare stub 必须从 `tests/assets/` 读取数据，并模拟项目实际使用的 Tushare 接口返回形状。

最低接口能力：

1. 交易日历。
2. 股票列表。
3. 日线行情。
4. 复权因子。
5. 涨跌停价格。
6. ST 数据。

stub 必须支持：

1. 按日期区间过滤。
2. 按证券过滤。
3. 返回空数据。
4. 注入限流、认证失败、网络失败和字段缺失。
5. 记录调用参数，用于断言系统没有请求超出场景边界的数据。

### 4.3 验收要求

数据下载 E2E 不应只断言“下载完成”，还必须断言：

1. 下载后的 Parquet 行数、日期范围、证券集合与 manifest 一致。
2. 关键日期的行情、复权、涨跌停和 ST 字段与源 fixture 一致。
3. 数据补齐重复运行是幂等的。
4. 断点重试不会产生重复行或覆盖错误数据。

## 5. 本地 Gateway Stub

### 5.1 目标

gateway stub 用于替代真实 qmt-gateway，使 `paper` 和 `live` E2E 可以在本地与 GitHub Actions 中运行。它不是简单 ping 服务，而是脚本化交易与行情环境。

### 5.2 数据来源

gateway stub 的行情、资产、持仓、订单、成交和回报脚本必须来自 `tests/assets/` 的 scenario 文件。

最低数据内容：

1. 初始资产：现金、总资产、市值、冻结资金。
2. 初始持仓：证券、数量、可用数量、成本、市值。
3. 行情流：逐条 quote 或 bar，带时间戳。
4. 交易回报：委托确认、部分成交、全部成交、撤单、拒单、废单。
5. 异常脚本：断连、乱序回报、延迟回报、状态补推。

### 5.3 行为要求

gateway stub 必须支持：

1. 资产、持仓、订单、成交查询。
2. 买入、卖出、撤单。
3. 行情 WebSocket 推送。
4. 登录或最小鉴权。
5. qtoid 与外部订单号映射。
6. 部分成交、拒单、废单、撤单失败。
7. 断连后恢复与状态补推。

### 5.4 结果校验

gateway stub 驱动的 E2E 必须校验：

1. 主体系统内部订单主键始终为 `qtoid`。
2. 外部订单号只作为映射和诊断字段。
3. 每次成交后现金、持仓、冻结资金和资产总值变化正确。
4. 乱序和补推不会造成重复成交或资产重复扣减。
5. 异常状态能触发风险事件和阻断。

## 6. 三模式 E2E 场景文档

每个发布态 E2E 场景必须有场景文档。场景文档可以放在 `.dev/specs/` 中，也可以放在 `tests/e2e/scenarios/` 中；但 release gate 必须能从测试名追溯到文档。

每个场景文档必须包含：

1. 场景目标。
2. 使用的数据文件和 hash。
3. 策略名称、参数和运行模式。
4. 手续费、滑点、成交约束、涨跌停、停牌规则。
5. 用户交互流程或 HTTP/API 调用流程。
6. 逐日或逐事件的预期交易。
7. 每笔订单的预期 `qtoid`、方向、数量、价格、状态。
8. 每笔成交后的现金、持仓、市值、总资产。
9. 最终指标：总收益、年化收益、最大回撤、Sharpe ratio、交易次数、胜率。
10. 可接受误差范围和舍入规则。
11. 外部基准来源，例如 JoinQuant 回测、研报结果或独立脚本计算结果。
12. 人工复核注意事项。

## 7. Backtest E2E 基准

### 7.1 目标

backtest E2E 必须证明固定数据下策略结果完全可重复，并且关键指标正确。

### 7.2 最低场景

以内置 example 策略为第一条发布态场景：

1. 策略：`quantide/strategies/example/dual_ma.py`
2. 数据：`tests/assets/` 中固定真实日线数据。
3. 日期范围：由场景 manifest 明确指定。
4. 初始资金、手续费、滑点和撮合规则固定。
5. 预期结果存入 `tests/assets/baselines/`。

### 7.3 必须校验

backtest E2E 必须校验：

1. 策略运行期间每个交易信号日期正确。
2. 每笔订单和成交日期、数量、价格正确。
3. 现金、持仓、市值、总资产逐步变化正确。
4. 最终收益曲线与 baseline 一致。
5. 年化收益、最大回撤、Sharpe ratio 与 baseline 一致。
6. 多次运行结果完全一致。

如果与外部平台比较，必须记录外部平台配置差异，例如复权方式、手续费、成交价格、停牌处理和日内成交假设。

## 8. Paper E2E 基准

paper E2E 必须证明同一份策略代码在实时行情驱动下，通过本地主体仿真 broker 完成下单、成交、资产变化和风险处理。

最低场景：

1. gateway stub 推送固定行情。
2. RuntimeBootstrap 进入 `paper` 模式。
3. 策略接收行情后发出订单。
4. 本地仿真 broker 根据行情和撮合规则成交。
5. E2E 校验资产、持仓、订单、成交、收益和风险事件。

必须覆盖：

1. 正常买入到成交。
2. 正常卖出到成交。
3. 涨跌停或无成交量导致未成交。
4. 异常注入导致自动交易阻断。
5. 重启后阻断状态恢复。

## 9. Live E2E 基准

live E2E 必须证明主体通过 gateway 协议完成接近真实的下单、回报、查询和恢复链路。该测试仍使用本地 gateway stub，不访问真实 QMT。

最低场景：

1. gateway stub 提供初始资产和持仓。
2. gateway stub 推送行情。
3. 策略或测试动作提交买入/卖出。
4. gateway stub 返回委托确认、成交回报和查询结果。
5. 主体系统用 `qtoid` 闭合订单生命周期。
6. E2E 校验资产、持仓、订单、成交和风险事件。

必须覆盖：

1. 全部成交。
2. 部分成交后撤单。
3. 拒单或废单。
4. 回报乱序。
5. 断连重连与补推。
6. qtoid 映射断裂触发阻断。

## 10. 指标基准与误差规则

指标计算必须有单独测试覆盖，并在 E2E 中做端到端校验。

最低指标：

1. 总收益。
2. 年化收益。
3. 最大回撤。
4. Sharpe ratio。
5. 交易次数。
6. 胜率。
7. 手续费总额。

误差规则：

1. 金额类默认精确到分，除非场景文档另有说明。
2. 比率类默认允许 `1e-6` 以内误差。
3. 指标 baseline 必须记录计算公式、年化天数、无风险收益率和输入序列。
4. 如果与外部平台结果不同，必须在场景文档中解释差异来源，不能只放宽误差。

## 11. Release Gate 要求

发布态 release gate 至少包含：

```bash
poetry run pytest -m "e2e and release_gate" tests/e2e
```

该命令必须在无外部服务、无真实 token、无真实 gateway 的情况下通过。

进入 release gate 的 E2E 必须满足：

1. 使用 `tests/assets/` 固定数据。
2. 使用本地 Tushare stub 或 gateway stub。
3. 校验过程数据和最终指标。
4. 校验 baseline 文件未漂移。
5. 输出失败时能定位到具体日期、订单、成交、资产或指标差异。

## 12. 禁止以低质量断言替代准确性验收

以下断言不能单独作为发布态准确性证据：

1. HTTP 状态码为 200。
2. 页面包含某段文字。
3. 策略运行未抛异常。
4. 订单列表不为空。
5. 资产大于 0。
6. 指标字段存在但不比较数值。

这些断言可以作为辅助检查，但 release gate 必须包含数据级、交易级和指标级断言。

## 13. 渐进实施顺序

建议按以下顺序实施：

1. 为现有 `tests/assets/` 建立 manifest 和数据质量测试。
2. 实现本地 Tushare stub，并把初始化下载 E2E 改为数据级断言。
3. 扩展 gateway stub，使其从 scenario 文件读取行情、资产、订单和成交脚本。
4. 为 example 策略建立 backtest baseline。
5. 增加 paper E2E 的行情驱动、撮合和资产校验。
6. 增加 live E2E 的 gateway 状态机和 qtoid 校验。
7. 增加异常阻断与重启恢复 E2E。
8. 将所有场景纳入 `release_gate`。

完成这些工作前，当前 E2E 只能证明基础流程可用，不能证明量化结果准确。
