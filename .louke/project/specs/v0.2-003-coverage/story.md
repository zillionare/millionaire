# Millionaire Coverage — Story

## 1. 测试基础设施

作为开发者，我需要建立统一的测试基础设施，以便高效地为所有模块编写和运行单元测试。

- **pytest 配置**: 统一 `pytest.ini` 或 `pyproject.toml` 中的 pytest 配置（`--cov=quantide`, `--cov-report=term`, `--cov-report=html`）
- **覆盖率阈值**: CI 中强制 ≥95% 整体覆盖率，单模块不低于 80%
- **Mock 框架**: 统一使用 `unittest.mock` / `pytest-mock`，为数据层提供 mock 行情数据、mock 数据库
- **Fixture 共享**: 在 `tests/unit/conftest.py` 中集中管理跨模块 fixture（mock 日历、mock 行情、mock 网关）
- **测试隔离**: 每个测试用例独立清理状态，不依赖执行顺序

## 2. quantide/core/ 单测

作为开发者，我需要为业务核心模块编写单元测试，确保核心逻辑的正确性。

### 2.1 领域层
- `core/domain/events.py`: 事件对象的创建、序列化、反序列化
- `core/domain/` 其他模块: 领域对象的构造和校验

### 2.2 运行时
- `core/runtime/clock_bridge.py`: 时钟桥接的启动、停止、心跳
- `core/runtime/gateway_broker.py`: 网关代理的连接、断开、重连、下单流程（当前 80%）
- `core/runtime/gateway_client.py`: 客户端连接管理、消息收发（当前 75%）
- `core/runtime/modes.py`: 运行模式切换（当前 89%）
- `core/runtime/port_broker.py`: 端口代理的注册、路由（当前 72%）

### 2.3 策略与调度
- `core/strategy.py`: 策略生命周期（创建、初始化、运行、停止）（当前 79%）
- `core/strategy_discovery.py`: 策略发现与加载（当前 82%）
- `core/scheduler.py`: 任务调度（当前 94%）

### 2.4 其他核心模块
- `core/enums.py`: 枚举定义与转换（当前 75%）
- `core/message.py`: 消息协议编解码（当前 88%）
- `core/errors.py`: 错误类型（当前 99%）
- `core/sdk_metadata.py`: SDK 元数据（当前 87%）
- `core/ports/broker.py`: 经纪人端口抽象（当前 84%）
- `core/ports/clock.py`: 时钟端口（当前 73%）
- `core/ports/data_fetcher.py`: 数据获取端口（当前 65%）
- `core/ports/market_data.py`: 行情数据端口（当前 62%）

## 3. quantide/data/ 单测

作为开发者，我需要为数据层编写单元测试，确保数据获取、存储和校验的正确性。

### 3.1 数据获取
- `data/fetchers/tushare.py`: Tushare 数据获取的请求构建、响应解析、错误处理（当前 74%）
- `data/fetchers/registry.py`: 获取器注册与发现（当前 92%）

### 3.2 数据模型
- `data/models/calendar.py`: 交易日历模型（当前 90%）
- `data/models/daily_bars.py`: 日线数据模型（当前 85%）
- `data/models/stocks.py`: 股票信息模型（当前 91%）
- `data/models/app_state.py`: 应用状态模型（当前 88%）
- `data/models/index_bars.py`: 指数数据模型（当前 0%）

### 3.3 数据存储
- `data/stores/base.py`: 基础存储操作（当前 79%）
- `data/stores/index_bars.py`: 指数数据存储（当前 38%）
- `data/sqlite.py`: SQLite 数据库操作（当前 90%）

### 3.4 工具与辅助
- `data/helper.py`: 数据辅助函数（当前 49%）
- `data/utils/resampler.py`: 数据重采样（当前 83%）

## 4. quantide/service/ 单测

作为开发者，我需要为服务层编写单元测试，确保后台服务的可靠运行。

### 4.1 策略运行时
- `service/strategy_runtime.py`: 策略运行时管理（当前 65%）
- `service/discovery.py`: 服务发现（当前 57%）
- `service/registry.py`: 服务注册（当前 90%）
- `service/runner.py`: 策略运行器（当前 94%）

### 4.2 经纪人服务
- `service/abstract_broker.py`: 抽象经纪人接口（当前 54%）
- `service/backtest_broker.py`: 回测经纪人（当前 93%）
- `service/sim_broker.py`: 仿真经纪人（当前 87%）

### 4.3 数据与行情
- `service/datafeed.py`: 数据馈送服务（当前 22%）
- `service/livequote.py`: 实时行情服务（当前 72%）

### 4.4 其他服务
- `service/backtest_logs.py`: 回测日志（当前 91%）
- `service/grid_search.py`: 网格搜索（当前 68%）
- `service/init_wizard.py`: 初始化向导（当前 80%）
- `service/metrics.py`: 指标计算（当前 96%）
- `service/trade_lightning.py`: 闪电交易（当前 71%）
- `service/triple_barrier.py`: 三柱线方法（当前 96%）

## 5. quantide/web/components/ 单测

作为开发者，我需要为 UI 组件库编写单元测试，确保前端组件的正确渲染和交互。

- `web/components/analysis/kline_chart.py`: K 线图组件（当前 26%）
- `web/components/analysis/stock_list.py`: 股票列表组件（当前 33%）
- `web/components/header.py`: 页面头部组件（当前 100% — 验证已有测试）
- `web/components/sidebar.py`: 侧边栏组件（当前 100% — 验证已有测试）
- `web/components/toast.py`: Toast 通知组件（当前 100% — 验证已有测试）
- `web/components/runtime_params.py`: 运行时参数组件（当前 100% — 验证已有测试）
- `web/components/asset_label.py`: 资产标签组件（当前 100% — 验证已有测试）

## 6. CI/CD 与质量门禁

作为开发者，我需要 CI/CD 流水线自动执行测试并强制执行覆盖率阈值。

- **CI 配置**: GitHub Actions 在 push/PR 时自动运行 `pytest --cov=quantide --cov-fail-under=95`
- **覆盖率报告**: 生成 HTML 报告并作为 CI artifact 上传
- **阈值**: 整体 ≥95%，单模块 ≥80%（低于 80% 的模块需要单独说明）
- **增量检查**: PR 新增代码覆盖率 ≥95%（可选，使用 diff-cover）
