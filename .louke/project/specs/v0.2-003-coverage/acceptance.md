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
> **目标**: 整体 ≥95%, 单模块 ≥80% (NFR-0010)。每条覆盖率类 AC 在 `pytest --cov=quantide --cov-report=term-missing` 下可直接断言。

---

## §1 测试基础设施

<a id="ac-fr-0101"></a>
## FR-0101 pytest 配置与覆盖率命令

### AC-1
- 项目根目录跑 `pytest --cov=quantide --cov-report=term-missing` → 终端输出每文件 stmts/miss/cover 表格, 不报错 (exit 0)
### AC-2
- 跑 `pytest --cov=quantide --cov-report=html:htmlcov` → 生成 `htmlcov/index.html` 文件, 内容包含可点击的源码链接
### AC-3
- 跑 `pytest --cov=quantide --cov-fail-under=95` → 当覆盖率 < 95% 时 exit 1 (当前 69% 应该 fail; lock 时 ≥95% 应该 pass)
### AC-4
- `pyproject.toml` 中 `[tool.pytest.ini_options]` 含 `asyncio_mode = "auto"` (与现有一致, 不破坏异步测试)
### AC-5
- 跑 `pytest tests/unit` 不跑 e2e 测试 (`tests/e2e/` 被排除或 e2e marker 自动 skip)
### AC-6
- 不存在 `pytest.ini` 或 `setup.cfg` (配置单一来源在 `pyproject.toml`)

<a id="ac-fr-0102"></a>
## FR-0102 覆盖率阈值与排除清单

### AC-1
- 跑 `pytest --cov=quantide --cov-fail-under=95` → exit 0 (整体 ≥95% 时)
### AC-2
- `quantide/core/__init__.py` / `quantide/data/services/__init__.py` 等空文件: 100% 覆盖 (0 stmts 或全部覆盖)
### AC-3
- 实施阶段若某模块 < 80% 但需要豁免: PR description 必须包含 (模块名 / 当前覆盖 / 原因 / 补救 issue 链接), 否则 CI 应 fail
### AC-4
- `pyproject.toml` 的 `[tool.coverage.report]` 不修改 `exclude_lines` 默认值, 仅允许新增注释说明豁免 (排除项不通过工具配置隐式豁免)

<a id="ac-fr-0103"></a>
## FR-0103 Mock 框架与 Fixture 共享

### AC-1
- `tests/unit/conftest.py` 与 `tests/unit/quantide/conftest.py` 存在并被 pytest 自动加载 (无需 `import conftest`)
### AC-2
- `env` fixture (session scope) 提供 `manifest / universe / calendar / daily_bars / adj_factor / st_info / limit_price` 7 个属性, 任何单测可直接 `def test_xxx(env)` 获取
### AC-3
- 数据层 mock 使用 `unittest.mock.MagicMock` 或 pytest-mock 的 `mocker.patch` (无新引入第三方 mock 库)
### AC-4
- 时间依赖测试用 `@freeze_time("2024-01-02")` (freezegun) 或显式注入 `datetime`, 不用 `datetime.now()`
### AC-5
- 数据库 mock 用 `:memory:` SQLite 或 `tmp_path` 下的 SQLite 文件, `tests/` 目录不残留 .db / .sqlite

<a id="ac-fr-0104"></a>
## FR-0104 测试隔离与确定性

### AC-1
- 同一测试连续跑 100 次结果一致 (`pytest tests/unit/quantide/core/test_xxx.py --count=100` 验证, 或 `for i in {1..100}; do pytest ...; done`)
### AC-2
- 任意测试可单独跑 (`pytest tests/unit/quantide/core/test_clock_bridge.py::test_backtest_clock_set_now_and_now`) 而不依赖其它测试状态
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
- `pytest tests/unit/quantide/core/domain/` 全 pass, 0 failure / 0 error
### AC-2
- `pytest --cov=quantide/core/domain --cov-report=term-missing` → `events.py` 覆盖率 = 100% (基线已 100%, 本 FR 维护)
### AC-3
- events 序列化 round-trip 测试: `event = Event.from_dict(d); e2 = Event.from_dict(event.to_dict()); assert e2 == event`
### AC-4
- 缺失必填字段的反序列化测试: `with pytest.raises(ValidationError)` (或文档约定的异常类型)
### AC-5
- `__init__.py` 100% 覆盖 (基线 100%)

<a id="ac-fr-0202"></a>
## FR-0202 core/runtime/clock_bridge 单测

### AC-1
- `pytest --cov=quantide/core/runtime/clock_bridge --cov-report=term-missing` → 覆盖率 ≥ 95% (基线 90%)
### AC-2
- `BacktestClockAdapter.set_now(t)` 后 `clock.now() == t` (精确相等, 不带时区)
### AC-3
- `BacktestClockAdapter.iter_frames(start, end, DAY)` 返回可迭代对象 (断言 `hasattr(frames, "__iter__")`)
### AC-4
- `SystemClockAdapter.set_now(t)` 抛 `RuntimeError` (live 模式不允许设置)
### AC-5
- 边界: `iter_frames` 的 start == end (单帧), start > end (空?) — 按现有实现断言

<a id="ac-fr-0203"></a>
## FR-0203 core/runtime/gateway_broker + gateway_client 单测

### AC-1
- `pytest --cov=quantide/core/runtime/gateway_broker --cov-report=term-missing` → 覆盖率 ≥ 90% (基线 80%)
### AC-2
- `pytest --cov=quantide/core/runtime/gateway_client --cov-report=term-missing` → 覆盖率 ≥ 90% (基线 75%)
### AC-3
- gateway_broker 连接生命周期测试: mock 网络层, 调用 `connect() / disconnect() / reconnect()` 后断言 mock 被调用次数与方法名
### AC-4
- 下单流程测试: `place_order(mock_order)` → mock 网关收到 `place_order` 调用, 参数匹配 (代码/数量/价格)
### AC-5
- 重连退避测试: 第一次失败后, 断言第二次调用间隔 ≥ 退避基数 (用 freezegun 控时间)
### AC-6
- gateway_client 消息收发 round-trip: 发送 mock 消息 → 接收回调被触发, payload 还原
### AC-7
- 心跳测试: ping → pong, 超时抛 `TimeoutError`
### AC-8
- 错误恢复: 网络断开模拟 (mock 抛 ConnectionError) → 重连逻辑被触发

<a id="ac-fr-0204"></a>
## FR-0204 core/runtime/modes + port_broker 单测

### AC-1
- `pytest --cov=quantide/core/runtime/modes --cov-report=term-missing` → 覆盖率 ≥ 95% (基线 89%)
### AC-2
- `pytest --cov=quantide/core/runtime/port_broker --cov-report=term-missing` → 覆盖率 ≥ 85% (基线 72%)
### AC-3
- modes 枚举值测试: `assert Mode.BACKTEST != Mode.PAPER`, `Mode.value == "backtest"`
### AC-4
- 模式切换合法路径: `backtest → paper → live` 各自合法
### AC-5
- 模式切换非法路径 (例: `idle → live` 跳过 paper): 抛 `InvalidTransitionError` (或文档约定异常)
### AC-6
- port_broker 注册测试: `register("foo", handler)` 后 `handler in registry`
### AC-7
- port_broker 路由测试: `dispatch(msg)` → 对应 port handler 被调用
### AC-8
- 重复注册 / 未注册 dispatch 抛错

<a id="ac-fr-0205"></a>
## FR-0205 core/strategy + strategy_discovery + scheduler 单测

### AC-1
- `pytest --cov=quantide/core/strategy --cov-report=term-missing` → 覆盖率 ≥ 90% (基线 79%)
### AC-2
- `pytest --cov=quantide/core/strategy_discovery --cov-report=term-missing` → 覆盖率 ≥ 90% (基线 82%)
### AC-3
- `pytest --cov=quantide/core/scheduler --cov-report=term-missing` → 覆盖率 ≥ 95% (基线 94%)
### AC-4
- strategy 生命周期: `create() → initialize() → run() → stop()` 状态机转换正确, 断言 `state == State.STOPPED`
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
- `pytest --cov=quantide/core/enums --cov-report=term-missing` → enums.py ≥ 90% (基线 75%)
### AC-2
- `pytest --cov=quantide/core/message --cov-report=term-missing` → message.py ≥ 95% (基线 88%)
### AC-3
- `pytest --cov=quantide/core/errors --cov-report=term-missing` → errors.py ≥ 99% (基线 99%, 保持)
### AC-4
- `pytest --cov=quantide/core/sdk_metadata --cov-report=term-missing` → sdk_metadata.py ≥ 95% (基线 87%)
### AC-5
- enums 转换: `enum.from_str("backtest") == Mode.BACKTEST`, 无效字符串抛 `ValueError`
### AC-6
- message 编解码 round-trip: `assert msg == decode(encode(msg))`
### AC-7
- errors 异常链: `raise ServiceError("x") from IOError("y")` → `e.__cause__ is not None`

<a id="ac-fr-0207"></a>
## FR-0207 core/ports/ 单测

### AC-1
- `pytest --cov=quantide/core/ports --cov-report=term-missing` → 整体 ≥ 90%
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
- `pytest --cov=quantide/data/fetchers --cov-report=term-missing` → 整体 ≥ 90%
### AC-2
- `tushare.py` ≥ 90% (基线 74%)
### AC-3
- `registry.py` ≥ 95% (基线 92%)
### AC-4
- tushare 请求构建: 给定参数 (ts_code, start_date, end_date), 断言生成的 URL / body 含正确参数 (用 `mocker.patch("requests.post")` 拦截)
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
- `pytest --cov=quantide/data/models --cov-report=term-missing` → 整体 ≥ 90%
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
- `pytest --cov=quantide/data/stores --cov-report=term-missing` → 整体 ≥ 90%
### AC-2
- `stores/base.py` ≥ 90% (基线 79%)
### AC-3
- `stores/index_bars.py` ≥ 80% (基线 38%)
### AC-4
- `pytest --cov=quantide/data/sqlite --cov-report=term-missing` → sqlite.py ≥ 95% (基线 90%)
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
- `pytest --cov=quantide/data/helper --cov-report=term-missing` → helper.py ≥ 80% (基线 49%, 大缺口)
### AC-2
- `pytest --cov=quantide/data/utils/resampler --cov-report=term-missing` → resampler.py ≥ 90% (基线 83%)
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
- `pytest --cov=quantide/service/strategy_runtime --cov-report=term-missing` → ≥ 90% (基线 65%, 大缺口)
### AC-2
- `pytest --cov=quantide/service/discovery --cov-report=term-missing` → ≥ 85% (基线 57%, 大缺口)
### AC-3
- `pytest --cov=quantide/service/registry --cov-report=term-missing` → ≥ 95% (基线 90%)
### AC-4
- `pytest --cov=quantide/service/runner --cov-report=term-missing` → ≥ 95% (基线 94%)
### AC-5
- strategy_runtime 状态机: `idle → running → paused → running → stopped`, 非法转换抛错
### AC-6
- strategy_runtime 心跳: mock 心跳回调, 推进时间 → 回调被周期性触发
### AC-7
- strategy_runtime 错误恢复: 模拟运行中异常 → 状态变为 `ERROR` (或文档约定状态)
### AC-8
- discovery: mock 服务注册中心 → 扫描返回可用服务列表, 健康检查通过/失败分流
### AC-9
- registry: register / deregister / list CRUD 测试
### AC-10
- runner: 给定策略函数 → 启动执行器, 断言策略被调用, 异常时清理资源

<a id="ac-fr-0402"></a>
## FR-0402 service/ 三类 broker 单测

### AC-1
- `pytest --cov=quantide/service/abstract_broker --cov-report=term-missing` → ≥ 85% (基线 54%, 大缺口)
### AC-2
- `pytest --cov=quantide/service/backtest_broker --cov-report=term-missing` → ≥ 95% (基线 93%)
### AC-3
- `pytest --cov=quantide/service/sim_broker --cov-report=term-missing` → ≥ 92% (基线 87%)
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
- `pytest --cov=quantide/service/datafeed --cov-report=term-missing` → ≥ 80% (基线 22%, 极大缺口)
### AC-2
- `pytest --cov=quantide/service/livequote --cov-report=term-missing` → ≥ 90% (基线 72%)
### AC-3
- datafeed: 从 mock store 读取 → 推送给 mock subscriber, 断言订阅者收到
### AC-4
- datafeed 重连: mock 网络断开 → 自动重连, 订阅者无感知
### AC-5
- livequote: subscribe / unsubscribe → 内部订阅列表更新
### AC-6
- livequote tick 推送: mock tick 输入 → 订阅者回调被触发, payload 正确
### AC-7
- livequote tick → bar 聚合: 给定 tick 序列 → 生成的 bar OHLC 与期望一致

<a id="ac-fr-0404"></a>
## FR-0404 service/ 其它服务单测

### AC-1
- `pytest --cov=quantide/service/backtest_logs --cov-report=term-missing` → ≥ 95% (基线 91%)
### AC-2
- `pytest --cov=quantide/service/grid_search --cov-report=term-missing` → ≥ 85% (基线 68%)
### AC-3
- `pytest --cov=quantide/service/init_wizard --cov-report=term-missing` → ≥ 90% (基线 80%)
### AC-4
- `pytest --cov=quantide/service/metrics --cov-report=term-missing` → ≥ 96% (基线 96%, 保持)
### AC-5
- `pytest --cov=quantide/service/trade_lightning --cov-report=term-missing` → ≥ 85% (基线 71%)
### AC-6
- `pytest --cov=quantide/service/triple_barrier --cov-report=term-missing` → ≥ 96% (基线 96%, 保持)
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
- `pytest --cov=quantide/web/components/analysis --cov-report=term-missing` → 整体 ≥ 85%
### AC-2
- `kline_chart.py` ≥ 85% (基线 26%, 大缺口)
### AC-3
- `stock_list.py` ≥ 85% (基线 33%, 大缺口)
### AC-4
- `backtest_charts.py` ≥ 100% (基线 100%, 保持)
### AC-5
- kline_chart 渲染: 给定 OHLCV 数据 → 输出 HTML/SVG 字符串含 K 线元素 (断言 `assert "svg" in output.lower()` 或 DOM 选择器)
### AC-6
- kline_chart 颜色规则: 涨绿 / 跌红 (断言 class 或颜色属性)
### AC-7
- stock_list 渲染: 给定股票列表 → 输出 HTML, 行数 = len(data) + 1 (header)
### AC-8
- stock_list 过滤: 输入 "ma" → 输出仅含匹配股票的行
### AC-9
- stock_list 排序: 按代码升序 → 输出顺序正确
### AC-10
- backtest_charts (净值/回撤/热力图) 渲染测试: 给定数据 → 输出含 svg / canvas

<a id="ac-fr-0502"></a>
## FR-0502 web/components/ 通用组件单测 (验证类)

### AC-1
- `pytest --cov=quantide/web/components/header --cov-report=term-missing` → 100%
### AC-2
- `pytest --cov=quantide/web/components/sidebar --cov-report=term-missing` → 100%
### AC-3
- `pytest --cov=quantide/web/components/toast --cov-report=term-missing` → 100%
### AC-4
- `pytest --cov=quantide/web/components/runtime_params --cov-report=term-missing` → 100%
### AC-5
- `pytest --cov=quantide/web/components/asset_label --cov-report=term-missing` → 100%
### AC-6
- 五个组件的现有测试保留, 不删除 (`git log --diff-filter=D --name-only` 验证)
### AC-7
- 重构任一组件时, 同步更新其测试; 重构后掉覆盖, 必须补回 100%


---

## §2.6 CI/CD 与质量门禁

<a id="ac-fr-0601"></a>
## FR-0601 CI 强制覆盖率门槛

### AC-1
- `.github/workflows/unit-coverage.yml` 存在, 触发条件: `push` 到 `releases/**` 与 `pull_request` 到 `main` / `releases/**`
### AC-2
- workflow 步骤: `pip install -e ".[test]"` → `pytest tests/unit --cov=quantide --cov-fail-under=95 --cov-report=term-missing`
### AC-3
- 整体覆盖率 < 95% 时 workflow fail (exit 1), 阻断合并
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

## §7 非功能需求

<a id="ac-nfr-0010"></a>
## NFR-0010 覆盖率阈值与豁免机制

### AC-1
- 跑 `pytest --cov=quantide --cov-fail-under=95` → 当覆盖率 < 95% 时 exit 1; ≥ 95% 时 exit 0
### AC-2
- 跑 `pytest --cov=quantide/core --cov-fail-under=80` → 单模块 ≥ 80% 时 exit 0; < 80% 时 exit 1
### AC-3
- `quantide/core/__init__.py` / `quantide/data/services/__init__.py` 等空 `__init__.py` 100% 覆盖 (0 stmts 时为 100% 自动)
### AC-4
- 临时豁免模块: PR description 必须包含 (模块名 / 当前覆盖 / 原因 / 补救 issue 链接), 否则 CI 应 fail (人工 review 检查)
### AC-5
- `pyproject.toml` 的 `[tool.coverage.report]` `exclude_lines` 不修改默认值 (与现有配置一致)
### AC-6
- 豁免清单 (本 spec 范围内): 仅 `__init__.py` 空文件; 其它模块不豁免, 必须达 ≥ 80% 或走临时豁免申请

<a id="ac-nfr-0020"></a>
## NFR-0020 测试隔离与确定性

### AC-1
- 同一测试连续跑 100 次结果一致 (`for i in {1..100}; do pytest tests/unit/quantide/core/test_xxx.py; done`, 全部 pass)
### AC-2
- 任意测试可单独跑 (`pytest path/to/test.py::test_yyy`) 而不依赖其它测试状态
### AC-3
- 测试结束后, `tests/` 目录无新增 `.db` / `.sqlite` / `.parquet` / `.log` 等残留文件 (`find tests -newer .gitignore -type f` 无输出)
### AC-4
- 测试不修改 `quantide.*` 任何模块级全局变量 (可通过 grep 验证: 测试代码中无 `quantide.X = Y` 直接赋值)
### AC-5
- 全局可变状态 (module-level `dict`/`list`/`set` 在测试间共享) 在 conftest.py 中无定义, 或 setup/teardown 中清空
### AC-6
- 时间依赖测试用 `@freeze_time` 或显式注入 `datetime`; 不存在裸 `datetime.now()` 在测试中


---

## No Acceptance

以下 FR 在 `acceptance.md` 中**没有专属 AC 章节**, AC 来源在 spec.md 章节或 test-plan 中:

- 所有 US-* 用户故事 (无独立 AC 节, AC 在对应 FR-* 中)

> **整体验证命令**:
> ```bash
> # 1. 单元测试 + 覆盖率
> pytest tests/unit --cov=quantide --cov-fail-under=95 --cov-report=term-missing
>
> # 2. 单模块验证
> pytest tests/unit/quantide/core --cov=quantide/core --cov-fail-under=80
>
> # 3. HTML 报告
> pytest tests/unit --cov=quantide --cov-report=html:htmlcov
>
> # 4. (可选) 增量覆盖率
> diff-cover coverage.xml --compare-branch=origin/main --fail-under=95
> ```
