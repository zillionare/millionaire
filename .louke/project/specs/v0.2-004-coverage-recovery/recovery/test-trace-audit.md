# Test Trace Audit

- Every `tests/**/*.py` module: **240**
- Every AST-discovered test function/method: **1651**
- Static semantic body review; runtime failing/order-dependent status is unverified because full suite was prohibited.

| Module | Role | Functions | Refs | Quality counts | Recommendation |
|---|---|---:|---|---|---|
| `tests/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/assets/unit/scripts/build_env.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/assets/unit/scripts/validate_env.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/conftest.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/backtest/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/backtest/test_dual_ma_accuracy.py` | test-module | 1 | none | {'aligned': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/e2e/backtest/test_fr_011_day_strategy.py` | test-module | 10 | FR-010, FR-011 | {'aligned': 9, 'self-fulfilling': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/calendar/test_fr_014_calendar.py` | test-module | 13 | FR-014 | {'aligned': 12, 'incomplete': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/calendar_v2/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/calendar_v2/test_fr_014_calendar_v2.py` | test-module | 20 | FR-014 | {'aligned': 19, 'incomplete': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/conftest.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/fixtures/combine_real_fixture.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/fixtures/fetch_tushare.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/fixtures/generate_synthetic.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/fixtures/minimal_assets.py` | helper/fixture | 0 | FR-180 | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/http_integration/test_http_broker_api.py` | test-module | 6 | FR-010 | {'aligned': 6} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/live/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/live/test_gateway_accuracy.py` | test-module | 5 | FR-125, FR-360 | {'aligned': 4, 'incomplete': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/pages/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/pages/app.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/paper/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/paper/test_dual_ma_accuracy.py` | test-module | 1 | none | {'aligned': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/e2e/paper/test_fr_115_185_360_e2e.py` | test-module | 7 | AC-FR-115, AC-FR-185, AC-FR-360, FR-115 | {'aligned': 6, 'incomplete': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/paper/test_fr_140_190_trading_rules_e2e.py` | test-module | 11 | AC-FR-140-01, AC-FR-140-02, AC-FR-150-01, AC-FR-150-02 | {'aligned': 9, 'incomplete': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/paper/test_fr_440_450_200_360_e2e.py` | test-module | 11 | AC-FR-100, AC-FR-110, AC-FR-115, AC-FR-125 | {'aligned': 10, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/paper/test_l1_paper_smoke.py` | test-module | 2 | NFR-060 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/risk_strategy/test_fr_013_risk_strategy.py` | test-module | 7 | FR-013, FR-250 | {'aligned': 7} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/risk_strategy/test_fr_013_risk_structure.py` | test-module | 18 | FR-013, FR-013 AC-01, FR-125, FR-250 | {'aligned': 15, 'incomplete': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/securities/test_fr_015_securities.py` | test-module | 12 | FR-015 | {'aligned': 12} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/securities_v2/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/securities_v2/test_fr_015_securities_v2.py` | test-module | 13 | FR-015 | {'aligned': 12, 'incomplete': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/strategy_discovery/test_fr_010_base_strategy.py` | test-module | 10 | FR-010, FR-010 AC-01 | {'aligned': 8, 'self-fulfilling': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/strategy_discovery/test_fr_020_discovery.py` | test-module | 8 | FR-020 | {'aligned': 2, 'self-fulfilling': 6} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/strategy_discovery_v2/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/strategy_discovery_v2/test_fr_020_discovery_v2.py` | test-module | 40 | FR-020 | {'aligned': 18, 'self-fulfilling': 22} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/strategy_example/test_dual_ma.py` | test-module | 2 | none | {'aligned': 2} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/e2e/strategy_v2/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/strategy_v2/test_fr_010_strategy_root.py` | test-module | 27 | FR-010 | {'aligned': 23, 'self-fulfilling': 4} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/support/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/support/gateway_stub.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/support/init_wizard_session.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/support/runtime_factory.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/support/system_settings_session.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/support/test_gateway_stub.py` | test-module | 6 | none | {'aligned': 6} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/e2e/support/test_tushare_stub.py` | test-module | 3 | none | {'aligned': 2, 'incomplete': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/e2e/support/tushare_stub.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/support/virtual_clock.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/test_app_factory_e2e.py` | test-module | 2 | AC-FR0703-03, AC-FR0703-04, AC-FR0703-05, FR-0703 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/test_boot_smoke.py` | test-module | 1 | AC-FR0101-01, AC-FR0101-02, FR-0101 AC-1 | {'aligned': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/test_ci_workflow_e2e.py` | test-module | 4 | AC-FR0102-01, AC-FR0601-01, AC-FR0601-04, AC-FR0601-05 | {'aligned': 4} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/test_coverage_checker_e2e.py` | test-module | 3 | AC-FR-0102-1, AC-FR-0102-2, AC-FR0102-01, AC-FR0102-02 | {'aligned': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/test_gateway.py` | test-module | 3 | AC-FR0180-01, AC-FR0180-03, AC-FR0180-10, AC-FR0340-01 | {'aligned': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/test_isolation_e2e.py` | test-module | 1 | AC-FR0104-04, AC-NFR-0020-2, AC-NFR0020-02, NFR-0020 | {'aligned': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/test_live_smoke.py` | test-module | 1 | AC-FR0340-06, AC-FR0420-01, AC-FR0460-04 | {'aligned': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/test_paper.py` | test-module | 2 | AC-FR0040-01, AC-FR0310-01, AC-FR0320-01, AC-FR0330-01 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/test_smoke.py` | test-module | 2 | AC-FR0080-01, AC-FR0091-01, AC-FR0091-02, AC-FR0110-01 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/three_mode/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/three_mode/test_dual_ma_parity.py` | test-module | 1 | none | {'aligned': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/e2e/web/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/e2e/web/test_dev_stub_mode.py` | test-module | 1 | none | {'self-fulfilling': 1} | **update** — no substantive independent assertion signal in any test body |
| `tests/e2e/web/test_init_wizard_flow.py` | test-module | 4 | none | {'aligned': 4} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/e2e/web/test_init_wizard_tushare.py` | test-module | 1 | none | {'aligned': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/e2e/web/test_system_settings_flow.py` | test-module | 12 | none | {'aligned': 12} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/grid_search_support.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/ground_truth/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/ground_truth/calendar.py` | helper/fixture | 0 | FR-014 | helper | **keep** — mapped references and substantive semantic signals |
| `tests/ground_truth/discovery.py` | helper/fixture | 0 | FR-020 | helper | **keep** — mapped references and substantive semantic signals |
| `tests/ground_truth/stocks.py` | helper/fixture | 0 | FR-015 | helper | **keep** — mapped references and substantive semantic signals |
| `tests/ground_truth/test_purity.py` | test-module | 2 | none | {'aligned': 2} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/_checkers/per_file_coverage.py` | helper/fixture | 0 | FR-0102 | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/_infra/test_coverage_artifact.py` | test-module | 3 | AC-FR-0602-1, AC-FR-0602-2, FR-0602, FR-0602 AC-1 | {'aligned': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/_infra/test_coverage_thresholds.py` | test-module | 2 | AC-NFR-0010-1, AC-NFR-0010-2, NFR-0010 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/_infra/test_isolation_and_determinism.py` | test-module | 2 | AC-NFR-0020-1, AC-NFR0020-3, NFR-0020 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/_infra/test_per_file_coverage.py` | test-module | 5 | AC-FR-0102-1, AC-FR-0102-2, AC-FR-0102-4, AC-FR-0102-5 | {'aligned': 5} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/_infra/test_pyproject_pytest_config.py` | test-module | 5 | FR-0101 AC-1, FR-0101 AC-4, FR-0101 AC-5 | {'aligned': 5} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/_infra/test_unit_coverage_workflow.py` | test-module | 4 | AC-FR-0601-1, AC-FR-0601-5, FR-0601, FR-0601 AC-1 | {'aligned': 4} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/conftest.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/config/test_branding.py` | test-module | 4 | none | {'aligned': 4} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/config/test_fr_0703_config_contracts.py` | test-module | 2 | AC-FR-0703-1, FR-0703 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/config/test_fr_470_install.py` | test-module | 6 | FR-470 | {'aligned': 5, 'incomplete': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/config/test_paths.py` | test-module | 5 | none | {'aligned': 5} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/config/test_settings.py` | test-module | 14 | none | {'aligned': 14} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/core/domain/test_events.py` | test-module | 2 | FR-0201, FR-0201 AC-1, FR-0201 AC-2 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/core/ports/test_protocol_structural.py` | test-module | 2 | FR-0207, FR-0207 AC-1, FR-0207 AC-2 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/core/runtime/test_clock_bridge.py` | test-module | 2 | FR-0202, FR-0202 AC-1, FR-0202 AC-2 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/core/runtime/test_gateway_client.py` | test-module | 2 | FR-0203, FR-0203 AC-1, FR-0203 AC-2 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/core/runtime/test_port_broker.py` | test-module | 2 | FR-0204, FR-0204 AC-4, FR-0204 AC-5 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/core/strategy/test_strategy_discovery.py` | test-module | 2 | FR-0205, FR-0205 AC-1, FR-0205 AC-3 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/core/test_adapter_registry.py` | test-module | 2 | none | {'aligned': 2} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/core/test_foundation_contracts.py` | test-module | 3 | FR-0206, FR-0206 AC-1, FR-0206 AC-4, FR-0206 AC-5 | {'aligned': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/core/test_fr_010_base_strategy_unit.py` | test-module | 15 | FR-010, FR-010 AC-01 | {'aligned': 12, 'incomplete': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/core/test_fr_012_live_strategy.py` | test-module | 6 | FR-012 | {'aligned': 5, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/core/test_gateway_broker_adapter.py` | test-module | 28 | none | {'aligned': 26, 'incomplete': 2} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/core/test_gateway_protocol_contract.py` | test-module | 8 | none | {'aligned': 3, 'incomplete': 5} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/core/test_message.py` | test-module | 11 | none | {'aligned': 9, 'incomplete': 1, 'self-fulfilling': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/core/test_runtime_modes.py` | test-module | 1 | none | {'aligned': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/core/test_sim_broker_market_data.py` | test-module | 2 | none | {'aligned': 2} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/core/test_strategy_runner.py` | test-module | 4 | none | {'aligned': 4} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/core/test_strategy_runtime_manager.py` | test-module | 12 | none | {'aligned': 11, 'self-fulfilling': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/core/test_wizard_steps_v2.py` | test-module | 17 | AC-FR0460-2, FR-0460 | {'aligned': 15, 'import-only': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/fetchers/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/fetchers/test_coverage_fetchers.py` | test-module | 4 | FR-0301 AC-1, FR-0301 AC-2, FR-0301 AC-3, FR-0301 AC-4 | {'aligned': 4} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/fetchers/test_fr_270_280_tushare.py` | test-module | 11 | FR-270, FR-280 | {'aligned': 9, 'incomplete': 1, 'self-fulfilling': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/fetchers/test_fr_300_gateway.py` | test-module | 6 | FR-300 | {'aligned': 5, 'self-fulfilling': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/fetchers/test_registry.py` | test-module | 2 | none | {'aligned': 2} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/data/fetchers/test_tushare.py` | test-module | 8 | none | {'aligned': 8} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/data/models/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/models/test_bars.py` | test-module | 4 | none | {'aligned': 4} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/data/models/test_calendar.py` | test-module | 31 | none | {'aligned': 30, 'import-only': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/data/models/test_coverage_models.py` | test-module | 5 | FR-0302 AC-1, FR-0302 AC-4, FR-0302 AC-5, FR-0302 AC-6 | {'aligned': 4, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/models/test_fr_330_data_query.py` | test-module | 6 | FR-330 | {'aligned': 6} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/models/test_fr_485_security_code.py` | test-module | 6 | FR-485 | {'aligned': 5, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/models/test_stocks.py` | test-module | 8 | none | {'aligned': 8} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/data/services/test_fr_320_integrity.py` | test-module | 6 | FR-320 | {'aligned': 4, 'incomplete': 1, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/stores/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/stores/test_bars.py` | test-module | 4 | none | {'aligned': 3, 'import-only': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/data/stores/test_base.py` | test-module | 16 | none | {'aligned': 16} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/data/stores/test_coverage_stores.py` | test-module | 2 | FR-0303 AC-1, FR-0303 AC-3 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/stores/test_legacy_index_sector_fetch_retirement.py` | test-module | 1 | none | {'incomplete': 1} | **update** — no substantive independent assertion signal in any test body |
| `tests/unit/quantide/data/test_assets_manifest.py` | test-module | 3 | none | {'aligned': 3} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/data/test_coverage_helper.py` | test-module | 3 | FR-0304 AC-1, FR-0304 AC-2 | {'aligned': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/test_coverage_sqlite.py` | test-module | 1 | FR-0303 AC-5 | {'aligned': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/test_fr_290_adjust_limit.py` | test-module | 7 | FR-290 | {'aligned': 1, 'incomplete': 1, 'import-only': 5} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/test_helper.py` | test-module | 4 | none | {'aligned': 4} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/data/test_init_data.py` | test-module | 2 | none | {'aligned': 2} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/data/test_sqlite.py` | test-module | 30 | none | {'aligned': 30} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/data/test_sqlite_market_data_retirement.py` | test-module | 2 | none | {'aligned': 2} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/data/utils/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/utils/test_coverage_resampler.py` | test-module | 2 | FR-0304 AC-3 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/utils/test_fr_480_resampler.py` | test-module | 8 | FR-480 | {'aligned': 7, 'incomplete': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/data/utils/test_fr_484_research_tools.py` | test-module | 7 | FR-484 | {'aligned': 6, 'incomplete': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/notify/test_fr_0701_notify_channels.py` | test-module | 5 | AC-FR-0701-1, AC-FR-0701-2, AC-FR-0701-4, AC-FR-0701-5 | {'aligned': 4, 'incomplete': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/notify/test_fr_481_notification.py` | test-module | 9 | FR-481 | {'aligned': 7, 'incomplete': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/notify/test_mail.py` | test-module | 2 | none | {'aligned': 2} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_abstract_broker.py` | test-module | 0 | none | helper | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_backtest_broker.py` | test-module | 25 | none | {'aligned': 21, 'incomplete': 4} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_backtest_logs.py` | test-module | 4 | none | {'aligned': 4} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_discovery.py` | test-module | 3 | none | {'aligned': 3} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_forming_daily_bars.py` | test-module | 12 | none | {'aligned': 12} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_fr0401_coverage.py` | test-module | 3 | FR-0401, FR-0401 AC-4, FR-0401 AC-5, FR-0401 AC-6 | {'aligned': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr0402_coverage.py` | test-module | 3 | FR-0402, FR-0402 AC-1, FR-0402 AC-6 | {'aligned': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr0403_coverage.py` | test-module | 4 | FR-0403, FR-0403 AC-1, FR-0403 AC-2, FR-0403 AC-3 | {'aligned': 4} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr0404_coverage.py` | test-module | 6 | AC-NFR0020-3, FR-0404, FR-0404 AC-1, FR-0404 AC-2 | {'aligned': 6} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_015_020_complete.py` | test-module | 20 | AC-FR-015-01, AC-FR-015-02, AC-FR-015-03, AC-FR-020-15 | {'aligned': 17, 'incomplete': 1, 'self-fulfilling': 1, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_020_discovery_unit.py` | test-module | 12 | FR-020, FR-020 AC-02 | {'aligned': 3, 'self-fulfilling': 9} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_050_060_070_080_order_modes.py` | test-module | 12 | AC-FR-050, AC-FR-060, AC-FR-070, AC-FR-080 | {'aligned': 9, 'import-only': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_115_125_driver_contract.py` | test-module | 10 | AC-FR-115, AC-FR-125, FR-115, FR-125 | {'aligned': 7, 'incomplete': 2, 'self-fulfilling': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_130_risk_strategy.py` | test-module | 4 | AC-FR-130, FR-115, FR-130 | {'aligned': 3, 'incomplete': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_140_price_limit.py` | test-module | 8 | AC-FR-140, FR-140, FR-160 | {'aligned': 1, 'incomplete': 7} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_150_quantity.py` | test-module | 8 | AC-FR-150, FR-150 | {'aligned': 4, 'incomplete': 4} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_160_time_t1.py` | test-module | 6 | AC-FR-160, FR-160 | {'aligned': 4, 'incomplete': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_170_halt.py` | test-module | 4 | AC-FR-170, FR-170 | {'aligned': 2, 'incomplete': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_180_funds.py` | test-module | 9 | AC-FR-180, FR-180, FR-200 | {'aligned': 5, 'incomplete': 2, 'import-only': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_185_cost_basis.py` | test-module | 7 | FR-185 | {'aligned': 7} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_190_parity.py` | test-module | 4 | AC-FR-190, FR-080, FR-140, FR-150 | {'aligned': 1, 'incomplete': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_200_slippage.py` | test-module | 5 | AC-FR-200, FR-200, fr200 | {'aligned': 4, 'incomplete': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_210_220_virtual_account.py` | test-module | 6 | AC-FR-130, AC-FR-210, AC-FR-220, FR-210 | {'aligned': 6} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_230_240_250_lifecycle.py` | test-module | 9 | AC-FR-230, AC-FR-240, AC-FR-250, FR-125 | {'aligned': 7, 'incomplete': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_340_350_metrics.py` | test-module | 12 | FR-340, FR-350 | {'aligned': 10, 'incomplete': 1, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_360_risk_events.py` | test-module | 11 | AC-FR-100, AC-FR-110, AC-FR-360, FR-100 | {'aligned': 11} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_360_triple_barrier.py` | test-module | 17 | AC-FR-360, FR-013, FR-360 | {'aligned': 16, 'incomplete': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_fr_440_450_dry_run_notification.py` | test-module | 6 | AC-FR-440, AC-FR-450, FR-440, FR-450 | {'aligned': 5, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_grid_search.py` | test-module | 1 | none | {'aligned': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_init_wizard.py` | test-module | 19 | none | {'aligned': 16, 'incomplete': 3} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_livequote.py` | test-module | 2 | none | {'aligned': 2} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_metrics.py` | test-module | 8 | none | {'aligned': 7, 'incomplete': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_runner.py` | test-module | 3 | none | {'aligned': 3} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_sim_broker_cleanup.py` | test-module | 3 | AC-NFR0020-3, NFR-0020 | {'aligned': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/service/test_sim_broker_paper.py` | test-module | 6 | none | {'aligned': 6} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_sim_broker_paper_lifecycle.py` | test-module | 4 | none | {'aligned': 4} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_strategy_runtime.py` | test-module | 2 | none | {'aligned': 2} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/service/test_stream_stop.py` | test-module | 1 | none | {'aligned': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/strategies/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/strategies/example/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/strategies/example/test_fr_0702_builtin_strategies.py` | test-module | 4 | AC-FR-0702-1, AC-FR-0702-3, AC-FR-0702-4, AC-FR-0702-5 | {'aligned': 4} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/strategies/example/test_fr_090_dual_ma.py` | test-module | 4 | FR-090 | {'aligned': 4} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/test_app_factory.py` | test-module | 1 | AC-FR-0703-3, FR-0703 | {'aligned': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/test_fr_010_020_030_040_sdk_discovery.py` | test-module | 22 | AC-FR-010, AC-FR-013, AC-FR-014, AC-FR-015 | {'aligned': 22} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/test_nfr_010_050_nonfunctional.py` | test-module | 15 | AC-NFR-010, AC-NFR-020, AC-NFR-030, AC-NFR-040 | {'aligned': 12, 'incomplete': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/test_nfr_060_runtime_injectability.py` | test-module | 11 | AC-NFR-060, FR-180, FR-200, FR-440 | {'aligned': 11} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/apis/analysis/test_kline_retirement.py` | test-module | 1 | none | {'aligned': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/apis/analysis/test_search_retirement.py` | test-module | 1 | none | {'aligned': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/components/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/components/analysis/test_backtest_charts.py` | test-module | 9 | AC-FR0370-1, AC-FR0370-2, FR-0370 | {'aligned': 9} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/components/analysis/test_kline_chart.py` | test-module | 3 | AC-FR-0501-1, AC-FR-0501-2, FR-0501, FR-0501 AC-1 | {'aligned': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/components/analysis/test_stock_list.py` | test-module | 2 | AC-FR-0501-3, AC-FR-0501-4, FR-0501, FR-0501 AC-3 | {'aligned': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/components/common/test_common.py` | test-module | 4 | AC-FR-0502-1, AC-FR-0502-4, FR-0502, FR-0502 AC-1 | {'aligned': 4} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/components/test_runtime_params.py` | test-module | 14 | AC-FR0020-1, FR-0020 | {'aligned': 13, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/components/test_toast.py` | test-module | 13 | AC-FR0170-1, FR-0170 | {'aligned': 13} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/pages/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/pages/system/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/pages/system/test_calendar.py` | test-module | 16 | none | {'aligned': 16} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/pages/system/test_datasource.py` | test-module | 7 | none | {'aligned': 7} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/pages/system/test_gateway.py` | test-module | 12 | none | {'aligned': 12} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/pages/system/test_jobs.py` | test-module | 5 | none | {'aligned': 5} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/pages/system/test_market.py` | test-module | 6 | none | {'aligned': 6} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/pages/system/test_risk_events.py` | test-module | 4 | none | {'aligned': 4} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/pages/system/test_runtime_monitor.py` | test-module | 4 | none | {'aligned': 4} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/pages/system/test_stocks.py` | test-module | 9 | none | {'aligned': 9} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/services/__init__.py` | helper/fixture | 0 | none | helper | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_account_overview.py` | test-module | 10 | AC-FR0390-1, AC-FR0390-2, AC-FR0390-3, AC-FR0390-4 | {'aligned': 10} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_accounts.py` | test-module | 18 | AC-FR0411-1, FR-0201, FR-0390, FR-0411 | {'aligned': 17, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_auth_session.py` | test-module | 12 | AC-FR0120-1, AC-FR0120-2, FR-0120 | {'aligned': 12} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_backtest_progress.py` | test-module | 12 | AC-FR0080-1, FR-0080 | {'aligned': 11, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_backtest_progress_fr0380.py` | test-module | 6 | AC-FR0380-1, FR-0080, FR-0080 AC-1, FR-0080 AC-3 | {'aligned': 6} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_backtest_reports.py` | test-module | 10 | AC-FR0091-1, AC-FR0091-2, AC-FR0092-1, AC-FR0093-1 | {'aligned': 10} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_dashboard.py` | test-module | 10 | AC-FR0201, AC-FR0201-1, AC-FR0202-1, AC-FR0202-2 | {'aligned': 10} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_gateway.py` | test-module | 12 | AC-FR0340-1, FR-0340 | {'aligned': 6, 'incomplete': 4, 'import-only': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_integrity.py` | test-module | 7 | AC-FR0320-1, FR-0320 | {'aligned': 6, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_layout.py` | test-module | 7 | AC-FR0130-2, AC-FR0130-4, AC-FR0150-1, FR-0130 | {'aligned': 5, 'import-only': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_notifications.py` | test-module | 11 | AC-FR0450-1, FR-0450 | {'aligned': 6, 'incomplete': 2, 'import-only': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_risk_events.py` | test-module | 10 | AC-FR0070-1, FR-0070 | {'aligned': 8, 'incomplete': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_routing.py` | test-module | 10 | AC-FR0110-1, AC-FR0140-1, FR-0110 | {'aligned': 10} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_runtime_control.py` | test-module | 20 | AC-FR0040-1, AC-FR0040-2, AC-FR0040-5, AC-FR0040-6 | {'aligned': 18, 'incomplete': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_scheduling.py` | test-module | 6 | AC-FR0260-1, FR-0010, FR-0020, FR-0040 | {'aligned': 6} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_stock_query.py` | test-module | 12 | AC-FR0330-1, FR-0330 | {'aligned': 12} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_strategy_management.py` | test-module | 17 | AC-FR0010-1, AC-FR0010-2, AC-FR0011-1, AC-FR0012-1 | {'aligned': 17} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_tasks.py` | test-module | 10 | AC-FR0310-1, FR-0310 | {'aligned': 7, 'incomplete': 2, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_trade.py` | test-module | 19 | AC-FR0420-4, FR-0420 | {'aligned': 19} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/services/test_trade_history.py` | test-module | 11 | AC-FR0400-1, AC-FR0400-2, AC-FR0430-1, AC-FR0430-2 | {'aligned': 11} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/test_degradation.py` | test-module | 28 | AC-FR0180-1, FR-0180 | {'aligned': 28} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/test_errors.py` | test-module | 6 | none | {'aligned': 6} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/test_events_and_storage.py` | test-module | 17 | NFR-0070 AC-5 | {'aligned': 14, 'import-only': 3} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/test_header.py` | test-module | 2 | none | {'aligned': 2} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/test_init_wizard.py` | test-module | 24 | none | {'aligned': 22, 'incomplete': 1, 'import-only': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/test_nfr_accessibility.py` | test-module | 10 | AC-NFR0020-1, NFR-0020 | {'aligned': 10} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/test_nfr_error_degradation.py` | test-module | 8 | AC-NFR0030-1, AC-NFR0030-2, NFR-0030 | {'aligned': 7, 'import-only': 1} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/test_nfr_long_task.py` | test-module | 7 | AC-NFR0060-1, AC-NFR0060-2, AC-NFR0060-3, AC-NFR0060-4 | {'aligned': 7} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/test_nfr_partial_refresh.py` | test-module | 9 | AC-NFR0050-1, AC-NFR0050-2, AC-NFR0050-3, NFR-0050 | {'aligned': 9} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/test_nfr_responsive.py` | test-module | 9 | AC-NFR0010-1, AC-NFR0010-2, AC-NFR0010-3, NFR-0010 | {'aligned': 9} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/test_nfr_state_persistence.py` | test-module | 8 | AC-NFR0070-1, AC-NFR0070-4, AC-NFR0070-5, NFR-0070 | {'aligned': 6, 'incomplete': 2} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/test_nfr_visual.py` | test-module | 23 | AC-NFR0040-1, AC-NFR0040-2, AC-NFR0040-3, AC-NFR0040-4 | {'aligned': 13, 'import-only': 10} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/quantide/web/test_strategy.py` | test-module | 37 | none | {'aligned': 37} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/quantide/web/test_trade.py` | test-module | 120 | none | {'aligned': 116, 'incomplete': 2, 'self-fulfilling': 1, 'import-only': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/strategies/test_fr_090_100_110_builtin_strategies.py` | test-module | 11 | AC-FR-090, AC-FR-100, AC-FR-110, FR-090 | {'aligned': 11} | **keep** — mapped references and substantive semantic signals |
| `tests/unit/test_app.py` | test-module | 1 | none | {'aligned': 1} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |
| `tests/unit/test_env_fixture_smoke.py` | test-module | 4 | none | {'aligned': 4} | **update** — no parseable FR/AC mapping; inspect semantics and map before retention |

Full function-level records are in `test-trace-data.json`. Unmapped tests are updated before keep; deletion follows only an Aaron-approved production deletion.
