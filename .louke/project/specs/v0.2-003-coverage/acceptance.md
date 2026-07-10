# Millionaire Coverage — Acceptance Criteria

- **Spec ID**: v0.2-003-coverage
- **创建日期**: 2026-07-09
- **对应 spec**: `.louke/project/specs/v0.2-003-coverage/spec.md`

> 验收标准集中处。spec.md 仅保留 FR/NFR 的需求描述与元数据 (testability/resolved/valid),
> 详细的可观察、可断言的通过条件放在本表里。
>
> 编号约定:
> - 每个 FR/NFR 单元内, AC-N 从 1 开始连续递增, 不可跨单元复用
> - 完整 AC 引用: **AC-FRXXXX-YY** (4 位 FR + 2 位 AC 序号), 与 test-plan/issue schema 一致
>
> Lex 阶段一/二审核时, 校验: (1) 本表存在; (2) spec.md 中出现的每个 FR/NFR 在本表都有对应节; (3) 每条 AC 都可被测试断言。

> **覆盖率基线** (2026-07-09): TOTAL 69% (15657 stmts / 4856 miss)。
> **目标**: 整体 ≥95%, 单模块 ≥80% (NFR-0010)。每条覆盖率类 AC 在 `poetry run pytest --cov=quantide --cov-report=term-missing` 下可直接断言。

---

## §1 测试基础设施

<a id="ac-fr-0101"></a>
## FR-0101 pytest 配置与覆盖率命令

### AC-1
- 项目根目录跑 `poetry run pytest --cov=quantide --cov-report=term-missing` → 终端输出每文件 stmts/miss/cover 表格, 不报错 (exit 0)
### AC-2
- 跑 `poetry run pytest --cov=quantide --cov-report=html:htmlcov` → 生成 `htmlcov/index.html` 文件, 内容包含可点击的源码链接
### AC-3
- 跑 `poetry run pytest --cov=quantide --cov-fail-under=95` → 当覆盖率 < 95% 时 exit 1 (当前 69% 应该 fail; lock 时 ≥95% 应该 pass)
### AC-4
- `pyproject.toml` 中 `[tool.pytest.ini_options]` 含 `asyncio_mode = "auto"` (与现有一致, 不破坏异步测试)
### AC-5
- 跑 `poetry run pytest tests/unit` 不跑 e2e 测试 (`tests/e2e/` 被排除或 e2e marker 自动 skip)
### AC-6
- 不存在 `pytest.ini` 或 `setup.cfg` (配置单一来源在 `pyproject.toml`)

<a id="ac-fr-0102"></a>
## FR-0102 覆盖率阈值与排除清单

### AC-1
- 跑 `poetry run pytest --cov=quantide --cov-fail-under=95` → exit 0 (整体 ≥95% 时)
### AC-2
- `quantide/core/__init__.py` / `quantide/data/services/__init__.py` 等空文件: 100% 覆盖 (0 stmts 或全部覆盖)
### AC-3
- 实施阶段若某模块 < 80% 但需要临时豁免: 人工 review artifact 或 PR description 必须包含 (模块名 / 当前覆盖 / 原因 / 补救 issue 链接); 该项是人工 review gate, 不伪装为 push CI 自动 gate
### AC-4
- `pyproject.toml` 的 `[tool.coverage.report]` 不修改 `exclude_lines` 默认值; 临时豁免只写入 `coverage-waivers.json`

<a id="ac-fr-0103"></a>
## FR-0103 Mock 框架与 Fixture 共享

### AC-1
- `tests/unit/conftest.py` 存在并被 pytest 自动加载 (无需 `import conftest`); 该文件提供 `env` 等共享 fixture
### AC-2
- `env` fixture (session scope) 提供 `manifest / universe / calendar / daily_bars / adj_factor / st_info / limit_price` 7 个属性, 任何单测可直接 `def test_xxx(env)` 获取
### AC-3
- 数据层 mock 使用 `unittest.mock.MagicMock` / `AsyncMock` / `patch` 或 pytest 内置 `monkeypatch`; 测试代码不依赖 `pytest-mock` 的 `mocker` fixture
### AC-4
- 时间依赖测试用 `@freeze_time("2024-01-02")` (freezegun) 或显式注入 `datetime`, 不用 `datetime.now()`
### AC-5
- 数据库 mock 用 `:memory:` SQLite 或 `tmp_path` 下的 SQLite 文件, `tests/` 目录不残留 .db / .sqlite

<a id="ac-fr-0104"></a>
## FR-0104 测试隔离与确定性

### AC-1
- 同一测试连续跑 100 次结果一致 (`for i in {1..100}; do poetry run pytest path/to/test.py::test_name; done`, 全部 pass; 不依赖 `pytest-count`)
### AC-2
- 任意测试可单独跑 (`poetry run pytest tests/unit/quantide/core/test_clock_bridge.py::test_backtest_clock_set_now_and_now`) 而不依赖其它测试状态
### AC-3
- 测试结束后, `tests/` 目录无新增 .db / .sqlite / .parquet / .log 等残留文件
### AC-4
- 测试不修改 `quantide.*` 任何模块级全局变量 (可通过 `_pytest.monkeypatch.undo()` 验证 — monkeypatch 自动还原)
### AC-5
- 全局可变状态 (module-level `dict`/`list`/`set` 在测试间共享) 在 conftest 中无定义, 或在 setup/teardown 中清空


---

## §2.2 quantide/core/ 单测

<a id="ac-fr-0201"></a>
## FR-0201 core/domain/ 单测

### AC-1
- `poetry run pytest tests/unit/quantide/core/domain/` 全 pass, 0 failure / 0 error
### AC-2
- `poetry run pytest --cov=quantide/core/domain --cov-report=term-missing` → `events.py` 覆盖率 = 100% (基线已 100%, 本 FR 维护)
### AC-3
- events 序列化 round-trip 测试: `event = Event.from_dict(d); e2 = Event.from_dict(event.to_dict()); assert e2 == event`
### AC-4
- 缺失必填字段的反序列化测试: `with pytest.raises(ValidationError)` (或文档约定的异常类型)
### AC-5
- `__init__.py` 100% 覆盖 (基线 100%)

<a id="ac-fr-0202"></a>
## FR-0202 core/runtime/clock_bridge 单测

### AC-1
- `poetry run pytest --cov=quantide/core/runtime/clock_bridge --cov-report=term-missing` → 覆盖率 ≥ 95% (基线 90%)
### AC-2
- `BacktestClockAdapter.set_now(t)` 后 `clock.now() == t` (精确相等, 不带时区)
### AC-3
- `BacktestClockAdapter.iter_frames(start, end, DAY)` 对给定交易日历 fixture 返回的首帧、末帧与帧数符合日历期望
### AC-4
- `SystemClockAdapter.set_now(t)` 抛 `RuntimeError` (live 模式不允许设置)
### AC-5
- 边界: `iter_frames` 的 start == end (单帧), start > end (空?) — 按现有实现断言

<a id="ac-fr-0203"></a>
## FR-0203 core/runtime/gateway_broker + gateway_client 单测

### AC-1
- `poetry run pytest --cov=quantide/core/runtime/gateway_broker --cov-report=term-missing` → 覆盖率 ≥ 90% (基线 80%)
### AC-2
- `poetry run pytest --cov=quantide/core/runtime/gateway_client --cov-report=term-missing` → 覆盖率 ≥ 90% (基线 75%)
### AC-3
- gateway_broker 下单适配: 给定 GatewayBrokerAdapter + fake GatewayClient, 调用 buy/sell/cancel 后 fake client 收到对应 HTTP form path 与 payload, 返回 `OrderAck` / `CancelAck`
### AC-4
- gateway_broker 查询适配: fake client 返回 positions/assets/orders/trades payload 后, query_* 方法输出字段对齐 `PositionView` / `AssetView` / `OrderView` / `Trade`
### AC-5
- gateway_broker 一致性错误: 网关返回 qtoid / external id 不一致 payload → 抛 `GatewayTradeStateConsistencyError`
### AC-6
- gateway_client 登录与 GET/POST: fake opener 返回 2xx JSON → `ensure_login` 只登录一次, `get_json` / `post_form` 返回解析后的 dict
### AC-7
- gateway_client 协议保护: 响应 `Content-Type: text/html` → 抛 `GatewayProtocolError`; 空 body → 返回 None
### AC-8
- gateway_client 地址与 cookie: `cookie_header()` 输出已有 cookie; `ws_url()` 将 http/https base_url 正确转换为 ws/wss

<a id="ac-fr-0204"></a>
## FR-0204 core/runtime/modes + port_broker 单测

### AC-1
- `poetry run pytest --cov=quantide/core/runtime/modes --cov-report=term-missing` → 覆盖率 ≥ 95% (基线 89%)
### AC-2
- `poetry run pytest --cov=quantide/core/runtime/port_broker --cov-report=term-missing` → 覆盖率 ≥ 85% (基线 72%)
### AC-3
- modes 枚举值测试: `assert Mode.BACKTEST != Mode.PAPER`, `Mode.value == "backtest"`
### AC-4
- 模式切换合法路径: `backtest → paper → live` 各自合法
### AC-5
- 模式切换非法路径 (例: `idle → live` 跳过 paper): 抛 `InvalidTransitionError` (或文档约定异常)
### AC-6
- PortBackedBroker 资产/持仓/委托适配: fake BrokerPort 返回 AssetView / PositionView / OrderView 后, wrapper 的 `asset` / `positions` / `orders` 输出旧 UI 可消费模型
### AC-7
- PortBackedBroker 交易方法透传: 调用 buy/sell/cancel/cancel_all/trade_target_pct 后, fake BrokerPort 收到相同 asset/shares/price/side 参数
### AC-8
- PortBackedBroker 状态映射: 网关订单状态字符串/整数/未知值映射为约定 `OrderStatus`, 未知值映射 `OrderStatus.UNKNOWN`

<a id="ac-fr-0205"></a>
## FR-0205 core/strategy + strategy_discovery + scheduler 单测

### AC-1
- `poetry run pytest --cov=quantide/core/strategy --cov-report=term-missing` → 覆盖率 ≥ 90% (基线 79%)
### AC-2
- `poetry run pytest --cov=quantide/core/strategy_discovery --cov-report=term-missing` → 覆盖率 ≥ 90% (基线 82%)
### AC-3
- `poetry run pytest --cov=quantide/core/scheduler --cov-report=term-missing` → 覆盖率 ≥ 95% (基线 94%)
### AC-4
- strategy 生命周期: 通过公开运行入口驱动一个测试策略, 生命周期日志/事件顺序符合 v0.2-001 AC-010-02 (`init` → `on_start` → 日内钩子 → `on_stop`)
### AC-5
- 参数注入: 默认参数 / 用户覆盖 / 类型校验失败抛错
### AC-6
- strategy_discovery 扫描: mock 文件系统 (有策略文件 / 无策略文件 / 损坏文件) → 断言发现列表正确
### AC-7
- scheduler.add_job / remove_job / list_jobs CRUD 测试
### AC-8
- scheduler 触发测试: mock 任务函数, 用 freezegun 推进时间 → 任务被执行 (断言 mock_called_once)

<a id="ac-fr-0206"></a>
## FR-0206 core/ 基础模块单测

### AC-1
- `poetry run pytest --cov=quantide/core/enums --cov-report=term-missing` → enums.py ≥ 90% (基线 75%)
### AC-2
- `poetry run pytest --cov=quantide/core/message --cov-report=term-missing` → message.py ≥ 95% (基线 88%)
### AC-3
- `poetry run pytest --cov=quantide/core/errors --cov-report=term-missing` → errors.py ≥ 99% (基线 99%, 保持)
### AC-4
- `poetry run pytest --cov=quantide/core/sdk_metadata --cov-report=term-missing` → sdk_metadata.py ≥ 95% (基线 87%)
### AC-5
- enums 转换: `enum.from_str("backtest") == Mode.BACKTEST`, 无效字符串抛 `ValueError`
### AC-6
- message 编解码 round-trip: `assert msg == decode(encode(msg))`
### AC-7
- errors 异常链: `raise ServiceError("x") from IOError("y")` → `e.__cause__ is not None`

<a id="ac-fr-0207"></a>
## FR-0207 core/ports/ 单测

### AC-1
- `poetry run pytest --cov=quantide/core/ports --cov-report=term-missing` → 整体 ≥ 90%
### AC-2
- `ports/broker.py` ≥ 90% (基线 84%)
### AC-3
- `ports/clock.py` ≥ 90% (基线 73%)
### AC-4
- `ports/data_fetcher.py` ≥ 85% (基线 65%)
### AC-5
- `ports/market_data.py` ≥ 85% (基线 62%)
### AC-6
- 抽象方法测试: 实例化抽象端口类抛 `TypeError` (不能用抽象方法直接实例化)
### AC-7
- mock 实现契约: 子类实现所有抽象方法 → 可正常实例化, 接口调用正常


---

## §2.3 quantide/data/ 单测

<a id="ac-fr-0301"></a>
## FR-0301 data/fetchers/ 单测

### AC-1
- `poetry run pytest --cov=quantide/data/fetchers --cov-report=term-missing` → 整体 ≥ 90%
### AC-2
- `tushare.py` ≥ 90% (基线 74%)
### AC-3
- `registry.py` ≥ 95% (基线 92%)
### AC-4
- tushare 请求构建: 给定参数 (ts_code, start_date, end_date), 断言生成的请求 body 含正确参数 (用 `unittest.mock.patch` 或 `monkeypatch` 拦截网络边界)
### AC-5
- 响应解析: mock 原始响应 (DataFrame dict) → fetcher 返回 domain 对象, 字段正确
### AC-6
- 错误处理: 网络错误 / 限流 (mock `requests.post` 抛 ConnectionError) → fetcher 抛 `FetchError` (或约定异常)
### AC-7
- 重试: tenacity 配置生效, mock 第一次失败 → 第二次调用成功 (断言 2 次调用)
### AC-8
- registry: `register(FooFetcher); resolve("foo") is FooFetcher`, 未注册 name 抛 `KeyError`

<a id="ac-fr-0302"></a>
## FR-0302 data/models/ 单测

### AC-1
- `poetry run pytest --cov=quantide/data/models --cov-report=term-missing` → 整体 ≥ 90%
### AC-2
- `calendar.py` ≥ 95% (基线 90%)
### AC-3
- `daily_bars.py` ≥ 95% (基线 85%)
### AC-4
- `stocks.py` ≥ 95% (基线 91%)
### AC-5
- `app_state.py` ≥ 95% (基线 88%)
### AC-6
- `index_bars.py` ≥ 80% (基线 0%, 从 0 起步 — 本 FR 主要交付)
### AC-7
- 构造测试: 给定合法字段 → 模型构造成功, 字段可访问
### AC-8
- 校验测试: 缺失必填字段 / 类型错误 → 抛 `ValidationError`
### AC-9
- 序列化 round-trip: `m == Model.from_dict(m.to_dict())`
### AC-10
- 查询方法测试 (calendar.is_trade_day / stocks.find_by_code 等): 给定输入 → 返回正确结果
### AC-11
- index_bars 关键 API 测试 (从 0 起步, 至少覆盖核心构造/查询/序列化)

<a id="ac-fr-0303"></a>
## FR-0303 data/stores/ + sqlite 单测

### AC-1
- `poetry run pytest --cov=quantide/data/stores --cov-report=term-missing` → 整体 ≥ 90%
### AC-2
- `stores/base.py` ≥ 90% (基线 79%)
### AC-3
- `stores/index_bars.py` ≥ 80% (基线 38%)
### AC-4
- `poetry run pytest --cov=quantide/data/sqlite --cov-report=term-missing` → sqlite.py ≥ 95% (基线 90%)
### AC-5
- 基础 CRUD: 用 `:memory:` SQLite, create / read / update / delete 单条记录 → 断言表内容
### AC-6
- 批量操作: `bulk_insert(rows)` → 表行数 = len(rows)
### AC-7
- 事务: 模拟事务回滚 → 数据未持久化
### AC-8
- 查询: 按索引 / 条件查询 → 返回正确结果集
### AC-9
- index_bars 关键路径 (从 38% 起步, 至少覆盖 CRUD + 批量写入 + 简单查询)
### AC-10
- sqlite.py 表创建 / 索引 / 备份 / 迁移核心路径

<a id="ac-fr-0304"></a>
## FR-0304 data/helper + utils/resampler 单测

### AC-1
- `poetry run pytest --cov=quantide/data/helper --cov-report=term-missing` → helper.py ≥ 80% (基线 49%, 大缺口)
### AC-2
- `poetry run pytest --cov=quantide/data/utils/resampler --cov-report=term-missing` → resampler.py ≥ 90% (基线 83%)
### AC-3
- helper 函数核心路径: 数据加载 / 格式转换 / 校验
### AC-4
- resampler: 日线 → 周线 / 月线 OHLC 重计算 (断言 open/close/high/low/vol 与期望一致)
### AC-5
- 缺失日期填充: 给定稀疏日期序列 → 补齐后日期连续


---

## §2.4 quantide/service/ 单测

<a id="ac-fr-0401"></a>
## FR-0401 service/ 策略运行时与执行器单测

### AC-1
- `poetry run pytest --cov=quantide/service/strategy_runtime --cov-report=term-missing` → ≥ 90% (基线 65%, 大缺口)
### AC-2
- `poetry run pytest --cov=quantide/service/discovery --cov-report=term-missing` → ≥ 85% (基线 57%, 大缺口)
### AC-3
- `poetry run pytest --cov=quantide/service/registry --cov-report=term-missing` → ≥ 95% (基线 90%)
### AC-4
- `poetry run pytest --cov=quantide/service/runner --cov-report=term-missing` → ≥ 95% (基线 94%)
### AC-5
- strategy_runtime: 通过公开启动/停止入口操作运行实例, 对外状态查询、日志或事件反映 `running` / `stopping` / `stopped` / `failed` / `finished` / `blocked` 等当前实现状态; 非法操作返回约定错误
### AC-6
- strategy_runtime 运行结果: mock strategy 正常完成 → 运行记录进入 `finished` 或约定完成状态, 清理后 active 列表不再包含该运行实例
### AC-7
- strategy_runtime 错误恢复: 模拟运行中异常 → 对外状态查询或错误事件包含失败原因, 后续清理/停止入口仍可调用
### AC-8
- discovery: mock 服务注册中心 → 扫描返回可用服务列表, 健康检查通过/失败分流
### AC-9
- registry: register / deregister / list CRUD 测试
### AC-10
- runner: 给定策略函数 → 启动执行器, 断言策略被调用, 异常时清理资源

<a id="ac-fr-0402"></a>
## FR-0402 service/ 三类 broker 单测

### AC-1
- `poetry run pytest --cov=quantide/service/abstract_broker --cov-report=term-missing` → ≥ 85% (基线 54%, 大缺口)
### AC-2
- `poetry run pytest --cov=quantide/service/backtest_broker --cov-report=term-missing` → ≥ 95% (基线 93%)
### AC-3
- `poetry run pytest --cov=quantide/service/sim_broker --cov-report=term-missing` → ≥ 92% (基线 87%)
### AC-4
- abstract_broker: 子类未实现抽象方法 → 实例化抛 `TypeError`
### AC-5
- backtest_broker 撮合: 给定订单 + 历史数据 → 断言成交价 / 成交量
### AC-6
- backtest_broker 滑点 / 手续费: 断言成交后账户余额变化符合公式
### AC-7
- sim_broker 部分成交测试: mock 部分成交场景 → 订单状态部分填充
### AC-8
- sim_broker 订单生命周期: pending → filled / cancelled / rejected

<a id="ac-fr-0403"></a>
## FR-0403 service/ 数据馈送与实时行情单测

### AC-1
- `poetry run pytest --cov=quantide/service/datafeed --cov-report=term-missing` → ≥ 80% (基线 22%, 极大缺口)
### AC-2
- `poetry run pytest --cov=quantide/service/livequote --cov-report=term-missing` → ≥ 90% (基线 72%)
### AC-3
- datafeed: 给定 fake DailyBars store, `get_bars(asset, start, end)` 返回规范列 (`asset/frame/open/high/low/close/volume/amount/...`) 与期望行数
### AC-4
- datafeed 错误/缺数据: store 抛异常或无数据 → 返回空 DataFrame, 不传播真实网络/数据库异常
### AC-5
- livequote: subscribe 后 mock tick 会触发订阅者回调; unsubscribe 后同一订阅者不再收到后续 tick
### AC-6
- livequote stream: subscribe 后向消息总线注入 mock quote → async stream 产出 `MarketEvent`; unsubscribe 后同一 symbol 不再产出事件
### AC-7
- livequote tick → bar 聚合: 给定 tick 序列 → 生成的 bar OHLC 与期望一致

<a id="ac-fr-0404"></a>
## FR-0404 service/ 其它服务单测

### AC-1
- `poetry run pytest --cov=quantide/service/backtest_logs --cov-report=term-missing` → ≥ 95% (基线 91%)
### AC-2
- `poetry run pytest --cov=quantide/service/grid_search --cov-report=term-missing` → ≥ 85% (基线 68%)
### AC-3
- `poetry run pytest --cov=quantide/service/init_wizard --cov-report=term-missing` → ≥ 90% (基线 80%)
### AC-4
- `poetry run pytest --cov=quantide/service/metrics --cov-report=term-missing` → ≥ 96% (基线 96%, 保持)
### AC-5
- `poetry run pytest --cov=quantide/service/trade_lightning --cov-report=term-missing` → ≥ 85% (基线 71%)
### AC-6
- `poetry run pytest --cov=quantide/service/triple_barrier --cov-report=term-missing` → ≥ 96% (基线 96%, 保持)
### AC-7
- backtest_logs: write / read / clean 核心路径
### AC-8
- grid_search: 给定参数网格 → 断言所有组合被执行, 结果聚合正确
### AC-9
- init_wizard: 步骤序列 / 校验 / 跳过 / 重试流程
### AC-10
- metrics: 给定收益序列 → 断言 Sharpe / Sortino / 最大回撤 与已知值匹配 (容差 ≤ 1e-6)
### AC-11
- trade_lightning: 快速下单 / 取消流程, 性能断言 (mock 时间)
### AC-12
- triple_barrier: 给定价格序列 → 标签生成结果与文档期望一致


---

## §2.5 quantide/web/components/ 单测

<a id="ac-fr-0501"></a>
## FR-0501 web/components/analysis/ 单测

### AC-1
- `poetry run pytest --cov=quantide/web/components/analysis --cov-report=term-missing` → 整体 ≥ 85%
### AC-2
- `kline_chart.py` ≥ 85% (基线 26%, 大缺口)
### AC-3
- `stock_list.py` ≥ 85% (基线 33%, 大缺口)
### AC-4
- `backtest_charts.py` ≥ 100% (基线 100%, 保持)
### AC-5
- kline_chart 渲染: 给定 OHLCV 数据 → 输出可解析的图表节点/HTML, 语义节点或 data 属性能对应日期、OHLC、成交量
### AC-6
- kline_chart 颜色规则: 涨绿 / 跌红 (断言 class 或颜色属性)
### AC-7
- stock_list 渲染: 给定股票列表 → 输出包含每个股票代码/名称的行或节点; 空列表显示约定空状态
### AC-8
- stock_list 过滤: 输入 "ma" → 输出仅含匹配股票的行
### AC-9
- stock_list 排序: 按代码升序 → 输出顺序正确
### AC-10
- backtest_charts (净值/回撤/热力图) 渲染测试: 给定数据 → 输出含 svg / canvas

<a id="ac-fr-0502"></a>
## FR-0502 web/components/ 通用组件单测 (验证类)

### AC-1
- `poetry run pytest --cov=quantide/web/components/header --cov-report=term-missing` → 100%
### AC-2
- `poetry run pytest --cov=quantide/web/components/sidebar --cov-report=term-missing` → 100%
### AC-3
- `poetry run pytest --cov=quantide/web/components/toast --cov-report=term-missing` → 100%
### AC-4
- `poetry run pytest --cov=quantide/web/components/runtime_params --cov-report=term-missing` → 100%
### AC-5
- `poetry run pytest --cov=quantide/web/components/asset_label --cov-report=term-missing` → 100%
### AC-6
- 五个组件的现有行为覆盖保留; 如删除或重写测试, 必须用等价 FR/AC 行为断言替代, 不允许仅靠删除测试提升通过率
### AC-7
- 重构任一组件时, 同步更新其测试; 重构后掉覆盖, 必须补回 100%

<a id="ac-fr-0503"></a>
## FR-0503 web/pages/ 页面模块单测

### AC-1
- `poetry run pytest --cov=quantide/web/pages --cov-report=term-missing` → 域整体 ≥ 90%, 且每个 `web/pages/*.py` / `web/pages/system/*.py` 单模块 ≥ 80%
### AC-2
- `strategy.py` / `trade_main.py` / `accounts.py` / `paper.py` / `live.py`: 给定 mock service 返回的策略、账户、订单、成交数据 → 页面输出包含 v0.2-002-ui 对应 FR 要求字段和按钮状态
### AC-3
- 表单校验: 本金 ≤ 0 / 空账户名 / 无策略选中 / 网关离线等输入 → 输出错误提示或 disabled 状态, 不调用下游真实服务
### AC-4
- `init_wizard.py`: 未初始化系统 → wizard 首步渲染; 已完成步骤 fixture → 从失败/待处理步骤继续; 可选步骤跳过显示待处理提示
### AC-5
- `data_*.py` 与 `system/*.py`: mock 任务/网关/完整性数据失败 → 只显示局部错误占位, 同页其它区域仍渲染
### AC-6
- 历史页面: 给定 orders/trades/positions fixture 和过滤条件 → 输出记录数、排序与字段值符合 v0.2-001 interfaces schema

<a id="ac-fr-0504"></a>
## FR-0504 web/auth + web/apis + middleware 单测

### AC-1
- `poetry run pytest --cov=quantide/web/auth --cov-report=term-missing` → auth 域整体 ≥ 90%, 且每个 `web/auth/*.py` 单模块 ≥ 80%
### AC-2
- `poetry run pytest --cov=quantide/web/apis --cov-report=term-missing` → APIs 域整体 ≥ 90%, 且每个 `web/apis/*.py` 单模块 ≥ 80%
### AC-3
- `poetry run pytest --cov=quantide/web/middleware --cov=quantide/web/middleware_init --cov=quantide/web/middleware_feature --cov-report=term-missing` → 三个 middleware 模块均 ≥ 80%
### AC-4
- 登录成功: 正确用户名/密码 → response 建立 session 并 redirect 到目标页; 登录失败 → 不建立 session, 返回错误文案
### AC-5
- 改密码: 旧密码错误 / 两次新密码不一致 / 成功 三个分支均有断言
### AC-6
- 未登录访问受保护路径 → redirect 到 `/login?next=...`; 登录后按 `next` 返回
### AC-7
- broker API: 有效 payload → 2xx + body 含业务 ID; 无效 payload → 4xx + 结构化错误; service 抛异常 → 5xx 或约定错误码
### AC-8
- analysis API: K 线/搜索参数有效、空结果、非法参数、下游失败四类分支都有断言
### AC-9
- middleware: 未初始化路由、A/B 类降级、认证拦截、异常转响应均有单测, 且不读取真实凭证


---

## §2.6 CI/CD 与质量门禁

<a id="ac-fr-0601"></a>
## FR-0601 CI 强制覆盖率门槛

### AC-1
- `.github/workflows/unit-coverage.yml` 存在, 触发条件: `push` 到 `releases/**` 与 `pull_request` 到 `main` / `releases/**`
### AC-2
- workflow 步骤使用项目当前依赖方式: `pip install poetry` → `poetry install --with test --no-interaction` → `poetry run pytest tests/unit --cov=quantide --cov-fail-under=95 --cov-report=term-missing --cov-report=json:coverage.json`
### AC-3
- 整体覆盖率 < 95%, 或覆盖率阈值检查脚本发现任何非豁免生产模块 <80% 时, workflow fail (exit 1), 阻断合并
### AC-4
- `.github/workflows/louke-ci.yml` 不被本 spec 修改 (Louke 项目自身维护)
### AC-5
- workflow 不引入 codecov 等第三方服务作为门禁

<a id="ac-fr-0602"></a>
## FR-0602 HTML 覆盖率报告 + 增量覆盖率 (可选)

### AC-1
- workflow 步骤追加 `--cov-report=html:htmlcov`, 紧跟 `actions/upload-artifact@v4`, artifact 名 `coverage-html`
### AC-2
- artifact 保留 30 天 (`retention-days: 30`)
### AC-3
- HTML 报告**不阻断** CI (即便生成失败也不 fail job)
### AC-4
- (可选) diff-cover 步骤: `pip install diff-cover` → `diff-cover coverage.xml --compare-branch=origin/main --fail-under=95` 或类似命令
### AC-5
- (可选) diff-cover 步骤默认 `continue-on-error: true`, 仅作 warning, 不阻断合并


---

## §2.7 其它 v0.2 已交付模块

<a id="ac-fr-0701"></a>
## FR-0701 notify/ 通知通道单测

### AC-1
- `poetry run pytest --cov=quantide/notify --cov-report=term-missing` → 域整体 ≥ 90%, 且每个 `quantide/notify/*.py` 单模块 ≥ 80%
### AC-2
- mail 通道: 给定事件 payload 和配置 → 生成主题/正文/收件人正确; SMTP 成功时返回成功状态
### AC-3
- mail 通道失败: SMTP 连接失败 / 鉴权失败 / 缺少收件人 → 抛约定异常或返回失败结果, 错误消息不包含密码
### AC-4
- dingtalk 通道: 给定事件 payload → webhook JSON 含 title、text、事件类型; HTTP 2xx 成功
### AC-5
- dingtalk 通道失败: HTTP 4xx/5xx / timeout / 缺失 webhook → 失败结果可断言, 日志不泄露 webhook secret
### AC-6
- notify 导出/工厂: 已知通道可解析, 未知通道抛 `KeyError` 或约定异常

<a id="ac-fr-0702"></a>
## FR-0702 strategies/ 内置与示例策略单测

### AC-1
- `poetry run pytest --cov=quantide/strategies --cov-report=term-missing` → 域整体 ≥ 90%, 且每个策略模块单模块 ≥ 80%
### AC-2
- dual_ma: 给定短均线上穿长均线行情 → 产生买入信号或调用 broker buy; 下穿 → 产生卖出信号或调用 broker sell
### AC-3
- dual_ma: 均线窗口不足 / 无交叉 / 缺失价格 → 不下单或返回约定空信号
### AC-4
- pullback_sell: 回落超过阈值且有持仓 → 产生卖出; 未超过阈值或无持仓 → 不卖出
### AC-5
- cost_stop_loss: 当前价低于成本止损阈值 → 只卖宿主持仓; 当前价高于阈值 / 成本缺失 → 不卖出或抛约定异常
### AC-6
- 测试断言策略外部输出或 broker 边界调用, 不断言私有 helper 调用次数

<a id="ac-fr-0703"></a>
## FR-0703 config/ 与 app bootstrap 单测

### AC-1
- `poetry run pytest --cov=quantide/config --cov=quantide/app --cov=quantide/app_factory --cov-report=term-missing` → `config/*.py`、`app.py`、`app_factory.py` 单模块均 ≥ 80%, 合计域整体 ≥ 90%
### AC-2
- dev_stubs: 安装/卸载/重复安装/非法配置四类路径均有断言, 且不污染真实 HOME 或用户配置
### AC-3
- paths/settings/branding: 默认值、环境变量覆盖、路径解析、品牌文本导出均有断言
### AC-4
- app_factory: 未初始化系统 → 注册/返回 init-wizard 路由; 已初始化系统 → 注册/返回登录或主界面路由
### AC-5
- app_factory 依赖注入: 给定 mock settings/services → app 对象创建成功, route 列表或 handler 可观察
### AC-6
- app/app_factory 错误路径: 缺少配置目录或无效配置 → 返回约定错误或抛约定异常, 不启动真实 Web server


---

## §8 非功能需求

<a id="ac-nfr-0010"></a>
## NFR-0010 覆盖率阈值与豁免机制

### AC-1
- 跑 `poetry run pytest --cov=quantide --cov-fail-under=95` → 当覆盖率 < 95% 时 exit 1; ≥ 95% 时 exit 0
### AC-2
- 跑 `poetry run pytest --cov=quantide/core --cov-fail-under=80` → 单模块 ≥ 80% 时 exit 0; < 80% 时 exit 1
### AC-3
- `quantide/core/__init__.py` / `quantide/data/services/__init__.py` 等空 `__init__.py` 100% 覆盖 (0 stmts 时为 100% 自动)
### AC-4
- 临时豁免模块必须写入 `.louke/project/specs/v0.2-003-coverage/coverage-waivers.json`, 且每条包含 `module / current_coverage / reason / expires_at / followup_issue`; 人工 review artifact 或 PR description 说明豁免理由
### AC-5
- `pyproject.toml` 的 `[tool.coverage.report]` `exclude_lines` 不修改默认值 (与现有配置一致)
### AC-6
- 默认豁免清单 `coverage-waivers.json` 的 `waivers` 为空; 除空 `__init__.py` 外, 其它模块必须达 ≥80% 或走临时豁免申请

<a id="ac-nfr-0020"></a>
## NFR-0020 测试隔离与确定性

### AC-1
- 同一测试连续跑 100 次结果一致 (`for i in {1..100}; do poetry run pytest tests/unit/quantide/core/test_xxx.py; done`, 全部 pass)
### AC-2
- 任意测试可单独跑 (`poetry run pytest path/to/test.py::test_yyy`) 而不依赖其它测试状态
### AC-3
- 测试结束后, `tests/` 目录无新增 `.db` / `.sqlite` / `.parquet` / `.log` 等残留文件 (`find tests -newer .gitignore -type f` 无输出)
### AC-4
- 测试不持久修改 `quantide.*` 模块级全局变量; 如需 monkeypatch, 必须使用 pytest `monkeypatch` 或 context manager 自动还原
### AC-5
- 全局可变状态 (module-level `dict`/`list`/`set` 在测试间共享) 在 conftest.py 中无定义, 或 setup/teardown 中清空
### AC-6
- 时间依赖测试用 `@freeze_time` 或显式注入 `datetime`; 不存在裸 `datetime.now()` 在测试中

<a id="ac-nfr-0030"></a>
## NFR-0030 有意义覆盖与反作弊

### AC-1
- 对每个新增测试文件抽样检查: 至少一个测试名、模块 docstring 或注释引用 v0.2-001/v0.2-002 或本 spec 的 FR/AC
### AC-2
- 对每个从 <80% 提升到 ≥80% 的模块, 新增测试至少包含一个正常路径和一个错误/边界路径断言
### AC-3
- 测试代码中不存在只 import 目标模块且无行为断言的 coverage-only 测试; 静态检查: 新增测试文件中至少出现 `assert` / `pytest.raises` / response 状态断言 / mock 边界调用断言之一
### AC-4
- 新增测试不 mock 当前被测函数或类的主体逻辑; mock 仅允许外部 IO、时间、网络、数据库、下游 service 边界
### AC-5
- `pyproject.toml` `[tool.coverage.run] omit` 未新增生产模块排除, `[tool.coverage.report] exclude_lines` 未新增大范围排除
### AC-6
- 新增或修改的生产代码未批量添加 `# pragma: no cover`; 若单行添加, review artifact 或 PR description 必须解释原因并链接 follow-up
### AC-7
- `--cov-fail-under=95` 与单模块 `--cov-fail-under=80` 未被降低; CI workflow 不允许用 `continue-on-error: true` 包住主覆盖率门禁


---

## No Acceptance

以下 FR 在 `acceptance.md` 中**没有专属 AC 章节**, AC 来源在 spec.md 章节或 test-plan 中:

- 所有 US-* 用户故事 (无独立 AC 节, AC 在对应 FR-* 中)

> **整体验证命令**:
> ```bash
> # 1. 单元测试 + 覆盖率
> poetry run pytest tests/unit --cov=quantide --cov-fail-under=95 --cov-report=term-missing --cov-report=json:coverage.json
>
> # 2. 单模块验证
> poetry run pytest tests/unit/quantide/core --cov=quantide/core --cov-fail-under=80
>
> # 3. HTML 报告
> poetry run pytest tests/unit --cov=quantide --cov-report=html:htmlcov
>
> # 4. (可选) 增量覆盖率
> diff-cover coverage.xml --compare-branch=origin/main --fail-under=95
> ```
