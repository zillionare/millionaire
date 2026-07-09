# Millionaire Coverage Spec — 单元测试覆盖率提升

- **Spec ID**: v0.2-003-coverage
- **创建日期**: 2026-07-09
- **状态**: 草稿 (M-SPEC Phase 1, 等 Aaron IDE review)
- **Story 同步基线**: `.louke/project/specs/v0.2-003-coverage/story.md` (113 行, 6 章)
- **上游 spec**:
  - [v0.2-001-strategy-framework](../v0.2-001-strategy-framework/spec.md) — 策略框架/调度/数据/SDK
  - [v0.2-002-ui](../v0.2-002-ui/spec.md) — UI 覆盖 (已 lock, web/services 99%, 但核心/数据/服务/UI 组件层未覆盖)

> **Sage 注释 (草稿状态)**: 本 spec 中所有 inline-discussion quote 当前均为 **open 状态** (无 marker)。Sage 不能在 Aaron 回复前擅自标记 `[RESOLVED]` (per agent.md §3.2 "Silence is NOT consent")。待 Aaron IDE review 答复后, 由 Sage 在下一轮回复中将对应 root comment 加 `[RESOLVED]`。

> **Sage**: Q-Spec-Format FR 编号偏差 (关键开放问题): 任务原文 "FR 编号: `UI-TEST-XXXX` (4 位, 0.8 期望)" 与 louke 0.8.0 的 `verify_acceptance.py` 正则不兼容 (工具硬编码接受 `FR-XXXX` 或 `NFR-XXXX`, 不接受 `UI-TEST-XXXX`)。Sage 选择遵循工具约定, 使用 `FR-XXXX` (与 v0.2-002-ui 一致)。**请 Aaron 确认**: 是预期 fallback (`FR-XXXX`), 还是需要升级 louke 工具以支持 `UI-TEST-XXXX` 前缀? 如果是后者, 本 spec 在 lock 前需要阻塞。
>> **Sage Round 2 备选方案**: 如果 Aaron 坚持 `UI-TEST-XXXX`, 备选方案是用 `FR-XXXX` + 在 FR 标题加 `[UI-TEST]` 前缀 (例: `### FR-0101 [UI-TEST] pytest 配置与覆盖率命令`), 这样 verify-acceptance 通过, 但语义上仍能区分测试类 FR。但 Sage 推荐方案 1 (纯 `FR-XXXX`)。

> **本 spec 仅定义测试覆盖率提升任务的需求与验收**, 不重复定义业务规则。
> 业务计算/调度/数据/撮合规则 → v0.2-001-strategy-framework。
> UI 展示/交互契约 → v0.2-002-ui。
> 本 spec 通过引用数据层/服务层模块清单与覆盖率目标, 推动实施阶段补齐单测。


## 当前覆盖率基线 (2026-07-09)

| 模块域       | Stmts    | Miss    | Cover | 目标 ≥80%? |
| ------------ | -------- | ------- | ----- | ---------- |
| **TOTAL**    | **15657** | **4856** | **69%** | ❌ (目标 ≥95%, 差 26pp) |
| quantide/core/ | 1726  | 273   | 84%  | ✅ (个别模块低于) |
| quantide/data/ | 1763  | 339   | 81%  | ✅ (个别模块低于) |
| quantide/service/ | 2876  | 873 | 70%  | ❌ |
| quantide/web/components/ | 271 | 41 | 85% | ✅ (个别模块低于) |
| quantide/web/(其它) | 4711 | 2972 | 37% | ❌ (**不在本 spec 范围**) |

> **范围声明**: 本 spec **仅覆盖** `quantide/core/`、`quantide/data/`、`quantide/service/`、`quantide/web/components/` 四个域 (story §2-§5)。`quantide/web/pages/`、`quantide/web/auth/`、`quantide/web/apis/`、`quantide/web/middleware*`、`quantide/notify/` 等不在范围内, 由 v0.2-002-ui (99% web/services) 与后续 spec 覆盖。

### 单模块低于 80% 名单 (story 提及)

| 模块                              | 当前  | 差距  | 涉及 FR           |
| --------------------------------- | ----- | ----- | ----------------- |
| `quantide/core/enums.py`          | 75%   | 5pp   | FR-0206           |
| `quantide/core/runtime/gateway_client.py` | 75% | 5pp | FR-0203       |
| `quantide/core/runtime/port_broker.py` | 72% | 8pp | FR-0204         |
| `quantide/core/strategy.py`       | 79%   | 1pp   | FR-0205           |
| `quantide/core/ports/clock.py`    | 73%   | 7pp   | FR-0207           |
| `quantide/core/ports/data_fetcher.py` | 65% | 15pp | FR-0207        |
| `quantide/core/ports/market_data.py` | 62% | 18pp | FR-0207        |
| `quantide/data/fetchers/tushare.py` | 74% | 6pp  | FR-0301          |
| `quantide/data/helper.py`         | 49%   | 31pp  | FR-0304           |
| `quantide/data/models/index_bars.py` | 0% | 80pp | FR-0302          |
| `quantide/data/stores/index_bars.py` | 38% | 42pp | FR-0303         |
| `quantide/data/stores/base.py`    | 79%   | 1pp   | FR-0303           |
| `quantide/service/abstract_broker.py` | 54% | 26pp | FR-0402        |
| `quantide/service/datafeed.py`    | 22%   | 58pp  | FR-0403           |
| `quantide/service/discovery.py`   | 57%   | 23pp  | FR-0401           |
| `quantide/service/grid_search.py` | 68%   | 12pp  | FR-0404           |
| `quantide/service/livequote.py`   | 72%   | 8pp   | FR-0403           |
| `quantide/service/init_wizard.py` | 80%   | 0pp   | FR-0404 (刚好达标) |
| `quantide/service/trade_lightning.py` | 71% | 9pp | FR-0404         |
| `quantide/service/strategy_runtime.py` | 65% | 15pp | FR-0401        |
| `quantide/web/components/analysis/kline_chart.py` | 26% | 54pp | FR-0501 |
| `quantide/web/components/analysis/stock_list.py` | 33% | 47pp | FR-0501 |


## 章节映射表

| spec.md 章节          | story.md 章节      | 内容主题                                            | 主要 FR                    |
| --------------------- | ------------------ | --------------------------------------------------- | -------------------------- |
| §1 测试基础设施       | story §1           | pytest 配置 / 覆盖率阈值 / Mock / Fixture / 隔离    | FR-0101~0104             |
| §2 core/ 单测         | story §2           | domain / runtime / strategy / ports 单元测试       | FR-0201~0207             |
| §3 data/ 单测         | story §3           | fetchers / models / stores / sqlite / utils 单测    | FR-0301~0304             |
| §4 service/ 单测      | story §4           | strategy_runtime / brokers / datafeed / 其它服务   | FR-0401~0404             |
| §5 web/components/ 单测 | story §5         | analysis 组件 / 通用组件 (header/sidebar/toast...)  | FR-0501~0502             |
| §6 CI/CD              | story §6           | GitHub Actions / --cov-fail-under / diff-cover     | FR-0601~0602             |
| §7 NFR                | —                  | 覆盖率阈值 / 排除清单 / 测试确定性                  | NFR-0010 / NFR-0020      |


---

## 0. 范围与边界

### 0.1 在本 spec 范围内

- `quantide/core/` 全模块单元测试 (`domain/`、`runtime/`、`strategy.py`、`strategy_discovery.py`、`scheduler.py`、`enums.py`、`message.py`、`errors.py`、`sdk_metadata.py`、`ports/`)
- `quantide/data/` 全模块单元测试 (`fetchers/`、`models/`、`stores/`、`sqlite.py`、`helper.py`、`utils/`)
- `quantide/service/` 全模块单元测试 (`strategy_runtime.py`、`discovery.py`、`registry.py`、`runner.py`、`abstract_broker.py`、`backtest_broker.py`、`sim_broker.py`、`datafeed.py`、`livequote.py`、`backtest_logs.py`、`grid_search.py`、`init_wizard.py`、`metrics.py`、`trade_lightning.py`、`triple_barrier.py`)
- `quantide/web/components/` 全模块单元测试 (`analysis/`、`header.py`、`sidebar.py`、`toast.py`、`runtime_params.py`、`asset_label.py`)
- 测试基础设施 (pytest 配置、Mock 框架、Fixture 共享、覆盖率报告)
- CI/CD 集成 (GitHub Actions `--cov-fail-under`)

### 0.2 不在本 spec 范围内

- `quantide/web/pages/`、`quantide/web/auth/`、`quantide/web/apis/`、`quantide/web/middleware*`、`quantide/web/services/`、`quantide/web/layouts/`、`quantide/web/nfr_*.py` 等 → v0.2-002-ui (99% 覆盖) 与后续 spec
- `quantide/notify/` → 后续 spec (本期覆盖率 15%, 不在本 spec 范围)
- `quantide/strategies/` → 已有 e2e + 单元测试 (本 spec 不重复定义)
- `quantide/config/` → 配置模块 (dev_stubs 61%, paths 96%, settings 91%, 由实施阶段单独决策)
- 业务规则 (策略评估、撮合、T+1 等) → v0.2-001-strategy-framework
- 集成测试 / 端到端测试 → v0.2-001-strategy-framework test-plan §5/§6
- 性能测试 (Lighthouse、表格 FPS) → NFR-0010 (v0.2-002-ui 已定义)


---

## 1. 用户故事

### 1.1 测试基础设施

> 对应 story §1 "作为开发者, 我需要建立统一的测试基础设施, 以便高效地为所有模块编写和运行单元测试"

#### US-0101
story: 作为开发者, 我希望用统一命令 (`pytest --cov=quantide`) 跑覆盖率, CI 中能强制 ≥95% 整体阈值, 以便任何 PR 合并前都能看到覆盖率变化。
priority: P0

> **Sage**: Q-US-0101 阈值来源: story §6 已明确 "整体 ≥95%, 单模块 ≥80%", 而 `meta.dod` 同样写 "单元测试覆盖率 ≥95%"。这是双重确认, 不需要二次确认 — 但请 Aaron 在 IDE 中 **确认** 这个解读与你预期一致 (即 v0.2 必须达到 ≥95% 整体覆盖率才能 lock)。

#### US-0102
story: 作为开发者, 我希望共享 `conftest.py` 中的 fixture (mock 行情、mock 网关、mock 日历), 避免每个测试文件重复声明, 以便加速编写和保证一致性。
priority: P0

#### US-0103
story: 作为开发者, 我希望测试之间状态隔离 (无顺序依赖, 不污染全局), 以便任意顺序、并行执行测试都能得到稳定结果。
priority: P0

### 1.2 core/ 单测

> 对应 story §2 (2.1 领域层 / 2.2 运行时 / 2.3 策略与调度 / 2.4 其他核心模块)

#### US-0201
story: 作为开发者, 我希望 `core/domain/events.py` 等领域对象有完整单测 (创建/序列化/反序列化/校验), 以便策略运行时实例能正确处理事件。
priority: P0

#### US-0202
story: 作为开发者, 我希望 `core/runtime/` 模块 (clock_bridge / gateway_broker / gateway_client / modes / port_broker) 都有单测覆盖启动、停止、连接、重连等核心路径, 以便运行时层行为可靠。
priority: P0

#### US-0203
story: 作为开发者, 我希望 `core/strategy.py` / `core/strategy_discovery.py` / `core/scheduler.py` 都有单测覆盖生命周期/发现/调度, 以便策略运行时正确调度。
priority: P0

#### US-0204
story: 作为开发者, 我希望 `core/enums.py` / `core/message.py` / `core/errors.py` / `core/sdk_metadata.py` / `core/ports/` 等基础模块有单测, 以便底层契约稳定。
priority: P0

### 1.3 data/ 单测

> 对应 story §3 (3.1 fetchers / 3.2 models / 3.3 stores / 3.4 utils)

#### US-0301
story: 作为开发者, 我希望 `data/fetchers/` (tushare + registry) 都有单测覆盖请求构建/响应解析/错误处理/注册发现, 以便数据获取稳定。
priority: P0

#### US-0302
story: 作为开发者, 我希望 `data/models/` (calendar / daily_bars / stocks / app_state / **index_bars**) 都有单测, 以便数据模型构造/校验/转换正确。
priority: P0

#### US-0303
story: 作为开发者, 我希望 `data/stores/` (base / index_bars) 与 `data/sqlite.py` 都有单测, 以便存储层 CRUD 与查询稳定。
priority: P0

#### US-0304
story: 作为开发者, 我希望 `data/helper.py` 与 `data/utils/resampler.py` 都有单测, 以便数据辅助函数与重采样逻辑正确。
priority: P1

### 1.4 service/ 单测

> 对应 story §4 (4.1 策略运行时 / 4.2 经纪人 / 4.3 数据与行情 / 4.4 其它)

#### US-0401
story: 作为开发者, 我希望 `service/strategy_runtime.py` / `service/discovery.py` / `service/registry.py` / `service/runner.py` 都有单测, 以便服务注册/发现/运行时/执行器可靠。
priority: P0

#### US-0402
story: 作为开发者, 我希望 `service/abstract_broker.py` / `service/backtest_broker.py` / `service/sim_broker.py` 都有单测, 以便抽象/回测/仿真三个 broker 行为一致。
priority: P0

#### US-0403
story: 作为开发者, 我希望 `service/datafeed.py` / `service/livequote.py` 都有单测覆盖数据馈送/实时行情核心路径, 以便数据流稳定。
priority: P0

#### US-0404
story: 作为开发者, 我希望 `service/` 其它模块 (backtest_logs / grid_search / init_wizard / metrics / trade_lightning / triple_barrier) 都有单测, 以便辅助服务稳定。
priority: P1

### 1.5 web/components/ 单测

> 对应 story §5 (analysis 组件 + 通用组件)

#### US-0501
story: 作为开发者, 我希望 `web/components/analysis/` (kline_chart / stock_list / backtest_charts) 都有单测, 以便分析组件渲染逻辑正确。
priority: P0

#### US-0502
story: 作为开发者, 我希望验证 `web/components/header.py` / `sidebar.py` / `toast.py` / `runtime_params.py` / `asset_label.py` 100% 覆盖 (story §5 标注), 以便通用组件稳定。
priority: P1 (验证类需求)

### 1.6 CI/CD

> 对应 story §6 "GitHub Actions 自动执行测试并强制执行覆盖率阈值"

#### US-0601
story: 作为开发者, 我希望 CI 在 push/PR 时自动跑 `pytest --cov=quantide --cov-fail-under=95`, 以便任何代码合并都通过覆盖率门槛。
priority: P0

#### US-0602
story: 作为开发者, 我希望 CI 生成 HTML 覆盖率报告并作为 artifact 上传, 以便审查者下载查看详细覆盖。
priority: P1

#### US-0603
story: 作为开发者, 我希望 (可选) CI 中跑 diff-cover, PR 新增代码覆盖率 ≥95%, 以便增量代码不降低覆盖率。
priority: P2 (可选, story §6 标注 "可选")


---

## 2. 功能需求

### 2.1 测试基础设施

> 对应 story §1。

<a id="fr-0101"></a>
### FR-0101 pytest 配置与覆盖率命令

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

项目统一通过 `pyproject.toml` 中 `[tool.pytest.ini_options]` 与 `[tool.coverage.*]` 配置, 提供以下命令:

- `pytest tests/unit`: 仅跑单元测试 (排除 `e2e` marker)
- `pytest --cov=quantide --cov-report=term-missing`: 终端显示缺哪些行
- `pytest --cov=quantide --cov-report=html`: 生成 `htmlcov/` HTML 报告
- `pytest --cov=quantide --cov-fail-under=95`: 整体覆盖率低于 95% 时 exit 1
- 单模块: 使用 `pytest --cov=quantide/core --cov-fail-under=80` 单独验证

**约束**:
- 配置在 `pyproject.toml` 中, 单一来源
- 不创建 `pytest.ini` / `setup.cfg` (避免多源)
- `asyncio_mode = "auto"` 保留 (异步测试无需 `@pytest.mark.asyncio`)

> **Sage**: Q-FR-0101 配置位置: story §1 提到 "pytest.ini 或 pyproject.toml"。本项目 pyproject.toml 已有 `[tool.pytest.ini_options]` 与 `[tool.coverage.*]`, 沿用现有结构, 不引入 pytest.ini。**请 Aaron 确认** 这一选择 (沿用 pyproject.toml) 与预期一致。

<a id="fr-0102"></a>
### FR-0102 覆盖率阈值与排除清单

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

覆盖率分级阈值:

- **整体**: ≥ 95% (CI `--cov-fail-under=95`)
- **单模块**: ≥ 80% (低 80% 模块需在 `pyproject.toml` `[tool.coverage.report] exclude_lines` 注释或文档中说明)

**允许豁免的模块** (按 v0.2-002-ui 类似豁免机制, 详见 NFR-0010):
- `quantide/core/__init__.py`: 0% 或可豁免 (只是 import 暴露)
- `quantide/data/services/__init__.py`: 0% (空文件)
- 各 `__init__.py` 空文件: 100% 自动达标

**单模块豁免申请**: 实施阶段若发现某模块无法达 80%, 需在 PR description 中说明:
- 模块名 + 当前覆盖率 + 原因 (第三方依赖/不可达分支/纯数据类等)
- 替代方案 (mock 改进/重构/接受低覆盖)

<a id="fr-0103"></a>
### FR-0103 Mock 框架与 Fixture 共享

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

测试使用统一的 Mock 框架与 Fixture:

- **Mock 框架**: `unittest.mock` (`MagicMock` / `AsyncMock` / `patch`) + `pytest-mock` (`mocker` fixture)
- **Fixture 共享**: 集中在 `tests/unit/conftest.py` 与 `tests/unit/quantide/conftest.py` (已存在, 见 `env` fixture)
- **数据层 mock**:
  - mock 行情数据: polars DataFrame fixture (`daily_bars.parquet` 等已存在)
  - mock 日历: `env.calendar` fixture (已存在)
  - mock 网关: `MagicMock(spec=GatewayProtocol)` 或 `FakeGateway` 测试替身
  - mock 数据库: 临时 SQLite `:memory:` 或 `tmp_path` fixture
- **时间 mock**: `freezegun` (`@freeze_time("2024-01-02")`) 用于固定时间测试

**约束**:
- 不引入新的 mock 库 (`mock` / `responses` / `httpx-mock` 等不在依赖中, 避免膨胀)
- 数据 fixture 优先复用 `tests/assets/unit/fixtures/data/` (现有资产)

<a id="fr-0104"></a>
### FR-0104 测试隔离与确定性

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

每个测试用例独立, 不依赖执行顺序:

- **测试无副作用**: 不修改全局状态 / 模块级变量 / 临时文件不残留
- **fixture 生命周期**: 函数级默认 (`scope="function"`); 只有 env 数据 (parquet) 可 session 级
- **临时资源**: 用 `tmp_path` fixture 创建, 测试结束自动清理
- **数据库**: 用 `:memory:` 或 `tmp_path` 下的 SQLite 文件, 不污染 `tests/` 目录
- **mock 还原**: `monkeypatch` 自动还原; `mocker.patch` 自动还原
- **确定性时间**: 使用 `freezegun` 或显式注入 `datetime`, 不依赖 `datetime.now()`
- **并行执行** (可选): `pytest-xdist` 不强制要求, 但测试不能因并行导致失败


### 2.2 quantide/core/ 单测

> 对应 story §2。

<a id="fr-0201"></a>
### FR-0201 core/domain/ 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`quantide/core/domain/` 全模块单元测试:

- `events.py`: 事件对象的**创建** (默认参数/边界值) + **序列化** (to_dict/to_json) + **反序列化** (from_dict/from_json) + **校验** (字段必填/类型) + **相等性** (__eq__ / __hash__)
- `__init__.py`: 模块导出检查
- 未来新增的领域对象: 同模式

**约束**:
- 当前 `events.py` 100% 覆盖 (基线), 本 FR 维护并保持 100%
- 反序列化时缺失字段: 抛 `ValidationError` 或默认值 (以现有实现为准, 单测断言)

<a id="fr-0202"></a>
### FR-0202 core/runtime/clock_bridge 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`quantide/core/runtime/clock_bridge.py` 单元测试, 当前 90% 覆盖:

- `BacktestClockAdapter.set_now()`: 设置时间, `now()` 返回相同值
- `BacktestClockAdapter.now()`: 默认值 / 设置后值
- `BacktestClockAdapter.iter_frames()`: 返回可迭代对象 (mock `calendar.get_frames`)
- `SystemClockAdapter.now()`: 返回当前时间 (mock `datetime`)
- `SystemClockAdapter.set_now()`: 抛 `RuntimeError` (live 模式不允许设置)
- 边界: 空区间 / 单帧区间 / 跨日区间

**目标**: ≥ 95% (基线 90%, 补齐 line 16, 29)

<a id="fr-0203"></a>
### FR-0203 core/runtime/gateway_broker + gateway_client 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`quantide/core/runtime/gateway_broker.py` (基线 80%) + `gateway_client.py` (基线 75%) 单元测试:

- **gateway_broker**:
  - 连接生命周期: `connect()` / `disconnect()` / `reconnect()` (mock 网络层)
  - 下单流程: `place_order()` / `cancel_order()` / 订单回报回调
  - 错误处理: 网络断开 / 网关鉴权失败 / 订单拒绝
  - 重连退避: 重试次数 / 重试间隔
- **gateway_client**:
  - 客户端连接: `connect()` / `disconnect()` (mock socket/websocket)
  - 消息收发: 发送消息 → 接收回调 (mock 异步消息队列)
  - 心跳: ping/pong
  - 重连: 断线重连机制
  - 错误: 解析错误 / 协议错误 / 超时

**目标**: gateway_broker ≥ 90%, gateway_client ≥ 90%

<a id="fr-0204"></a>
### FR-0204 core/runtime/modes + port_broker 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`modes.py` (基线 89%) + `port_broker.py` (基线 72%) 单元测试:

- **modes**:
  - 运行模式枚举: `backtest` / `paper` / `live` / `dry_run`
  - 模式切换: 合法切换 / 非法切换抛错
  - 模式查询: 当前模式 / 模式描述
- **port_broker**:
  - 端口注册: 注册 port → 出现在注册表
  - 端口路由: 消息 → port 路由 (mock 端口实现)
  - 取消注册: 端口注销
  - 多端口: 一对多路由
  - 错误: 未知端口 / 已注册端口重复注册

**目标**: modes ≥ 95%, port_broker ≥ 85%

<a id="fr-0205"></a>
### FR-0205 core/strategy + strategy_discovery + scheduler 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`strategy.py` (基线 79%) + `strategy_discovery.py` (基线 82%) + `scheduler.py` (基线 94%) 单元测试:

- **strategy**:
  - 生命周期: `create()` / `initialize()` / `run()` / `stop()` (mock 钩子)
  - 参数注入: 默认参数 / 用户参数 / 类型校验
  - 错误: 重复初始化 / 状态非法转换
- **strategy_discovery**:
  - 发现: 扫描目录 → 加载策略 (mock 文件系统)
  - 加载: 动态 import / 元数据提取
  - 错误: 导入失败 / 无效策略 / 重复 ID
- **scheduler**:
  - 任务添加: `add_job()` / `remove_job()` / `list_jobs()`
  - 任务触发: cron / interval / date
  - 任务执行: mock 任务函数 → 断言被调用
  - 错误: 重复任务 / 无效 cron

**目标**: strategy ≥ 90%, strategy_discovery ≥ 90%, scheduler ≥ 95%

<a id="fr-0206"></a>
### FR-0206 core/ 基础模块单测 (enums / message / errors / sdk_metadata)

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

基础模块单测:

- **enums.py** (基线 75%):
  - 枚举定义: 成员值 / 唯一性
  - 转换: enum → str / str → enum (含 invalid 抛错)
  - 比较: 枚举相等性 / 排序
- **message.py** (基线 88%):
  - 消息协议: 编码 / 解码 (round-trip)
  - 边界: 空消息 / 大消息 / 二进制安全
  - 错误: 截断消息 / 校验失败
- **errors.py** (基线 99%):
  - 错误类型: 异常构造 / 异常链 / 异常消息
- **sdk_metadata.py** (基线 87%):
  - SDK 元数据: 版本 / 名称 / 描述
  - 序列化

**目标**: enums ≥ 90%, message ≥ 95%, errors ≥ 99% (保持), sdk_metadata ≥ 95%

<a id="fr-0207"></a>
### FR-0207 core/ports/ 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`quantide/core/ports/` 单测:

- **broker.py** (基线 84%): 经纪人端口抽象 — 接口契约 (mock 实现) / 抽象方法抛错
- **clock.py** (基线 73%): 时钟端口 — `now()` / `set_now()` 接口契约
- **data_fetcher.py** (基线 65%): 数据获取端口 — `fetch()` / `validate()` 接口契约
- **market_data.py** (基线 62%): 行情数据端口 — `subscribe()` / `unsubscribe()` / `on_tick()` 接口契约

**目标**: ports/broker ≥ 90%, ports/clock ≥ 90%, ports/data_fetcher ≥ 85%, ports/market_data ≥ 85%


### 2.3 quantide/data/ 单测

> 对应 story §3。

<a id="fr-0301"></a>
### FR-0301 data/fetchers/ 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`data/fetchers/` 单测:

- **tushare.py** (基线 74%):
  - 请求构建: 参数 → URL / body
  - 响应解析: 原始响应 → DataFrame / 领域对象
  - 错误处理: 网络错误 / 限流 / 数据缺失 / 鉴权失败
  - 重试: tenacity 重试机制
- **registry.py** (基线 92%):
  - 注册: fetcher 类 → 注册表
  - 发现: 通过 name 查找 fetcher
  - 错误: 未注册 / 重复注册

**目标**: tushare ≥ 90%, registry ≥ 95%

<a id="fr-0302"></a>
### FR-0302 data/models/ 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`data/models/` 全模块单测:

- **calendar.py** (基线 90%): 交易日历 — 字段/构造/查询 (`is_trade_day` / `next_trade_date` 等)
- **daily_bars.py** (基线 85%): 日线数据 — 字段/构造/重采样/复权
- **stocks.py** (基线 91%): 股票信息 — 字段/构造/查询 (按代码/名称/拼音)
- **app_state.py** (基线 88%): 应用状态 — 状态机/序列化/反序列化
- **index_bars.py** (基线 **0%** — 完全无覆盖): 指数数据 — 字段/构造/查询 (从 0% 起步补齐)

**目标**: calendar ≥ 95%, daily_bars ≥ 95%, stocks ≥ 95%, app_state ≥ 95%, index_bars ≥ 80% (从 0 起步)

<a id="fr-0303"></a>
### FR-0303 data/stores/ + sqlite 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`data/stores/` + `data/sqlite.py` 单测:

- **stores/base.py** (基线 79%): 基础存储 — CRUD / 事务 / 查询 / 索引
- **stores/index_bars.py** (基线 38%): 指数存储 — CRUD / 批量写入 / 查询
- **sqlite.py** (基线 90%): SQLite 操作 — 连接 / 表创建 / 索引 / 备份 / 迁移

**目标**: stores/base ≥ 90%, stores/index_bars ≥ 80% (从 38% 起步), sqlite ≥ 95%

<a id="fr-0304"></a>
### FR-0304 data/helper + utils/resampler 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`data/helper.py` (基线 49%) + `data/utils/resampler.py` (基线 83%) 单测:

- **helper.py**:
  - 数据加载/保存辅助函数
  - 数据格式转换
  - 校验函数
- **resampler.py**:
  - 数据重采样: 日线 → 周线 / 月线
  - OHLC 重计算
  - 缺失日期填充

**目标**: helper ≥ 80% (从 49% 起步), resampler ≥ 90%


### 2.4 quantide/service/ 单测

> 对应 story §4。

<a id="fr-0401"></a>
### FR-0401 service/ 策略运行时与执行器单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`service/` 策略运行时四件套单测:

- **strategy_runtime.py** (基线 65%):
  - 运行时实例: 创建 / 启动 / 暂停 / 停止 / 销毁
  - 状态机转换: `idle` → `running` → `paused` → `stopped`
  - 心跳 / 健康检查
  - 错误恢复: 异常时状态 / 重启策略
- **discovery.py** (基线 57%):
  - 服务发现: 扫描可用服务 / 注册中心
  - 健康检查 / 心跳
  - 缓存 / 失效
- **registry.py** (基线 90%):
  - 服务注册 / 注销
  - 查询 / 列表
- **runner.py** (基线 94%):
  - 策略执行器: 运行 / 异常处理 / 清理

**目标**: strategy_runtime ≥ 90% (从 65% 起步), discovery ≥ 85% (从 57% 起步), registry ≥ 95%, runner ≥ 95%

<a id="fr-0402"></a>
### FR-0402 service/ 三类 broker 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`service/` 三类 broker 单测:

- **abstract_broker.py** (基线 54%):
  - 抽象接口: 子类实现契约 / 未实现方法抛错
  - 通用方法: 订单回调 / 持仓更新
- **backtest_broker.py** (基线 93%):
  - 回测撮合: 按历史数据撮合 / 滑点 / 手续费
  - 订单状态: pending → filled / rejected
- **sim_broker.py** (基线 87%):
  - 仿真撮合: 模拟实时撮合 / 部分成交
  - 订单生命周期

**目标**: abstract_broker ≥ 85% (从 54% 起步), backtest_broker ≥ 95%, sim_broker ≥ 92%

<a id="fr-0403"></a>
### FR-0403 service/ 数据馈送与实时行情单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`service/datafeed.py` (基线 22%) + `service/livequote.py` (基线 72%) 单测:

- **datafeed.py**:
  - 数据馈送: 从 store 读取 / 推送至订阅者
  - 重连 / 重试
  - 数据格式转换
- **livequote.py**:
  - 实时行情订阅: subscribe / unsubscribe
  - tick 推送: 回调 / 队列
  - 断线重连
  - 数据聚合: tick → bar

**目标**: datafeed ≥ 80% (从 22% 起步, 大缺口), livequote ≥ 90%

<a id="fr-0404"></a>
### FR-0404 service/ 其它服务单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`service/` 其它模块单测:

- **backtest_logs.py** (基线 91%): 回测日志 — 写入 / 读取 / 清理
- **grid_search.py** (基线 68%): 网格搜索 — 参数组合 / 并行执行 / 结果聚合
- **init_wizard.py** (基线 80%): 初始化向导 — 步骤序列 / 校验 / 跳过
- **metrics.py** (基线 96%): 指标计算 — Sharpe / Sortino / 最大回撤
- **trade_lightning.py** (基线 71%): 闪电交易 — 快速下单 / 取消
- **triple_barrier.py** (基线 96%): 三柱线方法 — 标签生成

**目标**: backtest_logs ≥ 95%, grid_search ≥ 85% (从 68% 起步), init_wizard ≥ 90%, metrics ≥ 96% (保持), trade_lightning ≥ 85% (从 71% 起步), triple_barrier ≥ 96% (保持)


### 2.5 quantide/web/components/ 单测

> 对应 story §5。

<a id="fr-0501"></a>
### FR-0501 web/components/analysis/ 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`web/components/analysis/` 单测:

- **kline_chart.py** (基线 26%):
  - K 线图渲染: 数据 → HTML/SVG 输出 (含 OHLC + 成交量)
  - 颜色规则: 涨绿 / 跌红
  - 交互: hover / click (mock 回调)
- **stock_list.py** (基线 33%):
  - 股票列表渲染: 数据列表 → HTML
  - 过滤 / 排序 / 搜索
  - 高亮 / 选中状态
- **backtest_charts.py** (基线 100%): 验证已有 (净值/回撤/热力图)

**目标**: kline_chart ≥ 85% (从 26% 起步, 大缺口), stock_list ≥ 85% (从 33% 起步), backtest_charts 保持 100%

<a id="fr-0502"></a>
### FR-0502 web/components/ 通用组件单测 (验证类)

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

story §5 标注这些组件当前 100% 覆盖, 本 FR **验证** 已有覆盖:

- `header.py`: 100% (顶部 nav bar / brand / 导航菜单 / 告警图标 / 用户菜单)
- `sidebar.py`: 100% (左侧导航栏 / 多级菜单 / 折叠状态)
- `toast.py`: 100% (success/error/warning/info 4 类)
- `runtime_params.py`: 100% (运行时参数编辑表单)
- `asset_label.py`: 100% (资产标签)

**目标**: 保持 100%, 若重构后掉覆盖, 需补回

**约束**:
- 不删除已有测试
- 重构组件时同步更新测试


### 2.6 CI/CD 与质量门禁

> 对应 story §6。

<a id="fr-0601"></a>
### FR-0601 CI 强制覆盖率门槛

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

CI 流水线配置:

- 在 `.github/workflows/` 中添加或更新 workflow:
  - 触发条件: `push` 到 `releases/**` 与 `pull_request` 到 `main` / `releases/**`
  - 步骤: `pytest tests/unit --cov=quantide --cov-fail-under=95 --cov-report=term-missing`
  - 失败: 覆盖率 < 95% 时, CI exit 1, 阻断合并
- 现有 `.github/workflows/louke-ci.yml` 已有 `lk archer ci-scan`, 不冲突; 新 workflow 可命名为 `unit-coverage.yml`

**约束**:
- 不修改 `louke-ci.yml` (Louke 项目自身维护)
- 不引入第三方 coverage 服务 (codecov) 作为门禁 (可选上传, 不阻断)
- 覆盖率工具仅 `pytest-cov`

<a id="fr-0602"></a>
### FR-0602 HTML 覆盖率报告 + 增量覆盖率 (可选)

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

附加 CI 行为:

- **HTML 报告**: CI 步骤追加 `--cov-report=html:htmlcov`, 通过 `actions/upload-artifact@v4` 上传 (保留 30 天)
- **增量覆盖率 (diff-cover)**: story §6 标注 "可选", 用 `diff-cover` 工具检查 PR 新增代码覆盖率 ≥95%
  - 实施阶段由 Aaron 决定是否启用

**约束**:
- HTML 报告**不阻断** CI, 仅作 artifact
- diff-cover **可选**, 标注在 workflow 中但默认 `continue-on-error: true`


---

## 7. 非功能需求

<a id="nfr-0010"></a>
### NFR-0010 覆盖率阈值与豁免机制

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

**阈值**:
- **整体覆盖率**: ≥ 95% (CI 强制)
- **单模块覆盖率**: ≥ 80% (低 80% 需说明)
- **未达标处理**: PR 阶段 CI 失败; 本地开发仅 warning

**豁免清单** (允许低于 80% 的模块, 不在覆盖率门槛范围):

| 模块                                  | 原因                          | 替代方案                       |
| ------------------------------------- | ----------------------------- | ------------------------------ |
| `quantide/core/__init__.py`           | 仅 import 暴露, 1-3 行        | 100% 自动达标                  |
| `quantide/data/services/__init__.py`  | 空文件 (0 stmts)              | 100% 自动达标                  |
| 其它 `__init__.py`                    | 空文件或仅 import             | 100% 自动达标                  |

**临时豁免申请流程** (适用于本 spec 范围内, 但某模块短期内无法达 80%):
1. 在 PR description 中说明: 模块名 / 当前覆盖 / 不达标原因 / 补救计划
2. 在 `pyproject.toml` `[tool.coverage.report]` 加注释 (不修改 exclude_lines)
3. 跟进 issue: 创建 `coverage-<module>` issue, 跟踪后续补齐

> **Sage**: Q-NFR-0010 豁免清单 (开放问题): 本 spec 范围内, 哪些模块可以永久豁免? Sage 默认提议仅 `__init__.py` 空文件。其余模块即便实施阶段短期未达 80%, 也需要走 "临时豁免申请流程"。**请 Aaron 确认** 这一边界。
>> **Sage Round 2**: 当前基线下, 没有模块被 Sage 标记为豁免 (除 `__init__.py`)。所有 ≥80% 目标都是"应达目标", 由实施阶段决定如何补齐。如果实施时发现某模块确实不可达, 走申请流程。

<a id="nfr-0020"></a>
### NFR-0020 测试隔离与确定性

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

所有单测满足:

- **可重复**: 同一测试连续跑 100 次结果一致
- **可并行**: `pytest -n auto` (pytest-xdist, 可选) 不因并行导致失败
- **可独立**: 任意测试可单独跑 (`pytest tests/unit/quantide/core/test_xxx.py::test_yyy`), 不依赖其它测试状态
- **不污染**: 测试结束后, 无残留文件 / 全局状态 / 模块级变量

**禁止的写法**:
- 全局可变状态 (例: `module_var = []`)
- 时间依赖 (`datetime.now()` 无 mock)
- 文件系统硬编码路径 (应用 `tmp_path`)
- 网络依赖 (应用 mock)
- 数据库持久化 (`tests/` 目录不残留 .db / .sqlite)


---

## 已知约束与排除

> **Sage**: Q-Spec-Scope 整体 ≥95% 可达性 (关键开放问题): 当前覆盖率基线 **69%**, story §6 要求整体 **≥95%**, 缺口 **26pp**。这是大跨度提升, 需要约 **3100 行覆盖** (粗算: 4856 miss / 0.95 ≈ 4975 expected miss, 当前 4856, 即需要减少 ~113 条 miss 行 OR 新增 1320 行可执行代码 → 实际是两者皆有)。
> **请 Aaron 确认**: 这个 ≥95% 是 **v0.2 必达目标** (lock 阶段硬性), 还是 **阶段性目标** (v0.2-003 至少推到 90%, 95% 留给后续 spec)? 这个决定影响本 spec 的实施范围与工作量。
>> **Sage Round 2 默认方案**: Sage 推荐 ≥95% 为 **v0.2 必达目标**, 但允许通过"豁免清单"或"模块分级"放宽个别不可达模块 (见 NFR-0010)。如果 Aaron 倾向阶段性 (90% for v0.2), 需要调整所有 FR 的目标值。

### 不在本 spec 范围 (与 v0.2-002-ui 边界)

- `quantide/web/pages/` / `quantide/web/auth/` / `quantide/web/apis/` / `quantide/web/middleware*` → v0.2-002-ui 已 lock (99% web/services)
- `quantide/web/nfr_*.py` (无障碍/错误降级/长任务等) → v0.2-002-ui NFR-0010~0070 已 lock
- `quantide/web/services/` / `quantide/web/layouts/` → v0.2-002-ui 100% 覆盖, 验证保持

### 不在 v0.2 范围 (后续 spec)

- `quantide/notify/` (dingtalk / mail) → 通知层后续 spec
- `quantide/strategies/example/` (dual_ma.py 等示例策略) → 已有 e2e, 单测可后续补
- `quantide/config/dev_stubs.py` (61%) → 配置层后续 spec
- `quantide/web/auth/utils.py` (0%) → auth 后续 spec

### 工具限制

- `lk agent lex verify-issue` 不支持 `--branch` 参数 (louke bug, 已知, 不影响本 spec 验证)
- `lk agent lex verify-issue` 用英文 label, 项目 ISSUE_TEMPLATE 用中文 label (louke bug, workaround: feature.yml 用英文 label, 已应用于 v0.2-002-ui)


---

## 实施阶段交付物

实施阶段 (M-DEV) 应输出:

1. **测试代码** (`tests/unit/quantide/<module>/`):
   - 至少每个 FR 对应 1 个测试文件
   - 路径与源码一致 (例: `quantide/core/runtime/clock_bridge.py` → `tests/unit/quantide/core/runtime/test_clock_bridge.py`, 已存在则补齐)
   - 命名: `test_<source_module>.py`
2. **覆盖率报告**:
   - 终端报告 (`--cov-report=term-missing`) 显示缺行
   - HTML 报告 (`htmlcov/index.html`) 提交前本地查看
3. **豁免文档** (如适用):
   - PR description 中说明豁免模块
   - 不达 80% 的模块需要单独的 follow-up issue
4. **CI 配置**:
   - `.github/workflows/unit-coverage.yml` 新增
   - 现有 `louke-ci.yml` 不修改
