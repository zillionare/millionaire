# Millionaire Coverage — Interface Contracts

- **Spec ID**: v0.2-003-coverage
- **阶段**: M-ARCH (Phase 2)
- **范围**: pytest 配置契约、`coverage-waivers.json` 与 `coverage.json` schema、按 FR 家族的测试接口契约、GitHub Actions workflow schema
- **原则**: 本文件只定义测试与 CI 的外部可观察契约，不重新定义 001/002 的业务接口；上游业务接口见 [v0.2-001 interfaces](../v0.2-001-strategy-framework/interfaces.md) 与 [v0.2-002 interfaces](../v0.2-002-ui/interfaces.md)。

---

## 1. 通用约定

### 1.1 pytest 配置来源（FR-0101 AC-5）

| 项 | 决策 |
| --- | --- |
| 配置入口 | `pyproject.toml` 的 `[tool.pytest.ini_options]` 与 `[tool.coverage.run/report]`；**禁止**新增 `pytest.ini` / `setup.cfg` / `tox.ini` |
| `asyncio_mode` | `"auto"`（保留 v0.2-001 设定） |
| `testpaths` | `["tests/unit"]` |
| 规范命令 | `poetry run pytest tests/unit --cov=quantide --cov-fail-under=95 --cov-report=term-missing --cov-report=json:coverage.json --cov-report=html:htmlcov` |
| branch coverage | 开启（`[tool.coverage.run] branch = true`） |
| `cov.source` | `quantide` |
| `cov.omit` | 不得为本任务新增生产模块排除（FR-0102 末段） |

### 1.2 测试集合与命名

| 项 | 决策 |
| --- | --- |
| 测试根目录 | `tests/unit/`；e2e 占位由 `tests/e2e/` 提供，单独由 Shield 维护（[project.toml e2e]） |
| 共享 fixture 位置 | `tests/unit/conftest.py`；按 FR 家族就近的 `conftest.py` 允许存在 |
| 文件命名 | `test_<module>.py`；基础设施位于 `tests/unit/_infra/`；门禁检查器位于 `tests/unit/_checkers/` |
| 文档锚点 | 每个测试模块 docstring、测试 docstring 或紧邻断言注释**至少**含 1 个可解析引用：`v0.2-001 ... FR/AC` / `v0.2-002 ... FR/AC` / `v0.2-003 ... FR/AC`（FR-0001 AC-1） |

### 1.3 expected-value 规则（NFR-0030 AC-3）

| 维度 | 规则 |
| --- | --- |
| 来源 | 独立 fixture、公式、上游示例或上游 schema；不得调用被测实现生成 expected value |
| 失败用例 | 必须含异常类型或 `ErrorEnvelope.code` 的显式断言，不允许只断言“调用未抛错” |
| 时间相关 | `freezegun` / `monkeypatch` / 显式注入时钟；禁止依赖真实“今天” |
| 异步等待 | 使用 event / condition / 可控时钟；禁止超过必要范围的固定 `sleep` |

### 1.4 mock 边界（FR-0103）

| 允许 mock 的对象 | 禁止 mock 的对象 |
| --- | --- |
| 网络 / Tushare / qmt-gateway / SMTP / 钉钉 | 被测函数或类主体 |
| 时钟（freezegun、FakeClock） | 被测模块的内部 helper |
| 文件系统（`tmp_path`）、SQLite / Parquet | 上游 fixture 的数据生成器 |
| 进程 / 线程 / 调度 | 被测 DTO 的 `__init__` |
| 下游 port / service（结构化 Protocol doubles） | 被测 Protocol 自身的存在性 |

---

## 2. 覆盖率契约

### 2.1 `coverage-waivers.json` schema（FR-0102 AC-4 / AC-5）

```json
{
  "spec_id": "v0.2-003-coverage",
  "description": "Temporary coverage waivers. Empty by default; every entry must be reviewed and linked to a follow-up issue.",
  "waivers": [
    {
      "module": "quantide/<package>/<file>.py",
      "current_coverage": 73.5,
      "reason": "FR-XXXX gap: <one-sentence description>",
      "expires_at": "2026-07-24",
      "followup_issue": "https://github.com/zillionare/millionaire/issues/123"
    }
  ]
}
```

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `module` | string | 必须等于 `coverage.json.files` 中某条 `quantide/**/*.py` 路径 |
| `current_coverage` | float | 0~100，提交豁免时的实测值 |
| `reason` | string | 单句，引用具体 FR gap 或 `dead-or-marker` 分类 |
| `expires_at` | string (ISO date) | 必须 ≤ today + 14 天；过期 → checker 失败 |
| `followup_issue` | string | 非空 GitHub issue URL（`https://github.com/zillionare/millionaire/issues/NN`） |

> 默认 `waivers: []`；任何非零条目必须在 PR 评审中审查（FR-0102 AC-5）。FR-0102 末段禁止用 `omit` / 扩大 `exclude_lines` / 批量 `pragma: no cover` 实现豁免。

### 2.2 `coverage.json` schema（pytest-cov 输出）

| 路径 | 类型 | 测试断言 |
| --- | --- | --- |
| `totals.percent_covered` | float | `>= 95`（NFR-0010 AC-1） |
| `totals.num_statements` | int | 与首次全绿运行一致（NFR-0020 AC-2） |
| `totals.covered_lines` | int | 同上 |
| `files["quantide/<path>"].summary.percent_covered` | float | `>= 80` 或在合法未过期 waiver 内（FR-0102 AC-1/AC-4） |
| `files["quantide/<path>"].summary.num_statements` | int | `> 0` 才纳入逐文件检查（FR-0102 AC-2）；`0` 自然跳过 |
| `files["quantide/<path>"].missing_lines` | array | 调试用；CI 不直接断言 |
| `meta.branch_coverage` | bool | 应为 true（branch coverage 开启） |

**checker 行为表**

| 输入 | 期望 exit |
| --- | --- |
| overall=96% + 一个 79.99% 非豁免文件 | 非 0（AC-FR-0102-1） |
| 所有 `quantide/**/*.py` 且 `num_statements>0` ≥80% | 0（AC-FR-0102-2） |
| 含 1 条 import/re-export 的 `__init__.py` <80% | 非 0（AC-FR-0102-3） |
| 合法未过期 waiver 覆盖某 <80% 文件 | 0（AC-FR-0102-4） |
| waiver 缺字段 / 已过期 / 模块不存在 / `followup_issue` 为空 | 非 0（AC-FR-0102-4） |
| `coverage.json` 缺失生产模块 | 非 0（NFR-0010 AC-2） |

### 2.3 入口命令契约

```bash
poetry run pytest tests/unit \
  --cov=quantide \
  --cov-fail-under=95 \
  --cov-report=term-missing \
  --cov-report=json:coverage.json \
  --cov-report=html:htmlcov
python -m tests.unit._checkers.per_file_coverage coverage.json coverage-waivers.json
```

- 第一行 exit 0 当且仅当 unit 测试 0 failed/0 errors 且 `totals.percent_covered >= 95`（FR-0101 AC-1/AC-2）。
- 第二行 exit 0 当且仅当逐文件 ≥80% 或存在合法未过期 waiver。
- CI 中两行**串联**，任一非 0 都使 workflow 失败（FR-0601 AC-3/AC-4）。

---

## 3. 测试接口契约

每个 FR 家族给出统一的测试接口模板。Devon 按家族复用模板，仅替换 fixture 名与 AC 锚点。

### 3.1 FR-01xx 基础设施（`tests/unit/_infra/`）

| 测试文件 | 主要 fixture | 断言锚点 | Mock 边界 |
| --- | --- | --- | --- |
| `test_pyproject_pytest_config.py` | 无（解析 `pyproject.toml`） | FR-0101 AC-1..AC-5 | 无（仅文件解析） |
| `test_per_file_coverage.py` | `coverage_synth` | FR-0102 AC-1..AC-5 | synthetic JSON 文件系统 |
| `test_isolation_and_determinism.py` | `env` + 子 fixture monkeypatch | FR-0104 AC-1..AC-4；NFR-0020 AC-1..AC-4 | env、time、scheduler |
| `test_contract_source_registry.py` | `pytester` 或 AST 遍历 | FR-0001 AC-1..AC-4 | 文件系统 |
| `test_unit_coverage_workflow.py` | YAML 合成 fixture | FR-0601 AC-1..AC-5；FR-0602 AC-1..AC-3 | workflow 文件 |

### 3.2 FR-02xx core

| 测试家族 | 主要 fixture | 断言锚点 | Mock 边界 |
| --- | --- | --- | --- |
| `core/domain/test_events.py` | `event_factory` | FR-0201 AC-1..AC-4 | 无 |
| `core/runtime/test_clock_bridge.py` | `FakeClock` + 交易日历 sentinel | FR-0202 AC-1..AC-4 | 时间 |
| `core/runtime/test_gateway_client.py` | `httpx_mock_router` | FR-0203 AC-1..AC-3 | qmt-gateway HTTP |
| `core/runtime/test_gateway_broker.py` | `httpx_mock_router` + `broker_port_double` | FR-0203 AC-4..AC-5；FR-0204 AC-4..AC-5 | qmt-gateway HTTP + 内部 broker |
| `core/runtime/test_modes_bootstrap.py` | `FakeClock` + 临时 SQLite + `broker_port_double` | FR-0204 AC-1..AC-3, AC-6 | DB / clock / broker |
| `core/runtime/test_port_broker.py` | `broker_port_double` | FR-0204 AC-4..AC-6 | broker port |
| `core/strategy/test_base_and_risk.py` | `broker_port_double` + `data_fetcher_port_double` | FR-0205 AC-1..AC-3；FR-0207 AC-1..AC-4 | broker / data |
| `core/strategy/test_discovery.py` | 临时策略目录 + `broker_port_double` | FR-0205 AC-4 | 文件系统 |
| `core/strategy/test_scheduler.py` | `FakeClock` | FR-0205 AC-5..AC-6 | scheduler |
| `core/strategy/test_message.py` | `broker_port_double` | FR-0206 AC-2..AC-3 | 无 |
| `core/strategy/test_sdk_metadata.py` | `calendar`/`stock` fixture | FR-0206 AC-4 | SDK 边界 |
| `core/strategy/test_helpers.py` | `event_factory` | FR-0206 AC-5 | 无 |
| `core/ports/test_protocol_structural.py` | `broker_port_double` 等结构化替身 | FR-0207 AC-1..AC-5 | 无（结构化替身即隔离） |

### 3.3 FR-03xx data

| 测试家族 | 主要 fixture | 断言锚点 | Mock 边界 |
| --- | --- | --- | --- |
| `data/fetchers/test_tushare.py` | Tushare SDK 方法级 `pytest-mock` | FR-0301 AC-1..AC-3 | SDK 调用 |
| `data/fetchers/test_registry.py` | `data_fetcher_port_double` | FR-0301 AC-4 | 无 |
| `data/models/test_calendar.py` | `calendar` fixture | FR-0302 AC-1 | 时间 |
| `data/models/test_stocks.py` | `st_info`/`universe` fixture | FR-0302 AC-2 | 无 |
| `data/models/test_daily_bars.py` | `daily_bars` + `adj_factor` fixture | FR-0302 AC-3 | 无 |
| `data/models/test_app_state.py` | env | FR-0302 AC-4 | 文件系统 |
| `data/models/test_index_bars.py` | 临时 `tmp_path` parquet | FR-0302 AC-5 | 无（仅校验 schema） |
| `data/models/test_entities_strategy_config.py` | env | FR-0302 AC-6 | 无 |
| `data/stores/test_parquet_base.py` | `tmp_path` parquet 目录 | FR-0303 AC-1..AC-2 | 文件系统 |
| `data/stores/test_index_bars_store.py` | `tmp_path` parquet 目录 | FR-0303 AC-3..AC-4 | 文件系统 |
| `data/test_sqlite.py` | `sqlite_in_memory` 或 `tmp_path` | FR-0303 AC-5..AC-6 | DB |
| `data/test_helper.py` | 独立 OHLC fixture + 手算期望 | FR-0304 AC-1..AC-2 | 无 |
| `data/utils/test_resampler.py` | OHLC fixture | FR-0304 AC-3..AC-4 | 无 |

### 3.4 FR-04xx service

| 测试家族 | 主要 fixture | 断言锚点 | Mock 边界 |
| --- | --- | --- | --- |
| `service/test_strategy_runtime.py` | `lifecycle_recorder` + `broker_port_double` | FR-0401 AC-5 | broker / clock |
| `service/test_discovery_service.py` | 临时 builtin+user 目录 + 缓存 | FR-0401 AC-1..AC-3 | 文件系统 |
| `service/test_registry.py` | `broker_port_double` | FR-0401 AC-4 | broker |
| `service/test_runner.py` | `lifecycle_recorder` + 临时 SQLite + `data_fetcher_port_double` | FR-0401 AC-6 | DB / data / broker |
| `service/test_abstract_broker.py` | 内部 fake broker | FR-0402 AC-1 | 内部 broker |
| `service/test_backtest_broker.py` | 独立 `market_data` + clock + `tmp_path` SQLite | FR-0402 AC-2..AC-6 | DB / clock / market |
| `service/test_sim_broker.py` | paper 行情 + clock + `tmp_path` SQLite | FR-0402 AC-2..AC-6 | DB / clock / market |
| `service/test_datafeed.py` | `market_data_port_double` + 历史 store | FR-0403 AC-1..AC-2 | market data |
| `service/test_livequote.py` | websocket payload fixture + `market_data_port_double` | FR-0403 AC-3..AC-6 | websocket |
| `service/test_backtest_logs.py` | `tmp_path` + log fixture | FR-0404 AC-1 | 文件系统 |
| `service/test_grid_search.py` | 参数网格 fixture | FR-0404 AC-2 | 无 |
| `service/test_init_wizard.py` | `httpx_mock_router` + 临时 app config | FR-0404 AC-3 | HTTP / 文件系统 |
| `service/test_metrics.py` | returns/trades fixture + 手算 | FR-0404 AC-4 | 无 |
| `service/test_trade_lightning.py` | 价格缓存 fixture | FR-0404 AC-5 | broker |
| `service/test_triple_barrier.py` | F-TB-1~5 fixture | FR-0404 AC-6 | 无 |

### 3.5 FR-05xx web

| 测试家族 | 主要 fixture | 断言锚点 | Mock 边界 |
| --- | --- | --- | --- |
| `web/components/analysis/test_kline_chart.py` | chart id / OHLCV / periods fixture | FR-0501 AC-1..AC-2 | 无 |
| `web/components/analysis/test_stock_list.py` | stocks / selected_symbol fixture | FR-0501 AC-3..AC-4 | 无 |
| `web/components/analysis/test_chart_specs.py` | equity/drawdown/heatmap fixture | FR-0501 AC-5 | 无 |
| `web/components/test_common.py` | nav/unread/recent fixture | FR-0502 AC-1..AC-5 | 无 |
| `web/layouts/test_main_layout.py` | `create_app_isolated` + HTMX header | FR-0502 AC-5 | 服务/DB |
| `web/pages/test_*_pages.py` | `create_app_isolated` + service/registry/port doubles + HTMX header | FR-0503 AC-1..AC-6 | 下游服务 |
| `web/auth/test_login_logout_password.py` | `create_app_isolated` + session fixture | FR-0504 AC-1..AC-3 | DB / session |
| `web/auth/test_legacy_routes.py` | `create_app_isolated` | FR-0504 AC-3（characterization） | DB |
| `web/apis/test_*_apis.py` | `create_app_isolated` + broker/analysis doubles | FR-0504 AC-4 | 下游服务 |
| `web/middleware/test_*_middleware.py` | `create_app_isolated` + session / registry fixture | FR-0504 AC-5..AC-6 | DB / session |
| `web/test_cross_cutting.py` | env | FR-0505 AC-1..AC-5 | 文件系统 / 浏览器存储 |
| `web/services/test_dtos_and_pure.py` | DTO fixture | FR-0505 AC-1 | 无 |

> 已 100% 覆盖的 web 模块必须保留等价行为测试；允许重构测试，不允许只删测试（FR-0502 AC-1 末句、AC-FR-0505-1）。

### 3.6 FR-06xx CI

| 测试文件 | 主要 fixture | 断言锚点 |
| --- | --- | --- |
| `tests/unit/_infra/test_unit_coverage_workflow.py` | YAML 合成 fixture（negative case 注入 `continue-on-error`、`3.11` matrix 等） | FR-0601 AC-1..AC-5；FR-0602 AC-1..AC-3 |

### 3.7 FR-07xx notify / strategies / config / app

| 测试家族 | 主要 fixture | 断言锚点 | Mock 边界 |
| --- | --- | --- | --- |
| `notify/test_mail.py` | `aiosmtplib_fake` | FR-0701 AC-1..AC-2 | SMTP |
| `notify/test_dingtalk.py` | `httpx_mock_router` + 时间/secret fixture | FR-0701 AC-3..AC-4 | HTTP |
| `notify/test_market_helpers.py` | 001-FR-485 市场规则 fixture | FR-0701 AC-5 | 无 |
| `strategies/test_dual_ma.py` | `broker_port_double` + `data_fetcher_port_double` | FR-0702 AC-1..AC-2 | broker / data |
| `strategies/test_pullback.py` | 同上 + 时间窗口 fixture | FR-0702 AC-3..AC-4 | broker / data / 时钟 |
| `strategies/test_cost_stop.py` | 成本基准 fixture | FR-0702 AC-5..AC-6 | broker |
| `config/test_config.py` | env + monkeypatch | FR-0703 AC-1 | env |
| `config/test_dev_stub.py` | fake process / server | FR-0703 AC-2 | 进程 / 端口 |
| `app/test_app_factory.py` | `create_app_isolated` + 临时 app config | FR-0703 AC-3..AC-6 | DB / session / PID |

---

## 4. CI 接口契约

### 4.1 `.github/workflows/unit-coverage.yml` schema（FR-0601 / FR-0602）

| 字段 | 必填 | 约束 |
| --- | --- | --- |
| `name` | 是 | 固定 `unit-coverage` |
| `on.push.branches` | 是 | 包含 `main`、`releases/**` |
| `on.pull_request.branches` | 是 | 包含 `main`、`releases/**` |
| `jobs.unit-coverage.runs-on` | 是 | `ubuntu-latest`（与现有 louke-ci 一致） |
| `jobs.unit-coverage.strategy.matrix.python` | 是 | `>=3.13,<4.0`；不得复用 `dev.yml` 的 `3.8~3.11` |
| `jobs.unit-coverage.steps[].uses: actions/checkout@v4` | 是 | — |
| `jobs.unit-coverage.steps[].uses: actions/setup-python@v5` | 是 | `python-version: ${{ matrix.python }}` |
| `jobs.unit-coverage.steps[].run` (install) | 是 | 安装 test dependency group（含 pytest/pytest-cov/pytest-asyncio/freezegun/respx/httpx/aiosmtplib） |
| `jobs.unit-coverage.steps[].run` (pytest) | 是 | FR-0101 规范命令；env 设隔离 `HOME/XDG_CONFIG_HOME/QUANTIDE_*` |
| `jobs.unit-coverage.steps[].run` (checker) | 是 | 调用 FR-0102 checker；解析 `coverage.json` |
| `jobs.unit-coverage.steps[].uses: actions/upload-artifact@v4` | 是 | 上传 `coverage.json`、`htmlcov/`；`retention-days: 30`；失败路径使用 `if: always()` 但**不影响 job 终态**（FR-0602 AC-2） |
| 主门禁步骤 `continue-on-error` | 否 | 不得为 `true`（FR-0601 AC-5、NFR-0010 AC-4） |

### 4.2 workflow 验收矩阵

| 输入扰动 | 期望 job 结果 |
| --- | --- |
| 注入一条 failing test | 失败（FR-0601 AC-3） |
| 把 `--cov-fail-under` 改为 94.99 | 失败（FR-0601 AC-3） |
| 把某生产文件降到 79% | checker 步骤失败（FR-0601 AC-4） |
| 加一条合法未过期 waiver 覆盖该文件 | 通过（FR-0102 AC-4） |
| waiver 过期 | 失败（FR-0601 AC-4） |
| matrix 改为 `3.8` | 失败（FR-0601 AC-1） |
| 主步骤加 `continue-on-error: true` | 失败（FR-0601 AC-5） |
| artifact 步骤删除 | 失败（FR-0602 AC-1） |

### 4.3 与现有 CI 的关系

- `.github/workflows/unit-coverage.yml` 是 v0.2 的单元测试与覆盖率门禁（FR-0601）。
- 现有 `.github/workflows/louke-ci.yml`（或同义名）继续作为 smoke / lint / typecheck 流水线，与 unit-coverage 并存，不互相替代（FR-0601 AC-5）。
- `.github/workflows/dev.yml` 中的 Python 3.8~3.11 matrix 不再被 v0.2 门禁采纳（FR-0601 AC-1 末段）。

---

## 5. AC → 接口出口闭环

| FR/NFR 家族 | 验收出口 |
| --- | --- |
| FR-0001 / FR-01xx | `coverage.json` schema + `_infra/test_contract_source_registry.py` 报告 + `coverage-waivers.json` 字段校验 |
| FR-02xx / FR-03xx / FR-04xx / FR-07xx | `_checkers/per_file_coverage.py` exit code + 单测 docstring FR/AC 锚点 |
| FR-05xx | FastHTML `TestClient` 返回的 HTML fragment / status / header / body |
| FR-0601 / FR-0602 | workflow YAML + GitHub Actions 运行日志 + artifact 上传结果 |
| NFR-0010 | `coverage.json.totals.percent_covered` + 逐文件 checker exit |
| NFR-0020 | 重复运行 totals 不变；无未关闭资源；`tmp_path` 干净 |
| NFR-0030 | 测试文件新增数量 + 断言类型分布 + diff 审查 |