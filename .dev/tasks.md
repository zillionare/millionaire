# 任务进度追踪

## 2026-04-03

### 交易日历模块开发 ✅ 完成

- [x] 阅读 `04-system_management.md` 文档，理解需求
- [x] 创建 `quantide/web/pages/system/` 目录结构
- [x] 实现后端 API (`calendar_page` 和 `calendar_sync`)
- [x] 更新 `app_factory.py` 挂载路由
- [x] 前端页面实现（年月切换、日历表格、休市日标记）
- [x] 截图与文档对比
- [x] 配置 Tushare Token 并完成系统初始化
- [x] 完成测试并更新文档

### 实现细节

1. **路由**: `/system/calendar` (GET) 和 `/system/calendar/sync` (POST)
2. **数据来源**: 从 `Calendar` 模型加载 Parquet 格式的日历数据
3. **UI 特性**:
   - 年份/月份选择器，支持跳转
   - 交易日（绿色边框）、休市日（红色背景）、周末（灰色背景）清晰区分
   - "立即更新"按钮可同步 Tushare 最新数据
   - 响应式布局，使用 Tailwind CSS
4. **截图验证**: 已截图确认页面渲染正确，符合文档要求

### 下一步

根据 `04-system_management.md`，接下来需要实现：
- [ ] 股票列表查询模块 (`/system/stocks`)
- [ ] 行情数据查询模块 (`/system/market`)
- [ ] 系统设置模块（定时任务、交易网关、数据源）

## 2026-05-13

### E2E 准确性契约实施任务列表 ⏳

- 状态：`T01` 到 `T05` 已完成；当前恢复点为 `T06`。
- 任务来源：`.dev/specs/01-e2e-accuracy-contract.md`
- 拆分说明：`.dev/specs/01-e2e-accuracy-contract-task-breakdown.md`
- 本节用途：作为 `01-e2e-accuracy-contract` 的统一执行入口。重启或中断后，优先回到这里恢复状态。

### 恢复规则

1. 每次恢复时，先看“当前恢复点”“阻塞项”“最近验收命令”，再进入具体代码或 spec。
2. 只允许一个 `Txx` 任务处于进行中；完成后再推进下一个，避免同时展开 backtest、paper、live。
3. 每完成一个 `Txx`，必须同步更新状态、产出文件和验收命令。
4. 如果中途发现拆分粒度需要调整，先更新本节，再改代码。

### 当前恢复点

- 当前任务：`01-e2e-accuracy-contract` 已完成，等待下一轮需求。
- 当前阻塞：无。
- 最近产出：`tests/assets/manifest.yml`、`tests/data/test_assets_manifest.py`、`tests/assets/scenarios/dual_ma_2024.yml`、`tests/assets/baselines/dual_ma_2024.backtest.json`、`tests/assets/baselines/dual_ma_2024.paper.json`、`tests/assets/baselines/dual_ma_2024.live.json`、`tests/service/test_metrics.py`、`tests/e2e/backtest/test_dual_ma_accuracy.py`、`tests/e2e/paper/test_dual_ma_accuracy.py`、`tests/e2e/live/test_gateway_accuracy.py`、`tests/e2e/support/tushare_stub.py`、`tests/e2e/support/test_tushare_stub.py`、`tests/e2e/web/test_init_wizard_tushare.py`、`tests/e2e/support/gateway_stub.py`、`tests/e2e/support/test_gateway_stub.py`、`quantide/service/sim_broker.py`、`quantide/core/runtime/gateway_broker.py`、`quantide/core/runtime/modes.py`。
- 最近验收命令：`conda run -n quantide poetry run pytest tests/e2e/support/test_gateway_stub.py -q` 通过；`conda run -n quantide poetry run pytest tests/e2e/web/test_init_wizard_flow.py tests/e2e/web/test_system_settings_flow.py -q` 通过；`conda run -n quantide poetry run pytest tests/e2e -k tushare -q` 通过；`conda run -n quantide poetry run pytest tests/e2e/paper/test_dual_ma_accuracy.py -q` 通过；`conda run -n quantide poetry run pytest tests/service/test_sim_broker_paper_lifecycle.py tests/e2e/paper/test_dual_ma_accuracy.py -q` 通过；`conda run -n quantide poetry run pytest tests/e2e/live/test_gateway_accuracy.py tests/e2e/support/test_gateway_stub.py tests/core/test_gateway_broker_adapter.py -q` 通过。

### 任务总览

| ID | 状态 | 任务 | 依赖 | 关键输出 | 验收命令 |
| --- | --- | --- | --- | --- | --- |
| T01 | [x] | 资产目录与 manifest | 无 | `tests/assets/manifest.yml`、目录骨架、fixture 映射说明 | `conda run -n quantide poetry run pytest tests/data/test_assets_manifest.py` |
| T02 | [x] | 数据质量测试 | T01 | `tests/data/test_assets_manifest.py`、失败样例 | `conda run -n quantide poetry run pytest tests/data/test_assets_manifest.py` |
| T03 | [x] | dual_ma 场景与 baseline | T01 | `tests/assets/scenarios/dual_ma_2024.yml`、`tests/assets/baselines/dual_ma_2024.backtest.json` | `conda run -n quantide poetry run python scripts/demo_e2e_accuracy_contract.py` |
| T04 | [x] | metrics 公式与单测 | T03 | `tests/service/test_metrics.py` 更新 | `conda run -n quantide poetry run pytest tests/service/test_metrics.py` |
| T05 | [x] | backtest 准确性 E2E | T02,T03,T04 | `tests/e2e/backtest/test_dual_ma_accuracy.py`、必要的回测修复 | `conda run -n quantide poetry run pytest tests/e2e/backtest/test_dual_ma_accuracy.py` |
| T06 | [x] | Tushare stub 与下载 E2E | T01,T02 | `tests/e2e/support/` Tushare stub、下载数据级断言 | `conda run -n quantide poetry run pytest tests/e2e -k tushare` |
| T07 | [x] | Gateway stub 场景化 | T03 | scenario 驱动的 gateway stub | `conda run -n quantide poetry run pytest tests/e2e/support/test_gateway_stub.py` |
| T08 | [x] | paper 准确性 E2E | T05,T07 | `tests/e2e/paper/test_dual_ma_accuracy.py` | `conda run -n quantide poetry run pytest tests/e2e/paper/test_dual_ma_accuracy.py` |
| T09 | [x] | live 准确性 E2E | T07 | `tests/e2e/live/test_gateway_accuracy.py`、`tests/assets/baselines/dual_ma_2024.live.json`、必要的 gateway/runtime 修复 | `conda run -n quantide poetry run pytest tests/e2e/live/test_gateway_accuracy.py` |
| T10 | [x] | release gate 与证据文档 | T05,T06,T08,T09 | `release_gate` 标记、验收清单、readiness 更新 | `conda run -n quantide poetry run pytest -m "e2e and release_gate" tests/e2e` |

### 任务明细

#### T01 资产目录与 manifest

- [x] 建立 `tests/assets/market/`、`tests/assets/scenarios/`、`tests/assets/baselines/` 目录骨架。
- [x] 编写 `tests/assets/manifest.yml`，登记现有 fixture 的逻辑名称、schema、日期范围、内容 hash。
- [x] 明确 `baseline_calendar.parquet`、`2024_bars_ext_cols.parquet`、`2024_adjust_factor.parquet`、`2024_limit_price.parquet`、`2024_st_info.parquet` 的映射关系。
- [x] 锁定 demo 场景切片：`000001.SZ`、2024-01-02 到 2024-05-31。
- [x] 完成标准：后续测试不再散落硬编码 fixture 路径。

#### T02 数据质量测试

- [x] 新增 `tests/data/test_assets_manifest.py`。
- [x] 校验日线字段、唯一键、OHLC 关系、成交量非负、涨跌停关系。
- [x] 校验 demo 场景窗口内 `is_st=false`、`adjust=116.713`。
- [x] 加入缺失字段、重复行、越界日期的失败断言。
- [x] 完成标准：fixture 漂移时能精确报到文件、字段、日期、证券。

#### T03 dual_ma 场景与 baseline

- [x] 产出 `tests/assets/scenarios/dual_ma_2024.yml`。
- [x] 产出 `tests/assets/baselines/dual_ma_2024.backtest.json`。
- [x] 将外部 oracle 来源绑定到 `scripts/demo_e2e_accuracy_contract.py`。
- [x] 补充 baseline 生成说明，包括公式版本和人工复核状态。
- [x] 完成标准：交易表、每日资产序列和指标都能从 baseline 反查。

#### T04 metrics 公式与单测

- [x] 用 `dual_ma_2024` 每日总资产序列固定总收益、年化收益、最大回撤、Sharpe、胜率、手续费。
- [x] 为空序列、单日序列、全现金序列补边界测试。
- [x] 将误差规则统一为金额到分、比率 `1e-6`。
- [x] 完成标准：`tests/service/test_metrics.py` 成为指标真值入口之一。

#### T05 backtest 准确性 E2E

- [x] 新增 `tests/e2e/backtest/test_dual_ma_accuracy.py`。
- [x] 比较交易表、每日资产序列和最终指标。
- [x] 修复清仓后 gap fill 从过期持仓日期回填历史 `market_value` 的问题。
- [x] 回归验证 `tests/service/test_backtest_broker.py`、`tests/service/test_metrics.py`、`tests/strategies/example/test_dual_ma.py`。
- [x] 完成标准：backtest 闭环通过，且可纳入 release gate。

#### T06 Tushare stub 与下载 E2E

- [x] 在 `tests/e2e/support/tushare_stub.py` 中实现 `trade_cal`、`daily`、`adj_factor`、`stk_limit`、`stock_st` 等 fixture-backed 最小接口。
- [x] 支持空数据、限流、认证失败、网络失败、字段缺失注入，并在 `tests/e2e/support/test_tushare_stub.py` 中验证。
- [x] 将初始化下载 E2E 升级为数据级断言，在 `tests/e2e/web/test_init_wizard_tushare.py` 中验证真实下载链的落盘结果。
- [x] 完成标准：CI 无 token、无网络可跑通。

#### T07 Gateway stub 场景化

- [x] 将当前 gateway stub 收敛为 scenario 驱动状态机，并在 `tests/e2e/support/gateway_stub.py` 中支持 submit/cancel script。
- [x] 从 scenario 读取初始资产、持仓、行情流、订单回报和异常脚本；同时兼容 dataclass 和 dict 两种场景输入。
- [x] 支持 `qtoid` 到外部订单号映射，并允许查询快照只暴露 `order_id` 时仍由 adapter 还原内部 `qtoid`。
- [x] 完成标准：paper/live 共用同一组交易事实的基础 stub 已就绪，`tests/e2e/support/test_gateway_stub.py` 验证通过。

#### T08 paper 准确性 E2E

- [x] 新增 `tests/e2e/paper/test_dual_ma_accuracy.py`。
- [x] 校验实时行情驱动、本地仿真 broker 撮合、未成交和阻断恢复。
- [x] 完成标准：paper 与 backtest 使用同一策略源码，成交事实可复核。

#### T09 live 准确性 E2E

- [x] 新增 `tests/e2e/live/test_gateway_accuracy.py`。
- [x] 校验委托确认、部分成交、撤单、拒单、乱序、补推与重连。
- [x] 校验主体系统始终围绕 `qtoid` 闭合订单生命周期。
- [x] 完成标准：无真实 QMT、无真实 gateway 条件下仍可跑通 live 准确性场景。

#### T10 release gate 与证据文档

- [x] 为准确性 E2E 标注 `e2e` 和 `release_gate`。
- [x] 更新 `.dev/specs/three_mode_acceptance_checklist.md` 和相关 readiness 文档。
- [x] 确保失败时能定位到具体日期、订单、成交、资产或指标。
- [x] 完成标准：`e2e and release_gate` 命令在本地和 CI 均可执行。

### 第一阶段里程碑

- [x] 第一阶段只做到 `T05`，不提前展开 `T06` 到 `T10`。
- [x] 第一阶段完成后，当前恢复点从 `T01` 更新为 `T06`。
- [x] 第一阶段放行标准：backtest 交易、资产、指标三层断言全部稳定。
