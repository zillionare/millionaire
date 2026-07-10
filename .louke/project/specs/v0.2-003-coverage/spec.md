# Millionaire Coverage Spec — 单元测试覆盖率提升

- **Spec ID**: v0.2-003-coverage
- **创建日期**: 2026-07-09
- **状态**: 草稿 (code review 校准: 扩展覆盖范围 + 反作弊验收)
- **Story 同步基线**: `.louke/project/specs/v0.2-003-coverage/story.md`
- **上游 spec**:
  - [v0.2-001-strategy-framework](../v0.2-001-strategy-framework/spec.md) — 策略框架/调度/数据/SDK
  - [v0.2-002-ui](../v0.2-002-ui/spec.md) — UI 覆盖 (已 lock, web/services 99%, 但核心/数据/服务/UI 组件层未覆盖)

> **Sage 注释 (草稿状态) [RESOLVED]**: 本 spec 中所有 inline-discussion quote 当前均为 **open 状态** (无 marker)。Sage 不能在 Aaron 回复前擅自标记 `[RESOLVED]` (per agent.md §3.2 "Silence is NOT consent")。待 Aaron IDE review 答复后, 由 Sage 在下一轮回复中将对应 root comment 加 `[RESOLVED]`。
>> **Aaron [RESOLVED]**: 默认全部同意 6 个 quote 回复, 你帮我直接标 `[RESOLVED]` 加 reply。

> **Sage** [RESOLVED]: Q-Spec-Format FR 编号偏差 (关键开放问题): 任务原文 "FR 编号: `UI-TEST-XXXX` (4 位, 0.8 期望)" 与 louke 0.8.0 的 `verify_acceptance.py` 正则不兼容 (工具硬编码接受 `FR-XXXX` 或 `NFR-XXXX`, 不接受 `UI-TEST-XXXX`)。Sage 选择遵循工具约定, 使用 `FR-XXXX` (与 v0.2-002-ui 一致)。**请 Aaron 确认**: 是预期 fallback (`FR-XXXX`), 还是需要升级 louke 工具以支持 `UI-TEST-XXXX` 前缀? 如果是后者, 本 spec 在 lock 前需要阻塞。
>> **Aaron [RESOLVED]**: 同意 Sage 方案 1, 用 `FR-XXXX` (与 v0.2-002-ui 一致, louke 工具兼容)。先不解 louke 兼容性, 后续 spec 可以升级。
>> **Sage Round 2 备选方案**: 如果 Aaron 坚持 `UI-TEST-XXXX`, 备选方案是用 `FR-XXXX` + 在 FR 标题加 `[UI-TEST]` 前缀 (例: `### FR-0101 [UI-TEST] pytest 配置与覆盖率命令`), 这样 verify-acceptance 通过, 但语义上仍能区分测试类 FR。但 Sage 推荐方案 1 (纯 `FR-XXXX`)。

> **本 spec 仅定义测试覆盖率提升任务的需求与验收**, 不重复定义业务规则。
> 业务计算/调度/数据/撮合规则 → v0.2-001-strategy-framework。
> UI 展示/交互契约 → v0.2-002-ui。
> 本 spec 通过引用上游 FR/AC 与当前覆盖率缺口, 推动实施阶段补齐有行为断言的单测。


## 当前覆盖率基线 (2026-07-09)

| 模块域       | Stmts    | Miss    | Cover | 目标状态 |
| ------------ | -------- | ------- | ----- | -------- |
| **TOTAL**    | **15657** | **4856** | **69%** | ❌ (目标 ≥95%, 最多 782 miss) |
| quantide/core/ | 1740 | 274 | 84.25% | ✅ 域达标, 个别模块低于 80% |
| quantide/data/ | 2132 | 328 | 84.62% | ✅ 域达标, 个别模块低于 80% |
| quantide/service/ | 3404 | 865 | 74.59% | ❌ |
| quantide/web/components/ | 272 | 41 | 84.93% | ✅ 域达标, 个别模块低于 80% |
| quantide/web/(其它) | 7257 | 3108 | 57.17% | ❌ |
| quantide/notify/ | 197 | 112 | 43.15% | ❌ |
| quantide/strategies/ | 126 | 31 | 75.40% | ❌ |
| quantide/config/ | 384 | 55 | 85.68% | ✅ 域达标, 个别模块低于 80% |
| quantide 根模块 | 145 | 42 | 71.03% | ❌ |

> **范围声明**: 本 spec 覆盖当前 `coverage.json` 中所有属于 v0.2 已交付面的 `quantide/` 生产模块缺口。早期草稿只覆盖 `core/data/service/web/components` 时, 即使这些域全到 100%, TOTAL 仍约 79%, 与 v0.2 必达 ≥95% 冲突。因此本轮校准将 `web/pages`、`web/auth`、`web/apis`、`web/middleware*`、`notify`、`strategies`、`config/dev_stubs.py`、`app_factory.py` 等低覆盖模块纳入本 spec。

### 单模块低于 80% 名单 (coverage.json)

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
| `quantide/web/pages/*.py` 多模块 | 18%~72% | 8pp~62pp | FR-0503 |
| `quantide/web/auth/*.py` 多模块 | 0%~58% | 22pp~80pp | FR-0504 |
| `quantide/web/apis/*.py` 多模块 | 19%~46% | 34pp~61pp | FR-0504 |
| `quantide/web/middleware*.py` | 47%~69% | 11pp~33pp | FR-0504 |
| `quantide/notify/*.py` | 15%~62% | 18pp~65pp | FR-0701 |
| `quantide/strategies/example/dual_ma.py` | 42% | 38pp | FR-0702 |
| `quantide/config/dev_stubs.py` | 61% | 19pp | FR-0703 |
| `quantide/app_factory.py` | 68% | 12pp | FR-0703 |


## 章节映射表

| spec.md 章节          | story.md 章节      | 内容主题                                            | 主要 FR                    |
| --------------------- | ------------------ | --------------------------------------------------- | -------------------------- |
| §1 测试基础设施       | story §1           | pytest 配置 / 覆盖率阈值 / Mock / Fixture / 隔离    | FR-0101~0104             |
| §2 core/ 单测         | story §2           | domain / runtime / strategy / ports 单元测试       | FR-0201~0207             |
| §3 data/ 单测         | story §3           | fetchers / models / stores / sqlite / utils 单测    | FR-0301~0304             |
| §4 service/ 单测      | story §4           | strategy_runtime / brokers / datafeed / 其它服务   | FR-0401~0404             |
| §5 web/ 单测 | story §5 + v0.2-002-ui | components / pages / auth / APIs / middleware | FR-0501~0504 |
| §6 CI/CD              | story §6           | GitHub Actions / --cov-fail-under / diff-cover     | FR-0601~0602             |
| §7 其它 v0.2 模块     | v0.2-001/002       | notify / strategies / config / app bootstrap       | FR-0701~0703             |
| §8 NFR                | —                  | 覆盖率阈值 / 排除清单 / 测试确定性 / 反作弊         | NFR-0010~0030            |


---

## Traceability Matrix

本矩阵定义 v0.2-003 每个覆盖率 FR 应保护的上游合同。实施阶段新增测试优先断言这些上游 AC/FR 的外部可观察结果, 覆盖率阈值只作为质量门禁。

| v0.2-003 FR | 模块域 | 上游合同来源 | 测试重点 |
| ----------- | ------ | ------------ | -------- |
| FR-0101~0104 | 测试基础设施 | v0.2-001 test-plan §6.4 / v0.2-002 test-plan §2 | 统一命令、fixture、隔离、可重复 |
| FR-0201 | `core/domain` | v0.2-001 FR-010 / interfaces §6 | 事件序列化、日志/事件 payload |
| FR-0202 | `core/runtime/clock_bridge` | v0.2-001 NFR-060 / test-plan §6.4.1 | 虚拟时钟装配、日历帧输出 |
| FR-0203 | `core/runtime/gateway_*` | v0.2-001 FR-300 / interfaces §3.3 / §7.0.3 | HTTP JSON 协议、订单/查询适配、错误保护 |
| FR-0204 | `core/runtime/modes`, `port_broker` | v0.2-001 FR-040 / FR-210 / FR-220 | 运行模式枚举、BrokerPort 到旧 UI 模型适配 |
| FR-0205 | `strategy`, `strategy_discovery`, `scheduler` | v0.2-001 FR-010 / FR-020 / FR-230~250 | 生命周期钩子、策略发现 schema、调度入口 |
| FR-0206 | core 基础模块 | v0.2-001 FR-010 / FR-440 / FR-450 | 枚举、消息、异常、SDK 元数据 |
| FR-0207 | `core/ports` | v0.2-001 interfaces §2 / §7 | 端口协议、可测试装配点 |
| FR-0301 | `data/fetchers` | v0.2-001 FR-270 / FR-280 / FR-290 / FR-300 | Tushare 请求/响应/错误、fetcher registry |
| FR-0302 | `data/models` | v0.2-001 FR-014 / FR-015 / FR-330 | 日历、证券、行情、指数模型 |
| FR-0303 | `data/stores`, `sqlite` | v0.2-001 interfaces §4.12~§4.17 / FR-330 | CRUD、事务、查询、SQLite 边界 |
| FR-0304 | `data/helper`, `resampler` | v0.2-001 FR-480 / FR-484 / FR-485 | 重采样、证券代码、研究辅助 |
| FR-0401 | strategy runtime/services | v0.2-001 FR-230~250 / FR-440 | 运行状态、启动/停止、blocked/failed 边界 |
| FR-0402 | brokers | v0.2-001 FR-140~220 | 撮合、T+1、资金、虚拟账本 |
| FR-0403 | datafeed/livequote | v0.2-001 FR-300 / NFR-060 | pull-style bars、行情 stream/snapshot |
| FR-0404 | service 辅助模块 | v0.2-001 FR-340~360 / FR-460 / FR-480 | 指标、网格搜索、初始化、闪电交易、三柱线 |
| FR-0501~0502 | web components | v0.2-002 FR-0170 / FR-0330 / FR-0370 / NFR-0040 | 语义 DOM / 组件输出 / 颜色 class |
| FR-0503 | web pages | v0.2-002 FR-0010~0460 / NFR-0050 | 页面字段、按钮状态、局部失败隔离 |
| FR-0504 | auth/apis/middleware | v0.2-002 FR-0110~0180 / v0.2-001 interfaces §3 | 登录会话、API response、路由/降级 |
| FR-0601~0602 | CI/CD | v0.2 DoD / NFR-0010 | 总覆盖率、单模块阈值、artifact |
| FR-0701 | notify | v0.2-001 FR-450 / v0.2-002 FR-0450 | 通知 payload、失败不泄密 |
| FR-0702 | strategies | v0.2-001 FR-090 / FR-100 / FR-110 | 内置策略信号与边界 |
| FR-0703 | config/app bootstrap | v0.2-001 FR-470 / v0.2-002 FR-0110 / FR-0460 | 路径/设置、app factory、初始化路由 |
| NFR-0010~0030 | 全域 | v0.2 DoD / v0.2-001 test-plan §1.3 | 阈值、隔离、反作弊 |


## 0. 范围与边界

### 0.1 在本 spec 范围内

- `quantide/core/` 全模块单元测试 (`domain/`、`runtime/`、`strategy.py`、`strategy_discovery.py`、`scheduler.py`、`enums.py`、`message.py`、`errors.py`、`sdk_metadata.py`、`ports/`)
- `quantide/data/` 全模块单元测试 (`fetchers/`、`models/`、`stores/`、`sqlite.py`、`helper.py`、`utils/`)
- `quantide/service/` 全模块单元测试 (`strategy_runtime.py`、`discovery.py`、`registry.py`、`runner.py`、`abstract_broker.py`、`backtest_broker.py`、`sim_broker.py`、`datafeed.py`、`livequote.py`、`backtest_logs.py`、`grid_search.py`、`init_wizard.py`、`metrics.py`、`trade_lightning.py`、`triple_barrier.py`)
- `quantide/web/` 全模块单元测试与组件级行为验证 (`components/`、`pages/`、`auth/`、`apis/`、`middleware*`、`services/`、`layouts/`、`nfr_*.py`)
- `quantide/notify/` 通知通道单元测试 (微信/邮件/钉钉事件格式与失败路径)
- `quantide/strategies/` 内置/示例策略单元测试 (双均线/回落卖出/成本止损契约)
- `quantide/config/` 与根启动模块 (`app.py`、`app_factory.py`) 单元测试
- 测试基础设施 (pytest 配置、Mock 框架、Fixture 共享、覆盖率报告)
- CI/CD 集成 (GitHub Actions `--cov-fail-under`)

### 0.2 不在本 spec 范围内

- 外部真实服务连通性 (真实 qmt-gateway / 邮件服务器 / 钉钉或微信机器人 / Tushare 远程 API)
- 新业务能力或 UI 新交互设计 (本 spec 只要求现有 v0.2 已定义行为可被单测覆盖)
- 业务规则 (策略评估、撮合、T+1 等) → v0.2-001-strategy-framework
- 集成测试 / 端到端测试 → v0.2-001-strategy-framework test-plan §5/§6
- 性能测试 (Lighthouse、表格 FPS) → NFR-0010 (v0.2-002-ui 已定义)


---

## 1. 用户故事

### 1.1 测试基础设施

> 对应 story §1 "作为开发者, 我需要建立统一的测试基础设施, 以便高效地为所有模块编写和运行单元测试"

#### US-0101
story: 作为开发者, 我希望用统一命令 (`poetry run pytest --cov=quantide`) 跑覆盖率, CI 中能强制 ≥95% 整体阈值, 以便任何 PR 合并前都能看到覆盖率变化。
priority: P0

> **Sage** [RESOLVED]: Q-US-0101 阈值来源: story §6 已明确 "整体 ≥95%, 单模块 ≥80%", 而 `meta.dod` 同样写 "单元测试覆盖率 ≥95%"。这是双重确认, 不需要二次确认 — 但请 Aaron 在 IDE 中 **确认** 这个解读与你预期一致 (即 v0.2 必须达到 ≥95% 整体覆盖率才能 lock)。
>> **Aaron [RESOLVED]**: 确认 ≥95% 整体, ≥80% 单模块, 双重约束。

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
story: 作为开发者, 我希望 CI 在 push/PR 时自动跑 `poetry run pytest --cov=quantide --cov-fail-under=95`, 以便任何代码合并都通过覆盖率门槛。
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
## FR-0101 pytest 配置与覆盖率命令

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

项目统一通过 `pyproject.toml` 中 `[tool.pytest.ini_options]` 与 `[tool.coverage.*]` 配置, 提供以下命令:

- `poetry run pytest tests/unit`: 仅跑单元测试 (排除 `e2e` marker)
- `poetry run pytest --cov=quantide --cov-report=term-missing`: 终端显示缺哪些行
- `poetry run pytest --cov=quantide --cov-report=html`: 生成 `htmlcov/` HTML 报告
- `poetry run pytest --cov=quantide --cov-fail-under=95`: 整体覆盖率低于 95% 时 exit 1
- 单模块: 使用 `poetry run pytest --cov=quantide/core --cov-fail-under=80` 单独验证

**约束**:
- 配置在 `pyproject.toml` 中, 单一来源
- 不创建 `pytest.ini` / `setup.cfg` (避免多源)
- `asyncio_mode = "auto"` 保留 (异步测试无需 `@pytest.mark.asyncio`)

> **Sage** [RESOLVED]: Q-FR-0101 配置位置: story §1 提到 "pytest.ini 或 pyproject.toml"。本项目 pyproject.toml 已有 `[tool.pytest.ini_options]` 与 `[tool.coverage.*]`, 沿用现有结构, 不引入 pytest.ini。**请 Aaron 确认** 这一选择 (沿用 pyproject.toml) 与预期一致。
>> **Aaron [RESOLVED]**: 同意沿用 pyproject.toml, 不引入 pytest.ini。

<a id="fr-0102"></a>
## FR-0102 覆盖率阈值与排除清单

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

覆盖率分级阈值:

- **整体**: ≥ 95% (CI `--cov-fail-under=95`)
- **单模块**: ≥ 80% (低 80% 模块需在人工 review artifact 或 PR 说明中列明原因与补救 issue; 不通过 coverage 配置绕过)

**允许豁免的模块** (按 v0.2-002-ui 类似豁免机制, 详见 NFR-0010):
- `quantide/core/__init__.py`: 0% 或可豁免 (只是 import 暴露)
- `quantide/data/services/__init__.py`: 0% (空文件)
- 各 `__init__.py` 空文件: 100% 自动达标

**单模块豁免申请**: 实施阶段若发现某模块无法达 80%, 需在人工 review artifact 或 PR description 中说明:
- 模块名 + 当前覆盖率 + 原因 (第三方依赖/不可达分支/纯数据类等)
- 替代方案 (mock 改进/重构/接受低覆盖)
- 同步写入 `.louke/project/specs/v0.2-003-coverage/coverage-waivers.json`; 默认 `waivers=[]`

<a id="fr-0103"></a>
## FR-0103 Mock 框架与 Fixture 共享

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

测试使用统一的 Mock 框架与 Fixture:

- **Mock 框架**: `unittest.mock` (`MagicMock` / `AsyncMock` / `patch`) + pytest 内置 `monkeypatch`
- **Fixture 共享**: 集中在 `tests/unit/conftest.py` (已存在, 见 `env` fixture); 仅在目录级隔离确有必要时新增更深层 `conftest.py`
- **数据层 mock**:
  - mock 行情数据: polars DataFrame fixture (`daily_bars.parquet` 等已存在)
  - mock 日历: `env.calendar` fixture (已存在)
  - mock 网关: `MagicMock(spec=GatewayProtocol)` 或 `FakeGateway` 测试替身
  - mock 数据库: 临时 SQLite `:memory:` 或 `tmp_path` fixture
- **时间 mock**: `freezegun` (`@freeze_time("2024-01-02")`) 用于固定时间测试

**约束**:
- 不引入新的 mock 库 (`mock` / `pytest-mock` / `responses` / `httpx-mock` 等不在依赖中, 避免膨胀)
- 数据 fixture 优先复用 `tests/assets/unit/fixtures/data/` (现有资产)

<a id="fr-0104"></a>
## FR-0104 测试隔离与确定性

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

每个测试用例独立, 不依赖执行顺序:

- **测试无副作用**: 不修改全局状态 / 模块级变量 / 临时文件不残留
- **fixture 生命周期**: 函数级默认 (`scope="function"`); 只有 env 数据 (parquet) 可 session 级
- **临时资源**: 用 `tmp_path` fixture 创建, 测试结束自动清理
- **数据库**: 用 `:memory:` 或 `tmp_path` 下的 SQLite 文件, 不污染 `tests/` 目录
- **mock 还原**: `monkeypatch` 自动还原; `unittest.mock.patch` 使用 context manager 或 fixture teardown 还原
- **确定性时间**: 使用 `freezegun` 或显式注入 `datetime`, 不依赖 `datetime.now()`
- **顺序无关**: 当前 test 依赖不声明 `pytest-xdist`; 本 spec 不要求 `poetry run pytest -n auto`, 但要求任意单测可单独运行且不依赖执行顺序


### 2.2 quantide/core/ 单测

> 对应 story §2。

<a id="fr-0201"></a>
## FR-0201 core/domain/ 单测

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
## FR-0202 core/runtime/clock_bridge 单测

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
## FR-0203 core/runtime/gateway_broker + gateway_client 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`quantide/core/runtime/gateway_broker.py` (基线 80%) + `gateway_client.py` (基线 75%) 单元测试:

- **gateway_broker**:
  - 下单适配: buy / sell / cancel / cancel_all / trade_target_pct 到网关 HTTP form payload
  - 查询适配: positions / assets / orders / trades payload 到 port view 与旧 UI 模型
  - 错误处理: 网关鉴权失败 / 订单拒绝 / qtoid 与外部订单号不一致
- **gateway_client**:
  - HTTP 会话: `ensure_login()` / `get_json()` / `post_form()`
  - 协议保护: JSON/text 响应可解析, htmx/text/html 响应抛 `GatewayProtocolError`
  - 边界: 空 body 返回 None, cookie header 导出, ws/wss URL 转换

**目标**: gateway_broker ≥ 90%, gateway_client ≥ 90%

<a id="fr-0204"></a>
## FR-0204 core/runtime/modes + port_broker 单测

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
## FR-0205 core/strategy + strategy_discovery + scheduler 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`strategy.py` (基线 79%) + `strategy_discovery.py` (基线 82%) + `scheduler.py` (基线 94%) 单元测试:

- **strategy**:
  - 生命周期: 通过公开运行入口驱动策略 fixture, 断言 v0.2-001 生命周期日志/事件顺序
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
## FR-0206 core/ 基础模块单测 (enums / message / errors / sdk_metadata)

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
## FR-0207 core/ports/ 单测

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
## FR-0301 data/fetchers/ 单测

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
## FR-0302 data/models/ 单测

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
## FR-0303 data/stores/ + sqlite 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`data/stores/` + `data/sqlite.py` 单测:

- **stores/base.py** (基线 79%): 基础存储 — CRUD / 事务 / 查询 / 索引
- **stores/index_bars.py** (基线 38%): 指数存储 — CRUD / 批量写入 / 查询
- **sqlite.py** (基线 90%): SQLite 操作 — 连接 / 表创建 / 索引 / 备份 / 迁移

**目标**: stores/base ≥ 90%, stores/index_bars ≥ 80% (从 38% 起步), sqlite ≥ 95%

<a id="fr-0304"></a>
## FR-0304 data/helper + utils/resampler 单测

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
## FR-0401 service/ 策略运行时与执行器单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`service/` 策略运行时四件套单测:

- **strategy_runtime.py** (基线 65%):
  - 运行时实例: 创建 / 启动 / 停止 / 销毁
  - 状态转换: `idle` / `running` / `stopping` / `stopped` / `failed` / `finished` / `blocked`
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
## FR-0402 service/ 三类 broker 单测

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
## FR-0403 service/ 数据馈送与实时行情单测

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
## FR-0404 service/ 其它服务单测

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
## FR-0501 web/components/analysis/ 单测

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
## FR-0502 web/components/ 通用组件单测 (验证类)

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

<a id="fr-0503"></a>
## FR-0503 web/pages/ 页面模块单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`quantide/web/pages/` 单测覆盖 v0.2-002-ui 页面契约, 不重新定义 UI 业务规则:

- **策略/交易/账户页面** (`strategy.py` / `trade_main.py` / `trade_lightning.py` / `accounts.py` / `paper.py` / `live.py`):
  - 给定 mock service 返回的账户、策略、委托、成交、回测报告数据, 页面输出包含 v0.2-002-ui 对应 FR 要求的字段、按钮、状态徽章。
  - 表单输入校验与按钮可用性按 v0.2-002-ui FR-0020 / FR-0040 / FR-0390 / FR-0410 / FR-0420 / FR-0430 断言。
- **系统与数据页面** (`data_*.py` / `system/*.py` / `init_wizard.py`):
  - 给定数据同步、网关、数据完整性、初始化向导 fixture, 页面输出匹配 v0.2-002-ui FR-0310 / FR-0320 / FR-0330 / FR-0340 / FR-0460。
  - 失败状态只降级对应局部区域, 不让整页空白 (对齐 v0.2-002-ui NFR-0050)。
- **历史页面** (`history_orders.py` / `history_trades.py` / `history_positions.py`):
  - 给定查询条件与 mock 记录, 渲染结果按时间/策略/标的过滤, 字段对齐 v0.2-001 interfaces orders/trades/positions schema。

**目标**: 所有 `quantide/web/pages/*.py` 与 `quantide/web/pages/system/*.py` 单模块 ≥ 80%, 且 `web/pages` 域整体 ≥ 90%。

**约束**:
- 单测只 mock service 层返回值; 不 mock 当前页面函数本身。
- 不需要浏览器 e2e; DOM 字符串、组件树或 FastHTML 节点结构可作为可观察输出。

<a id="fr-0504"></a>
## FR-0504 web/auth + web/apis + middleware 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`quantide/web/auth/`、`quantide/web/apis/` 与 `quantide/web/middleware*.py` 单测覆盖 v0.2-002-ui 的认证、路由和 API 边界:

- **auth**:
  - 登录成功/失败、改密码成功/失败、登出、未登录重定向、session 建立与清除, 对齐 v0.2-002-ui FR-0120 / FR-0130 / FR-0140。
  - repository/database 层用临时 SQLite 或 in-memory store, 不写真实用户数据。
- **APIs**:
  - broker API handler: 请求 payload 校验、成功响应、错误码, 对齐 v0.2-001 interfaces §3.3 与 v0.2-002-ui 调度/交易页面。
  - analysis API handler: K 线/搜索请求参数校验、空结果、错误结果, 对齐 v0.2-002-ui FR-0330 / FR-0370。
- **middleware**:
  - 初始化向导强制路由、认证拦截、A/B 类功能降级、异常转响应, 对齐 v0.2-002-ui FR-0110 / FR-0180 / NFR-0030。

**目标**: `web/auth/*.py`、`web/apis/*.py`、`web/middleware*.py` 单模块 ≥ 80%, 域整体 ≥ 90%。

**约束**:
- API 测试断言 status code / response body / redirect target, 不断言内部私有变量。
- 密码与 token 只用测试 fixture, 不读取真实环境变量或本机凭证。


### 2.6 CI/CD 与质量门禁

> 对应 story §6。

<a id="fr-0601"></a>
## FR-0601 CI 强制覆盖率门槛

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

CI 流水线配置:

- 在 `.github/workflows/` 中添加或更新 workflow:
  - 触发条件: `push` 到 `releases/**` 与 `pull_request` 到 `main` / `releases/**`
  - 步骤: `poetry install --with test --no-interaction`
  - 步骤: `poetry run pytest tests/unit --cov=quantide --cov-fail-under=95 --cov-report=term-missing --cov-report=json:coverage.json`
  - 步骤: 运行覆盖率阈值检查脚本, 读取 `coverage.json` 和 `coverage-waivers.json`, 强制每个非豁免生产模块 ≥80%
  - 失败: 整体覆盖率 <95%, 或任何非豁免生产模块 <80%, CI exit 1, 阻断合并
- 现有 `.github/workflows/louke-ci.yml` 已有 `lk archer ci-scan`, 不冲突; 新 workflow 可命名为 `unit-coverage.yml`

**约束**:
- 不修改 `louke-ci.yml` (Louke 项目自身维护)
- 不引入第三方 coverage 服务 (codecov) 作为门禁 (可选上传, 不阻断)
- 覆盖率工具仅 `pytest-cov`

<a id="fr-0602"></a>
## FR-0602 HTML 覆盖率报告 + 增量覆盖率 (可选)

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

### 2.7 其它 v0.2 已交付模块单测

<a id="fr-0701"></a>
## FR-0701 notify/ 通知通道单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`quantide/notify/` 单测覆盖 v0.2-001 FR-450 与 v0.2-002-ui FR-0450 的通知契约:

- `notify/mail.py`: 配置校验、消息主题/正文渲染、附件/HTML 选项、发送成功、SMTP 失败。
- `notify/dingtalk.py`: webhook payload 格式、签名/关键字配置、HTTP 成功、HTTP 失败、超时。
- `notify/__init__.py`: 通道导出、工厂/注册表 (如存在)、未知通道错误。

**目标**: `quantide/notify/*.py` 单模块 ≥ 80%, 域整体 ≥ 90%。

**约束**:
- 不发真实网络请求; SMTP/HTTP 全部 mock 到边界。
- 断言错误日志和异常消息不泄露 token/password/webhook secret。

<a id="fr-0702"></a>
## FR-0702 strategies/ 内置与示例策略单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`quantide/strategies/` 单测覆盖 v0.2-001 FR-090 / FR-100 / FR-110:

- `example/dual_ma.py`: 默认参数、短均线上穿/下穿信号、无交叉不下单、缺失行情/窗口不足边界。
- `pullback_sell.py`: 回落阈值触发、未触发、持仓为空、价格缺失边界。
- `cost_stop_loss.py`: 成本止损触发、未触发、成本价缺失、只卖宿主持仓。

**目标**: `quantide/strategies/*.py` 与 `quantide/strategies/example/*.py` 单模块 ≥ 80%, 域整体 ≥ 90%。

**约束**:
- 单测断言策略对给定行情/持仓 fixture 的输出信号或 broker 调用, 不跑完整 e2e 回测。
- 不把策略输出固定成对当前实现私有方法的调用次数; 以 v0.2-001 策略契约为准。

<a id="fr-0703"></a>
## FR-0703 config/ 与 app bootstrap 单测

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

`quantide/config/` 与根启动模块单测覆盖 v0.2-001 FR-470 与 v0.2-002-ui FR-0110 / FR-0460:

- `config/dev_stubs.py`: 测试替身安装/卸载、缺省路径、重复安装幂等、非法配置错误。
- `config/paths.py` / `settings.py` / `branding.py`: 默认值、环境变量覆盖、路径解析、品牌文案导出。
- `app_factory.py` / `app.py`: 已初始化/未初始化路由分流、依赖注入、错误处理、app 对象创建。

**目标**: `quantide/config/*.py` 与 `quantide/app*.py` 单模块 ≥ 80%, 域整体 ≥ 90%。

**约束**:
- 使用 `tmp_path` 和 `monkeypatch` 模拟 HOME / 数据目录 / 环境变量。
- 不启动真实 Web server; 只验证 factory 返回对象、route 注册、依赖装配和 redirect 决策。


## 8. 非功能需求

<a id="nfr-0010"></a>
## NFR-0010 覆盖率阈值与豁免机制

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
1. 在人工 review artifact 或 PR description 中说明: 模块名 / 当前覆盖 / 不达标原因 / 补救计划
2. 在 `.louke/project/specs/v0.2-003-coverage/coverage-waivers.json` 增加对应条目 (`module`, `current_coverage`, `reason`, `expires_at`, `followup_issue`)
3. 不修改 `[tool.coverage.run] omit` 或 `[tool.coverage.report] exclude_lines` 来隐藏模块
4. 跟进 issue: 创建 `coverage-<module>` issue, 跟踪后续补齐

> **Sage** [RESOLVED]: Q-NFR-0010 豁免清单 (开放问题): 本 spec 范围内, 哪些模块可以永久豁免? Sage 默认提议仅 `__init__.py` 空文件。其余模块即便实施阶段短期未达 80%, 也需要走 "临时豁免申请流程"。**请 Aaron 确认** 这一边界。
>> **Aaron [RESOLVED]**: 同意仅 `__init__.py` 空文件永久豁免, 其余走临时豁免流程。
>> **Sage Round 2**: 当前基线下, 没有模块被 Sage 标记为豁免 (除 `__init__.py`)。所有 ≥80% 目标都是"应达目标", 由实施阶段决定如何补齐。如果实施时发现某模块确实不可达, 走申请流程。

<a id="nfr-0020"></a>
## NFR-0020 测试隔离与确定性

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

所有单测满足:

- **可重复**: 同一测试连续跑 100 次结果一致
- **顺序无关**: 不依赖测试文件或用例执行顺序; 当前项目未声明 `pytest-xdist`, 不把 `poetry run pytest -n auto` 作为验收命令
- **可独立**: 任意测试可单独跑 (`poetry run pytest tests/unit/quantide/core/test_xxx.py::test_yyy`), 不依赖其它测试状态
- **不污染**: 测试结束后, 无残留文件 / 全局状态 / 模块级变量

**禁止的写法**:
- 全局可变状态 (例: `module_var = []`)
- 时间依赖 (`datetime.now()` 无 mock)
- 文件系统硬编码路径 (应用 `tmp_path`)
- 网络依赖 (应用 mock)
- 数据库持久化 (`tests/` 目录不残留 .db / .sqlite)

<a id="nfr-0030"></a>
## NFR-0030 有意义覆盖与反作弊

| 有效需求 | 可测性 | 是否已决定 |
| -------- | ------ | ---------- |
| ✅        | ✅      | ✅          |

覆盖率提升必须来自对 v0.2-001 / v0.2-002 可观察契约的行为断言:

- **必须断言行为**: 每个低覆盖模块至少覆盖一个正常路径、一个错误路径或边界路径; 断言输出、状态、响应、异常、日志或外部边界调用。
- **禁止 import-only 测试**: 只 import 模块、只实例化无行为对象、只断言常量存在, 不计入该模块的有效覆盖交付。
- **禁止 mock 被测主体**: 只能 mock 时间、网络、文件系统、数据库、远程服务、下游 service 边界; 不 mock 当前被测函数/类的主体逻辑。
- **禁止覆盖率配置作弊**: 不扩大 `[tool.coverage.run] omit`、不新增大范围 `exclude_lines`、不批量添加 `# pragma: no cover`、不降低 `--cov-fail-under`。
- **禁止删除有效代码换覆盖**: 删除代码只能基于上游 spec 明确排除或已有 dead-code 证据, 且需在 PR 说明中列出依据。

**评审口径**:
- 测试文件路径必须与源码路径对应, 以便 reviewers 能从源码缺口追到测试断言。
- 每个新增测试文件至少引用一个上游 FR/AC 或本 spec FR/AC (注释、测试名、docstring、或测试模块说明均可)。


---

## 已知约束与排除

> **Sage** [RESOLVED]: Q-Spec-Scope 整体 ≥95% 可达性 (关键开放问题): 当前覆盖率基线 **69%**, story §6 要求整体 **≥95%**, 缺口 **26pp**。以当前 15657 statements 计算, 95% 覆盖最多允许约 **782** miss 行; 当前 miss 为 **4856**, 因此需要减少约 **4074** miss 行 (若后续新增可执行代码, 目标 miss 上限随总 statements 变化重新计算)。
> **请 Aaron 确认**: 这个 ≥95% 是 **v0.2 必达目标** (lock 阶段硬性), 还是 **阶段性目标** (v0.2-003 至少推到 90%, 95% 留给后续 spec)? 这个决定影响本 spec 的实施范围与工作量。
>> **Aaron [RESOLVED]**: ≥95% 是 v0.2 必达目标, M-DEV 持续补齐, 用 NFR-0010 豁免清单管理个别不可达模块。
>> **Sage Round 2 校准**: 因 Aaron 确认为 v0.2 必达目标, 本 spec 已把 `web/pages`、`web/auth`、`web/apis`、`notify`、`strategies`、`config`、`app_factory` 等当前低覆盖模块纳入范围; 不再把这些模块推迟到后续 spec。

### 不在本 spec 范围

- 真实第三方服务联调 (真实 qmt-gateway、真实 SMTP、真实钉钉/微信 webhook、真实 Tushare 额度与网络)
- 浏览器端 e2e、性能测试、视觉回归测试 (由 v0.2-001/002 test-plan 或后续 spec 覆盖)
- 新功能需求或 UI 设计调整; 本 spec 只为现有 v0.2 行为补单测覆盖

### 不在 v0.2 范围 (后续 spec)

- 新通知渠道、新策略模板、新配置向导步骤
- 未在 v0.2-001 / v0.2-002 中定义的业务规则

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
   - 人工 review artifact 或 PR description 中说明豁免模块
   - 不达 80% 的模块需要单独的 follow-up issue
4. **CI 配置**:
   - `.github/workflows/unit-coverage.yml` 新增
   - 覆盖率阈值检查脚本新增, 读取 `coverage.json` 和 `coverage-waivers.json`
   - 现有 `louke-ci.yml` 不修改
5. **反作弊证据**:
   - review artifact 或 PR description 列出新增测试覆盖的 FR/AC 映射
   - 若覆盖率配置变化, 单独说明每一项变化的必要性
