# Millionaire Coverage — Test Plan (M-TESTPLAN, Phase 1)

- **Spec ID**: v0.2-003-coverage
- **Spec source**: [spec.md](./spec.md) · [acceptance.md](./acceptance.md) · [story.md](./story.md)
- **Upstream contracts**: [v0.2-001 spec/interfaces/acceptance](../v0.2-001-strategy-framework/) · [v0.2-002 spec/interfaces/acceptance](../v0.2-002-ui/)
- **Framework binding**: `pytest` per `.louke/project/project.toml [meta].test_framework`
- **Target**: 33 FR/NFR · 166 ACs · ≥95% overall statement/line coverage (NFR-0010) · ≥80% per non-waived `quantide/**/*.py` with `num_statements>0` (FR-0102)

This plan is derived **strictly** from spec FR-0001 contract-source priority: v0.2-001/002 → interfaces → story → current public behavior. Tests do not invent behavior; conflicts are flagged `implementation-defect` and the upstream value is asserted.

---

## §1. Test scope & strategy

**In scope**

- All 33 FR/NFR across spec.md (FR-0001, FR-0101–0104, FR-0201–0207, FR-0301–0304, FR-0401–0404, FR-0501–0505, FR-0601–0602, FR-0701–0703, NFR-0010, NFR-0020, NFR-0030) and the 166 ACs in acceptance.md.
- `quantide/` production Python tree (≥1 statement per file), `tests/unit/`, `pyproject.toml` (`[tool.pytest.ini_options]`, `[tool.coverage.run]`, `[tool.coverage.report]`), per-file coverage checker, and the GitHub Actions unit-coverage job.
- Contract tests derived from `interfaces.md` §2–§6 of v0.2-001 and §1–§6 of v0.2-002.

**Out of scope** (defers to other agents / phases)

- UI snapshot testing, visual regression, accessibility automation (002 NFR coverage is assertion-based, not browser-driven).
- Performance benchmarks, load tests, async-throughput tests.
- Real-network E2E (qmt-gateway, Tushare, SMTP, DingTalk/WeChat) — owned by **Shield M-E2E** in Phase 2.
- Mutation testing (cosmic-ray / mutmut) — deferred; NFR-0030 already enforces dual-path assertions per module so mutation coverage adds little signal at v0.2 launch.
- 001/002 business-rule invention — no new CRUD, serialization, or state-machine APIs asserted that lack an upstream reference.

**Test pyramid**

| Layer | Share | Targets |
|---|---|---|
| Unit (pure functions, dataclass invariants, port contracts, schema round-trip) | ~80% | Every FR-02/03/04/05/07 family; FR-01xx infrastructure. |
| Integration / contract (ports → adapters, FastHTML TestClient round-trip, SQLite/Parquet on tmp_path, gateway/broker round-trip) | ~15% | FR-0203 (GatewayBrokerAdapter), FR-0204 (RuntimeBootstrap), FR-0303 (SQLite cascade), FR-0402 (Broker → BrokerPort), FR-0503 (page → handler), FR-0703 (create_app). |
| End-to-end (handed off to Shield M-E2E, Phase 2) | ~5% | Boot → tick → order → fill, init-wizard → login → dashboard, push-event SSE reconnection. |

**Coverage gates** (NFR-0010 + FR-0102)

- Overall `coverage.json.totals.percent_covered ≥ 95`, computed from a **fully green** `tests/unit` run (FR-0101 AC-2/AC-3).
- Per-file: every `quantide/**/*.py` with `num_statements > 0` ≥ 80%, or has a valid unexpired entry in `coverage-waivers.json`.
- Empty / 0-statement files are excluded by the checker (FR-0102 AC-2); `__init__.py` files with import/re-export statements are NOT empty (FR-0102 AC-3).

---

## §2. Test framework & tools

| Concern | Tool | Why |
|---|---|---|
| Test runner | `pytest ≥ 9.0.2` | Already pinned in `pyproject.toml` line 97–98 (`asyncio_mode = "auto"`) and declared in `project.toml [meta].test_framework`. |
| Async | `pytest-asyncio ≥ 1.3.0` | Already pinned; auto mode covers `RuntimeBootstrap`, scheduler, message hub, LiveQuote stream. |
| Coverage | `pytest-cov ≥ 7.0.0` | Branch coverage ON (`--cov-branch`); emits `coverage.json` for FR-0102 checker and `htmlcov/` for FR-0602. |
| Time control | `freezegun` | Wall-clock isolation for SystemClockAdapter, scheduler tick windows, Triple Barrier date math, market open/close helpers. |
| HTTP mocking | `respx` + `httpx` | Mock qmt-gateway login/poll endpoints in `GatewayClient`/`GatewayBrokerAdapter`; mock Tushare-equivalent HTTP in fetchers when the boundary is HTTP rather than the SDK shim. |
| General mocking | `pytest-mock` (`mocker` fixture) | For port-level doubles where `respx` is inappropriate (e.g., `MarketDataPort.stream` async iterator, `BrokerPort` DTO mutation guards). |
| Property tests | `hypothesis` (limited) | Only for domain-event boundary properties (e.g., mutable-default isolation of `ErrorEvent.details`; broker round-trip preserving `extra` JSON). NOT for whole modules — runs would explode the time budget. |
| Per-file checker | Custom script under `tests/unit/_checkers/` | Reads `coverage.json`, applies FR-0102 rules, exits non-zero on violation. The checker itself is unit-tested (AC-FR-0102-01..05). |
| CI | GitHub Actions | New `unit-coverage.yml` workflow (FR-0601). |

`pyproject.toml` is the **only** source of pytest/coverage config (FR-0101 AC-5). No `pytest.ini`/`setup.cfg`. `asyncio_mode = "auto"` is preserved.

---

## §3. Coverage strategy per module

Coverage measurement comes from the same green run that produces the report. `coverage-waivers.json` starts with `waivers: []`; any entry requires `module`, `current_coverage`, `reason`, `expires_at`, `followup_issue` (FR-0102 AC-4).

| # | Group | Production path | Target | Test files | Waivers (current) |
|---|---|---|---|---|---|
| 1 | `core/domain` | `quantide/core/domain/*.py` (events, value objects, enums) | **95%** | `tests/unit/quantide/core/domain/` | none |
| 2 | `core/runtime` | `quantide/core/runtime/*.py` (clock_bridge, gateway_client, gateway_broker, modes, port_broker) | 90% | `tests/unit/quantide/core/runtime/` | none |
| 3 | `core/strategy` + ports | `quantide/core/strategy.py`, `core/strategy_discovery.py`, `core/scheduler.py`, `core/message.py`, `core/sdk_metadata.py`, `core/enums.py`, `core/errors.py`, `quantide/core/ports/*.py` | 90% | `tests/unit/quantide/core/strategy/` and `tests/unit/quantide/core/ports/` | none |
| 4 | `data/` | `quantide/data/fetchers/*.py`, `quantide/data/models/*.py`, `quantide/data/stores/*.py`, `quantide/data/sqlite.py`, `quantide/data/helper.py`, `quantide/data/utils/resampler.py` | 90% | `tests/unit/quantide/data/` | none |
| 5 | `service/` | `quantide/service/*.py` (strategy_runtime, discovery, registry, runner, abstract_broker, backtest_broker, sim_broker, datafeed, livequote, backtest_logs, grid_search, init_wizard, metrics, trade_lightning, triple_barrier, helpers) | 90% | `tests/unit/quantide/service/` | none |
| 6 | `web/` | `quantide/web/components/**`, `layouts/`, `pages/`, `auth/`, `apis/`, `middleware/**`, `services/` | 90% | `tests/unit/quantide/web/` | none |
| 7 | `notify/` + `strategies/` | `quantide/notify/mail.py`, `notify/dingtalk.py`, `notify/__init__.py` (market helpers), `quantide/strategies/example/*.py` (DualMA, PullbackSell, CostStopLoss) | 85% | `tests/unit/quantide/notify/`, `tests/unit/quantide/strategies/` | none |
| 8 | `config/` + `app/` + bootstrap | `quantide/config/*.py`, `quantide/app.py`, `quantide/app_factory.py` | 90% | `tests/unit/quantide/config/`, `tests/unit/quantide/app/` | none |

**Floors**: per-file ≥ 80% (NFR-0010 AC-2/AC-3). Overall ≥ 95% (NFR-0010 AC-1). The two are checked independently — `--cov-fail-under=80` does NOT replace per-file verification (FR-0102).

---

## §4. Test patterns per FR family

The matrix below locks the **technique** per FR family so Devon (M-DEV) writes tests that hit the right boundary.

- **FR-0001** (contract source & conflict resolution). Each test module docstring / test docstring / line-anchored comment must cite at least one upstream FR/AC or this spec's FR/AC. A unit test under `tests/unit/_contract_registry/` enumerates the FR→module→test mapping; conflicts are tagged `implementation-defect`. Test fixtures (manifest, universe, calendar, daily_bars, adj_factor, st_info, limit_price) carry expected values that were computed independently — never by calling the production code under test (AC-FR-0001-2, NFR-0030 AC-3).
- **FR-0101** (pytest config). `tests/unit/_infra/test_pyproject_pytest_config.py` parses `pyproject.toml` and asserts `[tool.pytest.ini_options]` includes the canonical command, `asyncio_mode = "auto"`, and the canonical coverage source = `quantide`. The test fails if any of `pytest.ini`, `setup.cfg`, or `tox.ini` exists at the project root.
- **FR-0102** (per-file coverage + waivers). `tests/unit/_infra/test_per_file_coverage.py` runs the checker against synthetic `coverage.json` fixtures (AC-FR-0102-01..05): overall 96% with a 79.99% un-waived file → exit non-zero; all-good → exit 0; missing fields/expired/empty `followup_issue` → exit non-zero.
- **FR-0103** (mock boundary). `pytest-mock` for `BrokerPort`/`MarketDataPort`/`DataFetcherPort`/`ClockPort` doubles; `respx` for `GatewayClient` HTTP boundary, `aiosmtplib` fake for `send_mail`, `aiohttp`/`httpx` mock for DingTalk. App tests construct `create_app(app_config_dir=tmp_path, enforce_single_instance=False)` (AC-FR-0103-3). Patches never target the function under test (NFR-0030 AC-3).
- **FR-0104** (isolation & determinism). Per-test fixture scope only; `tmp_path` for every filesystem; `monkeypatch.setenv` and `monkeypatch.delenv` for env; `freezegun` for `BacktestClockAdapter` start time and `BacktestRunner` ranges. Teardown closes `httpx.AsyncClient`, APScheduler instances, sqlite connections, websocket tasks. A random-order test (`pytest --random-order`) rerun must yield identical totals (NFR-0020 AC-2).
- **FR-020x** (core). Pure-Python tests; `FakeClock` (freezegun-backed `ClockPort`) for runtime; structured doubles for ports; `isinstance`-style Protocol conformance via `runtime_checkable` rather than `isinstance`-on-ABC (AC-FR-0207-5).
- **FR-030x** (data). Per-test in-memory or `tmp_path` SQLite; `respx` for HTTP-boundary fetchers; `tushare` SDK is faked at its **method** boundary (e.g., `mocker.patch("tushare.pro_api.pro.trade_cal", return_value=df)`) — the SDK is treated as an external dependency (AC-FR-0301-1).
- **FR-040x** (service). Port-level doubles for broker/data/quote dependencies; per-test fresh `SQLiteDB(tmp_path / "test.db")`; `BacktestRunner` tests inject `BacktestClockAdapter` and check the `on_start → on_day_open → on_bar → on_day_close → on_stop` sequence via a `lifecycle_recorder` fixture.
- **FR-050x** (web). `fastapi.testclient.TestClient(create_app(...))`; component unit tests introspect FastHTML `__html__()` strings (or `repr()` if FastHTML); auth/middleware tests post to `/login` then assert `303` and session cookie. Htmx requests send `HX-Request: true` and expect fragment-shaped bodies (AC-FR-0503-5).
- **FR-060x** (CI). `tests/unit/_infra/test_unit_coverage_workflow.py` parses `.github/workflows/unit-coverage.yml`, asserts: Python matrix ≥ 3.13, FR-0101 canonical command present, FR-0102 checker invoked, no `continue-on-error: true` on the coverage gate steps, `actions/upload-artifact` with `retention-days: 30`. Uses synthetic YAML fixtures for negative cases.
- **FR-070x** (notify / strategy / config). `aiosmtplib` fake for SMTP, `respx` for DingTalk HTTP; builtin strategy tests load `DualMAStrategy` / `PullbackSellStrategy` / `CostStopLossStrategy` from `quantide/strategies/example/`, inject a fake broker + fake `get_bars`, and assert order calls + `default_config`. `create_app` tests always use `tmp_path` and a fresh `enforce_single_instance=False` call.

**Minimum test-file inventory per family** (Devon must create at least these; each file's module docstring cites the FR/AC anchor; `test_contract_source_registry.py` enforces it). Files already in `tests/unit/quantide/` may be extended rather than replaced.

- FR-0001/01xx infra: `tests/unit/_infra/test_contract_source_registry.py`, `test_pyproject_pytest_config.py`, `test_per_file_coverage.py`, `test_isolation_and_determinism.py`, `test_unit_coverage_workflow.py`.
- FR-0201–0207 core: `tests/unit/quantide/core/domain/{test_events,test_enums,test_errors}.py`, `runtime/{test_clock_bridge,test_gateway_client,test_gateway_broker,test_modes_bootstrap,test_port_broker}.py`, `strategy/{test_base_and_risk,test_discovery,test_scheduler,test_message,test_sdk_metadata,test_helpers}.py`, `ports/test_protocol_structural.py`.
- FR-0301–0304 data: `tests/unit/quantide/data/fetchers/{test_tushare,test_registry}.py`, `models/{test_calendar,test_stocks,test_daily_bars,test_app_state,test_index_bars,test_entities_strategy_config}.py`, `stores/{test_parquet_base,test_index_bars_store}.py`, `test_sqlite.py`, `test_helper.py`, `utils/test_resampler.py`.
- FR-0401–0404 service: `tests/unit/quantide/service/{test_strategy_runtime,test_discovery_service,test_registry,test_runner,test_abstract_broker,test_backtest_broker,test_sim_broker,test_datafeed,test_livequote,test_backtest_logs,test_grid_search,test_init_wizard,test_metrics,test_trade_lightning,test_triple_barrier}.py`.
- FR-0501–0505 web: `components/analysis/{test_kline_chart,test_stock_list,test_chart_specs}.py`, `components/test_common.py`, `layouts/test_main_layout.py`, `pages/{test_strategy_pages,test_account_pages,test_trade_pages,test_history_pages,test_system_pages,test_init_wizard}.py`, `auth/{test_login_logout_password,test_legacy_routes}.py`, `apis/{test_broker_apis,test_analysis_apis}.py`, `middleware/{test_init_feature_auth,test_broker_registry}.py`, `test_cross_cutting.py`, `services/test_dtos_and_pure.py`.
- FR-0601–0602 CI: `tests/unit/_infra/test_unit_coverage_workflow.py` + new `.github/workflows/unit-coverage.yml`.
- FR-0701–0703 notify/strategy/config/app: `tests/unit/quantide/notify/{test_mail,test_dingtalk,test_market_helpers}.py`, `strategies/{test_dual_ma,test_pullback,test_cost_stop}.py`, `config/{test_config,test_dev_stub}.py`, `app/test_app_factory.py`.

---

## §5. Test data & fixtures

The following fixtures live in `tests/unit/conftest.py` (top-level) and per-directory `conftest.py` files. They are **shared** across the suite; per-test variants use smaller `tmp_path`-scoped data.

- **`env`** (session- or module-scoped): versioned bundle of `manifest`, `universe`, `calendar`, `daily_bars`, `adj_factor`, `st_info`, `limit_price` from `tests/assets/unit/ground_truth/`. Manifest version is exposed and asserted in FR-0103 AC-1.
- **`FakeClock`** (function-scoped): implements `ClockPort` (`now`/`set_now`/`iter_frames`). Backed by freezegun where wall-clock control is needed, and by an injected iterable for `iter_frames` (FR-0202 AC-3).
- **`sqlite_in_memory`** (function-scoped): per-test `quantide.data.sqlite.SQLiteDB(":memory:")` with the schema bootstrap applied. Cascade test uses a `tmp_path` file instead so delete behaviour can be observed on disk.
- **`httpx_mock_router`** (function-scoped): `respx` router pre-loaded with qmt-gateway login/poll stubs and Tushare HTTP fallbacks. Yielded with `respx.reset` on teardown.
- **`aiosmtplib_fake`** (function-scoped): records outgoing SMTP envelopes; refuses to open sockets.
- **`event_factory`** (function-scoped): produces `MarketEvent` / `QuoteSnapshot` / `OrderEvent` / `TradeEvent` / `ErrorEvent` with stable IDs and timestamps; mutations to one instance's `details`/`extra` must not leak to siblings (FR-0201 AC-3, FR-0207 AC-4).
- **`broker_port_double`** / **`market_data_port_double`** / **`data_fetcher_port_double`** (function-scoped): struct-typed port doubles that satisfy the Protocol structurally. Each implements the seven/three/five methods respectively and records call history for assertions.
- **`create_app_isolated`** (function-scoped): calls `create_app(app_config_dir=tmp_path / "cfg", enforce_single_instance=False)` returning a `TestClient`. Closes DB / scheduler / message hub on teardown.
- **`lifecycle_recorder`** (function-scoped): wraps a strategy under test; records every `on_*` hook call and every broker call with timestamp and argument shape, so FR-0401 AC-6 can assert the exact sequence.
- **`coverage_synth`** (function-scoped): factory that builds synthetic `coverage.json` payloads on `tmp_path` for FR-0102 / FR-0601 tests.

Per-directory `conftest.py` files add module-specific helpers (e.g., `data/conftest.py` provides `parquet_tmp_store`, `web/conftest.py` provides `htmx_client`).

---

## §6. E2E outline (handoff to Shield M-E2E)

Phase 1 only **outlines the contract**; Phase 2 (M-E2E) owns implementation and lives in the host-project repository, NOT in `.louke/`.

**Boundary**

- M-E2E owns: full boot → tick → order → fill flow, init-wizard → login → dashboard, SSE reconnection, dev-stub process lifecycle. Likely test dirs: `tests/e2e/{backtest,live,pages,http_integration}/` (already scaffolded in repo).
- Phase 1 (this plan) provides: the **contract list** of scenarios each E2E suite must cover; **TestClient-based tests in `tests/unit/quantide/web/`** cover the page/handler layer without spawning real processes, so M-E2E focuses on inter-process paths only.

**Contract handed to M-E2E**

| Scenario | Required seeds | Expected observable | Mapping |
|---|---|---|---|
| Boot → live tick → order submit → fill | dev-stub gateway, paper account, Tushare HTTP mock | `/broker/{id}/portfolios` shows `running`, `/broker/portfolios/{id}/status` shows fill count > 0, `orders.filled > 0` in SQLite, `trades` row with correct `qtoid`/`portfolio_id` | FR-0204, FR-0401, FR-0402, AC-FR-0402-* |
| Init-wizard first-run | empty `app_config_dir` in `tmp_path` | `GET /` → 303 `/wizard`, completion → 303 `/login` | FR-0504 AC-1, FR-0703 AC-3/AC-4 |
| B-class degradation (gateway drops) | running live portfolio, dev-stub gateway killed | Yellow banner via SSE, `/trade/live` returns 503 fragment, no portfolio mutation | FR-0180, FR-0505 |
| Push-event reconnection | SSE client reconnects with `Last-Event-ID` | server replays missed `order`/`portfolio` events or sends snapshot | §5 v0.2-002 interfaces, FR-0160 |
| Per-file waiver expiration | `coverage-waivers.json` with one expired entry | FR-0102 checker exits non-zero | FR-0601 AC-4 |

**Out of scope for M-E2E here**: real qmt-gateway binary, real Tushare token, real SMTP delivery — those remain mocked at the same boundary established in §5.

---

## §7. Coverage waivers

`coverage-waivers.json` ships with `waivers: []` (NFR-0010 AC-2, FR-0102 AC-5). Waivers are **explicit list only**; no implicit exclusions via `omit` / `exclude_lines` / `pragma: no cover` are permitted (FR-0102 closing paragraph; NFR-0030 AC-4).

**Required fields per waiver entry**

| Field | Type | Constraint |
|---|---|---|
| `module` | string | Must equal a `quantide/**/*.py` path present in `coverage.json` |
| `current_coverage` | float | Last measured value at time of waiver |
| `reason` | string | Single sentence citing the FR gap or `dead-or-marker` classification |
| `expires_at` | string (ISO date) | Must be ≤ today + 14 days |
| `followup_issue` | string | Must be non-empty GitHub issue URL (e.g., `https://github.com/zillionare/millionaire/issues/NN`) |

**Process** (when Devon needs to add a waiver)

1. Confirm via `rg` that the file has at least one production consumer (FR-0001 AC-4). If zero consumers, classify `dead-or-marker` and route to a separate dead-code decision PR — **do not** waive.
2. Open a follow-up issue in `zillionare/millionaire` describing what tests must be added and why they were deferred.
3. Add the waiver entry with all five fields.
4. The FR-0102 checker will then accept the file for up to 14 days; after expiry, CI fails until either tests are added or the waiver is renewed with a new `expires_at` + `followup_issue`.
5. Signed-off-by recorded in the PR body that adds the waiver.

**Pre-approved budget**: zero waivers at v0.2 launch. Any non-zero entry is reviewed at PR time.

---

## §8. Risks & known gaps

- **`quantide` import path**. The host project currently exposes production under `quantide/`; FR-0101's coverage source is `quantide`. If the package is later renamed, the canonical command and per-file checker must move in lockstep (NFR-0010 AC-4).
- **LiveQuote / BarsFeed**. Real websocket & tick-stream are external; all tests use structured doubles (`httpx_mock_router` + a `MarketDataPort` fake that yields pre-recorded payloads). No `live=true` path is exercised in unit tests — that is M-E2E Phase 2 (FR-0403 AC-5).
- **Notify channels (SMTP / DingTalk / WeChat)**. SMTP via `aiosmtplib_fake`, DingTalk via `respx`, WeChat/IM via stubbed request signer. No real network egress; secret-bearing fields are scrubbed from logged payloads (FR-0701 AC-4 last sentence, FR-0504 AC-5).
- **v0.2-001 issue path migration**. v0.2-001 historically referenced `quantide.core` vs `quantide/core` paths; tests import via the **public** path (FR-0001 AC-4) and never from private underscore modules. If a mismatch is found, the file becomes `implementation-defect`.
- **v0.2-001 interfaces not exhaustive**. The interfaces.md §4 catalog covers schemas (orders/trades/positions/assets/portfolios/strategy_logs/backtest_logs) but does NOT list every method on every model. For models, tests use the model's **own** documented API (FR-0302 AC-1..AC-5) rather than a hypothetical `Model.from_dict/to_dict` union. If Phase 2 surfaces a schema that lacks a unit test, an `interfaces.md` amendment + new AC may be needed — out of scope here.
- **Mutation testing deferred**. NFR-0030 AC-1 enforces dual-path (normal + boundary/failure) assertions per module, which provides most of the mutation signal. If Phase 3 wants strict mutation scores, cosmic-ray must be added with a separate waiver budget.
- **`tmp_path` discipline**. Some modules currently call `Path.home()` or read `QUANTIDE_*` env vars at import time. FR-0104 AC-1/AC-2 plus the env fixture override these; any module that bypasses fixtures must be flagged `implementation-defect` and fixed.
- **Port protocol checks**. NFR-0030 AC-3 forbids mocking the function under test; FR-0207 AC-5 forbids `isinstance(x, BrokerPort)` style assertions. Conftest provides **structural** doubles — Devon's tests must use those, not ad-hoc `MagicMock(spec=...)`.

---

## §9. Handoff to Devon (M-DEV)

Devon's M-DEV pass produces the actual test files. The list below is the **minimum file inventory**; each file must cite the FR/AC anchor in its module docstring.

**Infrastructure (`tests/unit/_infra/`)**

- `conftest.py` — env, sqlite_in_memory, httpx_mock_router, event_factory, broker/market_data/data_fetcher doubles.
- `test_pyproject_pytest_config.py` — FR-0101 AC-1..AC-5.
- `test_per_file_coverage.py` — FR-0102 AC-1..AC-5 (drives `coverage_synth`).
- `test_isolation_and_determinism.py` — FR-0104 AC-1..AC-4; NFR-0020 AC-1..AC-4; NFR-0030 AC-1..AC-5.
- `test_unit_coverage_workflow.py` — FR-0601 AC-1..AC-5; FR-0602 AC-1..AC-3.
- `test_contract_source_registry.py` — FR-0001 AC-1..AC-4 (auto-discovers tests, asserts docstring citations and independent fixtures).

**Domain & runtime (`tests/unit/quantide/core/`)**

- `domain/test_events.py` — FR-0201 AC-1..AC-4.
- `domain/test_enums.py` — FR-0206 AC-1.
- `domain/test_errors.py` — FR-0206 AC-5 (errors + helpers).
- `runtime/test_clock_bridge.py` — FR-0202 AC-1..AC-4.
- `runtime/test_gateway_client.py` — FR-0203 AC-1..AC-3 (uses `httpx_mock_router`).
- `runtime/test_gateway_broker.py` — FR-0203 AC-4..AC-5; FR-0204 AC-4..AC-5.
- `runtime/test_modes_bootstrap.py` — FR-0204 AC-1..AC-3; AC-6.
- `runtime/test_port_broker.py` — FR-0204 AC-4..AC-6.
- `strategy/test_base_and_risk.py` — FR-0205 AC-1..AC-3; FR-0207 AC-1..AC-4.
- `strategy/test_discovery.py` — FR-0205 AC-4.
- `strategy/test_scheduler.py` — FR-0205 AC-5..AC-6.
- `strategy/test_message.py` — FR-0206 AC-2..AC-3.
- `strategy/test_sdk_metadata.py` — FR-0206 AC-4.
- `strategy/test_helpers.py` — FR-0206 AC-5 (notifications/order_execution/risk_events/wizard steps).
- `ports/test_protocol_structural.py` — FR-0207 AC-1..AC-5.

**Data (`tests/unit/quantide/data/`)**

- `fetchers/test_tushare.py` — FR-0301 AC-1..AC-4.
- `fetchers/test_registry.py` — FR-0301 AC-4.
- `models/test_calendar.py` — FR-0302 AC-1.
- `models/test_stocks.py` — FR-0302 AC-2.
- `models/test_daily_bars.py` — FR-0302 AC-3.
- `models/test_app_state.py` — FR-0302 AC-4.
- `models/test_index_bars.py` — FR-0302 AC-5.
- `models/test_entities_strategy_config.py` — FR-0302 AC-6.
- `stores/test_parquet_base.py` — FR-0303 AC-1..AC-2.
- `stores/test_index_bars_store.py` — FR-0303 AC-3..AC-4.
- `test_sqlite.py` — FR-0303 AC-5..AC-6.
- `test_helper.py` — FR-0304 AC-1..AC-2.
- `utils/test_resampler.py` — FR-0304 AC-3..AC-4.

**Service (`tests/unit/quantide/service/`)**

- `test_strategy_runtime.py` — FR-0401 AC-5.
- `test_discovery_service.py` — FR-0401 AC-1..AC-3.
- `test_registry.py` — FR-0401 AC-4.
- `test_runner.py` — FR-0401 AC-6; FR-0402 trade rules via injected runner.
- `test_abstract_broker.py` — FR-0402 AC-1.
- `test_backtest_broker.py` — FR-0402 AC-2..AC-6.
- `test_sim_broker.py` — FR-0402 AC-2..AC-6 (paper partial fills).
- `test_datafeed.py` — FR-0403 AC-1..AC-2.
- `test_livequote.py` — FR-0403 AC-3..AC-6.
- `test_backtest_logs.py` — FR-0404 AC-1.
- `test_grid_search.py` — FR-0404 AC-2.
- `test_init_wizard.py` — FR-0404 AC-3.
- `test_metrics.py` — FR-0404 AC-4.
- `test_trade_lightning.py` — FR-0404 AC-5.
- `test_triple_barrier.py` — FR-0404 AC-6.

**Web (`tests/unit/quantide/web/`)**

- `components/analysis/test_kline_chart.py` — FR-0501 AC-1..AC-2.
- `components/analysis/test_stock_list.py` — FR-0501 AC-3..AC-4.
- `components/analysis/test_chart_specs.py` — FR-0501 AC-5.
- `components/test_common.py` — FR-0502 AC-1..AC-5 (header/sidebar/toast/runtime_params/asset_label).
- `layouts/test_main_layout.py` — FR-0502 AC-5.
- `pages/test_strategy_pages.py` — FR-0503 AC-1..AC-2, AC-5.
- `pages/test_account_pages.py` — FR-0503 AC-2.
- `pages/test_trade_pages.py` — FR-0503 AC-2, AC-5.
- `pages/test_history_pages.py` — FR-0503 AC-2.
- `pages/test_system_pages.py` — FR-0503 AC-3, AC-5.
- `pages/test_init_wizard.py` — FR-0503 AC-4..AC-5.
- `auth/test_login_logout_password.py` — FR-0504 AC-1..AC-3.
- `auth/test_legacy_routes.py` — FR-0504 AC-3 characterization.
- `apis/test_broker_apis.py` — FR-0504 AC-4.
- `apis/test_analysis_apis.py` — FR-0504 AC-4.
- `middleware/test_init_feature_auth.py` — FR-0504 AC-5.
- `middleware/test_broker_registry.py` — FR-0504 AC-6.
- `test_cross_cutting.py` — FR-0505 AC-1..AC-5 (degradation / events / localStorage / NFR helpers).
- `services/test_dtos_and_pure.py` — FR-0505 AC-1.

**Notify / strategies / config / app (`tests/unit/quantide/{notify,strategies,config,app}/`)**

- `notify/test_mail.py` — FR-0701 AC-1..AC-2.
- `notify/test_dingtalk.py` — FR-0701 AC-3..AC-4.
- `notify/test_market_helpers.py` — FR-0701 AC-5.
- `strategies/test_dual_ma.py` — FR-0702 AC-1..AC-2.
- `strategies/test_pullback.py` — FR-0702 AC-3..AC-4.
- `strategies/test_cost_stop.py` — FR-0702 AC-5..AC-6.
- `config/test_config.py` — FR-0703 AC-1.
- `config/test_dev_stub.py` — FR-0703 AC-2.
- `app/test_app_factory.py` — FR-0703 AC-3..AC-6.

**Per-FR traceability** is enforced automatically by `test_contract_source_registry.py` (FR-0001 AC-1): if Devon adds a test file without an upstream citation, that registry test fails.