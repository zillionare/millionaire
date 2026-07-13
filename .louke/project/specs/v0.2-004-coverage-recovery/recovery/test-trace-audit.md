# Test Trace Audit

- Test modules: **240**.
- Test functions: **1651/1651** with disposition and concrete target behavior.
- Functions with spec-qualified refs: **1651**.
- Dispositions: `{'aligned': 1455, 'update': 196}`.
- Semantic quality: `{'aligned': 1455, 'conflicting': 2, 'fake': 3, 'import-only': 41, 'incomplete': 87, 'self-fulfilling': 61, 'spec-gap': 2}`.
- Open Devon work items: **196**; update binding coverage: **196/196**; registry status: **open**.
- Registry: `devon-work-items.json`, SHA-256 `bac42a69bcd6359afe16fbcdc8ae710314ad00ced431dff9c1625186cb2bd088`.
- Full suite was prohibited and was not run; `failing` is recorded only when statically encoded, never guessed from old CI.

## Normative shard index

All module metadata and function-level records are normative in the listed JSON shards. Sage's 57 dispositions and all 196 open Devon bindings are materialized in those records.

| Test module | Functions | Recommendation | Dispositions | Quality | Normative record |
|---|---:|---|---|---|---|
| `tests/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-001e61d97d9d`](test-trace/tests-root.json) |
| `tests/assets/unit/scripts/build_env.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-1f7c12045801`](test-trace/tests-assets.json) |
| `tests/assets/unit/scripts/validate_env.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-e84096a57f9e`](test-trace/tests-assets.json) |
| `tests/conftest.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-e52e4ddd58b7`](test-trace/tests-root.json) |
| `tests/e2e/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-00bcc726b70a`](test-trace/tests-e2e-01.json) |
| `tests/e2e/backtest/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-dac872aa5fbc`](test-trace/tests-e2e-01.json) |
| `tests/e2e/backtest/test_dual_ma_accuracy.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-4d0c915920aa`](test-trace/tests-e2e-01.json) |
| `tests/e2e/backtest/test_fr_011_day_strategy.py` | 10 | update | `{"aligned": 9, "update": 1}` | `{"aligned": 9, "self-fulfilling": 1}` | [`testmod-7ba624dc8baf`](test-trace/tests-e2e-01.json) |
| `tests/e2e/calendar/test_fr_014_calendar.py` | 13 | update | `{"aligned": 12, "update": 1}` | `{"aligned": 12, "incomplete": 1}` | [`testmod-b562b7b67e58`](test-trace/tests-e2e-01.json) |
| `tests/e2e/calendar_v2/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-db45fb5e49ec`](test-trace/tests-e2e-01.json) |
| `tests/e2e/calendar_v2/test_fr_014_calendar_v2.py` | 20 | update | `{"aligned": 19, "update": 1}` | `{"aligned": 19, "incomplete": 1}` | [`testmod-183e485b7c82`](test-trace/tests-e2e-01.json) |
| `tests/e2e/conftest.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-824bc3e5c282`](test-trace/tests-e2e-01.json) |
| `tests/e2e/fixtures/combine_real_fixture.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-84798d87eaa8`](test-trace/tests-e2e-01.json) |
| `tests/e2e/fixtures/fetch_tushare.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-1aae8d426350`](test-trace/tests-e2e-01.json) |
| `tests/e2e/fixtures/generate_synthetic.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-ff08c7d57bc1`](test-trace/tests-e2e-01.json) |
| `tests/e2e/fixtures/minimal_assets.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-0be39b7cb094`](test-trace/tests-e2e-01.json) |
| `tests/e2e/http_integration/test_http_broker_api.py` | 6 | keep | `{"aligned": 6}` | `{"aligned": 6}` | [`testmod-4fa62d89d6ce`](test-trace/tests-e2e-01.json) |
| `tests/e2e/live/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-a986e7a7ec29`](test-trace/tests-e2e-01.json) |
| `tests/e2e/live/test_gateway_accuracy.py` | 5 | update | `{"aligned": 4, "update": 1}` | `{"aligned": 4, "incomplete": 1}` | [`testmod-dfac236950ae`](test-trace/tests-e2e-01.json) |
| `tests/e2e/pages/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-878bcaf6426d`](test-trace/tests-e2e-01.json) |
| `tests/e2e/pages/app.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-a59c8ed3b396`](test-trace/tests-e2e-01.json) |
| `tests/e2e/paper/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-ca55b8ec0dce`](test-trace/tests-e2e-01.json) |
| `tests/e2e/paper/test_dual_ma_accuracy.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-2275e676e6aa`](test-trace/tests-e2e-01.json) |
| `tests/e2e/paper/test_fr_115_185_360_e2e.py` | 7 | update | `{"aligned": 6, "update": 1}` | `{"aligned": 6, "incomplete": 1}` | [`testmod-20c4cd0d408e`](test-trace/tests-e2e-01.json) |
| `tests/e2e/paper/test_fr_140_190_trading_rules_e2e.py` | 11 | update | `{"aligned": 9, "update": 2}` | `{"aligned": 9, "incomplete": 2}` | [`testmod-6cbae8223032`](test-trace/tests-e2e-01.json) |
| `tests/e2e/paper/test_fr_440_450_200_360_e2e.py` | 11 | keep | `{"aligned": 11}` | `{"aligned": 11}` | [`testmod-80c9181f1d10`](test-trace/tests-e2e-01.json) |
| `tests/e2e/paper/test_l1_paper_smoke.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-6e8cee0f1cf6`](test-trace/tests-e2e-01.json) |
| `tests/e2e/risk_strategy/test_fr_013_risk_strategy.py` | 7 | keep | `{"aligned": 7}` | `{"aligned": 7}` | [`testmod-00e587545887`](test-trace/tests-e2e-01.json) |
| `tests/e2e/risk_strategy/test_fr_013_risk_structure.py` | 18 | update | `{"aligned": 15, "update": 3}` | `{"aligned": 15, "incomplete": 3}` | [`testmod-592922ca1a7f`](test-trace/tests-e2e-01.json) |
| `tests/e2e/securities/test_fr_015_securities.py` | 12 | keep | `{"aligned": 12}` | `{"aligned": 12}` | [`testmod-4fa813763f1a`](test-trace/tests-e2e-01.json) |
| `tests/e2e/securities_v2/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-310f3e1abedd`](test-trace/tests-e2e-01.json) |
| `tests/e2e/securities_v2/test_fr_015_securities_v2.py` | 13 | update | `{"aligned": 12, "update": 1}` | `{"aligned": 12, "incomplete": 1}` | [`testmod-b6e0d06b96d5`](test-trace/tests-e2e-01.json) |
| `tests/e2e/strategy_discovery/test_fr_010_base_strategy.py` | 10 | update | `{"aligned": 8, "update": 2}` | `{"aligned": 8, "self-fulfilling": 2}` | [`testmod-479164ca6dab`](test-trace/tests-e2e-01.json) |
| `tests/e2e/strategy_discovery/test_fr_020_discovery.py` | 8 | update | `{"aligned": 2, "update": 6}` | `{"aligned": 2, "self-fulfilling": 6}` | [`testmod-b5ec2c2e0d37`](test-trace/tests-e2e-01.json) |
| `tests/e2e/strategy_discovery_v2/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-92fb3c3c1c61`](test-trace/tests-e2e-01.json) |
| `tests/e2e/strategy_discovery_v2/test_fr_020_discovery_v2.py` | 40 | update | `{"aligned": 18, "update": 22}` | `{"aligned": 18, "self-fulfilling": 22}` | [`testmod-b581d6dcb435`](test-trace/tests-e2e-01.json) |
| `tests/e2e/strategy_example/test_dual_ma.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-fba1b9adde77`](test-trace/tests-e2e-01.json) |
| `tests/e2e/strategy_v2/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-99648f9bdde8`](test-trace/tests-e2e-01.json) |
| `tests/e2e/strategy_v2/test_fr_010_strategy_root.py` | 27 | update | `{"aligned": 23, "update": 4}` | `{"aligned": 23, "self-fulfilling": 4}` | [`testmod-f54f01ab6978`](test-trace/tests-e2e-01.json) |
| `tests/e2e/support/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-c409204d95e0`](test-trace/tests-e2e-01.json) |
| `tests/e2e/support/gateway_stub.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-4c247e49bf4c`](test-trace/tests-e2e-01.json) |
| `tests/e2e/support/init_wizard_session.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-d020c6ee50ea`](test-trace/tests-e2e-01.json) |
| `tests/e2e/support/runtime_factory.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-efba52f1b695`](test-trace/tests-e2e-01.json) |
| `tests/e2e/support/system_settings_session.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-b13f8c615456`](test-trace/tests-e2e-01.json) |
| `tests/e2e/support/test_gateway_stub.py` | 6 | keep | `{"aligned": 6}` | `{"aligned": 6}` | [`testmod-4d13811dde93`](test-trace/tests-e2e-01.json) |
| `tests/e2e/support/test_tushare_stub.py` | 3 | update | `{"aligned": 2, "update": 1}` | `{"aligned": 2, "incomplete": 1}` | [`testmod-5dbeeb944224`](test-trace/tests-e2e-01.json) |
| `tests/e2e/support/tushare_stub.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-63b2f3dee501`](test-trace/tests-e2e-01.json) |
| `tests/e2e/support/virtual_clock.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-bf0a168ceaf5`](test-trace/tests-e2e-01.json) |
| `tests/e2e/test_app_factory_e2e.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-103f14651d1b`](test-trace/tests-e2e-01.json) |
| `tests/e2e/test_boot_smoke.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-d1f4a8f11f81`](test-trace/tests-e2e-01.json) |
| `tests/e2e/test_ci_workflow_e2e.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-6cebff91eb07`](test-trace/tests-e2e-02.json) |
| `tests/e2e/test_coverage_checker_e2e.py` | 3 | keep | `{"aligned": 3}` | `{"aligned": 3}` | [`testmod-6b059aae3b64`](test-trace/tests-e2e-02.json) |
| `tests/e2e/test_gateway.py` | 3 | keep | `{"aligned": 3}` | `{"aligned": 3}` | [`testmod-ce3b3180c209`](test-trace/tests-e2e-02.json) |
| `tests/e2e/test_isolation_e2e.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-fe2ee2a381f9`](test-trace/tests-e2e-02.json) |
| `tests/e2e/test_live_smoke.py` | 1 | update | `{"update": 1}` | `{"incomplete": 1}` | [`testmod-7af10b84d636`](test-trace/tests-e2e-02.json) |
| `tests/e2e/test_paper.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-1c4d2660cd0e`](test-trace/tests-e2e-02.json) |
| `tests/e2e/test_smoke.py` | 2 | update | `{"aligned": 1, "update": 1}` | `{"aligned": 1, "conflicting": 1}` | [`testmod-7fd9f3f7e57a`](test-trace/tests-e2e-02.json) |
| `tests/e2e/three_mode/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-a1fbfbf6e3d9`](test-trace/tests-e2e-02.json) |
| `tests/e2e/three_mode/test_dual_ma_parity.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-be4e04466068`](test-trace/tests-e2e-02.json) |
| `tests/e2e/web/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-da44b0a9d1b8`](test-trace/tests-e2e-02.json) |
| `tests/e2e/web/test_dev_stub_mode.py` | 1 | update | `{"update": 1}` | `{"self-fulfilling": 1}` | [`testmod-570f37204379`](test-trace/tests-e2e-02.json) |
| `tests/e2e/web/test_init_wizard_flow.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-22baa7e31fff`](test-trace/tests-e2e-02.json) |
| `tests/e2e/web/test_init_wizard_tushare.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-d93181b27345`](test-trace/tests-e2e-02.json) |
| `tests/e2e/web/test_system_settings_flow.py` | 12 | keep | `{"aligned": 12}` | `{"aligned": 12}` | [`testmod-dcf2d3fc4d37`](test-trace/tests-e2e-02.json) |
| `tests/grid_search_support.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-9417d8e78efb`](test-trace/tests-root.json) |
| `tests/ground_truth/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-3e8f166cb017`](test-trace/tests-ground-truth.json) |
| `tests/ground_truth/calendar.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-fa0ed23423ff`](test-trace/tests-ground-truth.json) |
| `tests/ground_truth/discovery.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-ecb4bc1cf2ee`](test-trace/tests-ground-truth.json) |
| `tests/ground_truth/stocks.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-4736fd2b9c80`](test-trace/tests-ground-truth.json) |
| `tests/ground_truth/test_purity.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-58d32b901ffe`](test-trace/tests-ground-truth.json) |
| `tests/unit/_checkers/per_file_coverage.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-7ceddc39750c`](test-trace/tests-unit-01.json) |
| `tests/unit/_infra/test_coverage_artifact.py` | 3 | keep | `{"aligned": 3}` | `{"aligned": 3}` | [`testmod-f89d8de2aba4`](test-trace/tests-unit-01.json) |
| `tests/unit/_infra/test_coverage_thresholds.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-06cd54682e71`](test-trace/tests-unit-01.json) |
| `tests/unit/_infra/test_isolation_and_determinism.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-1140207edc4f`](test-trace/tests-unit-01.json) |
| `tests/unit/_infra/test_per_file_coverage.py` | 5 | keep | `{"aligned": 5}` | `{"aligned": 5}` | [`testmod-8826f44c96bb`](test-trace/tests-unit-01.json) |
| `tests/unit/_infra/test_pyproject_pytest_config.py` | 5 | keep | `{"aligned": 5}` | `{"aligned": 5}` | [`testmod-1e1070789141`](test-trace/tests-unit-01.json) |
| `tests/unit/_infra/test_unit_coverage_workflow.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-4066a6a2c83c`](test-trace/tests-unit-01.json) |
| `tests/unit/conftest.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-0cae8a7ee2d3`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/config/test_branding.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-9c0d82c22c47`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/config/test_fr_0703_config_contracts.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-392ae71a7991`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/config/test_fr_470_install.py` | 6 | update | `{"aligned": 5, "update": 1}` | `{"aligned": 5, "incomplete": 1}` | [`testmod-b7d5289b7f51`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/config/test_paths.py` | 5 | keep | `{"aligned": 5}` | `{"aligned": 5}` | [`testmod-9c911e0760a8`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/config/test_settings.py` | 14 | keep | `{"aligned": 14}` | `{"aligned": 14}` | [`testmod-829b0e7a65dd`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/domain/test_events.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-0c69705e58ba`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/ports/test_protocol_structural.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-281dd382e3d3`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/runtime/test_clock_bridge.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-a64f5dedcf17`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/runtime/test_gateway_client.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-134b3b4ae715`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/runtime/test_port_broker.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-573d19cc2961`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/strategy/test_strategy_discovery.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-142d3f69e537`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/test_adapter_registry.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-3fbb0dbbd35b`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/test_foundation_contracts.py` | 3 | keep | `{"aligned": 3}` | `{"aligned": 3}` | [`testmod-eae42ed96754`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/test_fr_010_base_strategy_unit.py` | 15 | keep | `{"aligned": 15}` | `{"aligned": 15}` | [`testmod-7905d05486a7`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/test_fr_012_live_strategy.py` | 6 | update | `{"aligned": 5, "update": 1}` | `{"aligned": 5, "import-only": 1}` | [`testmod-2a3bf4c18de0`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/test_gateway_broker_adapter.py` | 28 | update | `{"aligned": 26, "update": 2}` | `{"aligned": 26, "incomplete": 2}` | [`testmod-68f849a5b714`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/test_gateway_protocol_contract.py` | 8 | update | `{"aligned": 2, "update": 6}` | `{"aligned": 2, "conflicting": 1, "incomplete": 5}` | [`testmod-f206ddae1362`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/test_message.py` | 11 | update | `{"aligned": 9, "update": 2}` | `{"aligned": 9, "incomplete": 1, "self-fulfilling": 1}` | [`testmod-600b8d2d8359`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/test_runtime_modes.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-291ff69d4985`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/test_sim_broker_market_data.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-5551704e96f4`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/test_strategy_runner.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-5c6842e3ec34`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/test_strategy_runtime_manager.py` | 12 | update | `{"aligned": 11, "update": 1}` | `{"aligned": 11, "self-fulfilling": 1}` | [`testmod-0690b0fb9571`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/core/test_wizard_steps_v2.py` | 17 | keep | `{"aligned": 17}` | `{"aligned": 17}` | [`testmod-26a078109d3c`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/data/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-ab4f3f817c3c`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/data/fetchers/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-4486e80d7b29`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/data/fetchers/test_coverage_fetchers.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-df95a8ed6e23`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/data/fetchers/test_fr_270_280_tushare.py` | 11 | update | `{"aligned": 9, "update": 2}` | `{"aligned": 9, "incomplete": 1, "self-fulfilling": 1}` | [`testmod-e6981cb117b0`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/data/fetchers/test_fr_300_gateway.py` | 6 | update | `{"aligned": 5, "update": 1}` | `{"aligned": 5, "self-fulfilling": 1}` | [`testmod-e2872cf3fa01`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/data/fetchers/test_registry.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-7b12d95c3219`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/data/fetchers/test_tushare.py` | 8 | keep | `{"aligned": 8}` | `{"aligned": 8}` | [`testmod-91cc8ea107cf`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/data/models/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-8289ea804dc1`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/data/models/test_bars.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-32a09de98ac8`](test-trace/tests-unit-01.json) |
| `tests/unit/quantide/data/models/test_calendar.py` | 31 | update | `{"aligned": 30, "update": 1}` | `{"aligned": 30, "fake": 1}` | [`testmod-94b6aa8b77ee`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/models/test_coverage_models.py` | 5 | update | `{"aligned": 4, "update": 1}` | `{"aligned": 4, "import-only": 1}` | [`testmod-6060afca0063`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/models/test_fr_330_data_query.py` | 6 | keep | `{"aligned": 6}` | `{"aligned": 6}` | [`testmod-2b8341925851`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/models/test_fr_485_security_code.py` | 6 | update | `{"aligned": 5, "update": 1}` | `{"aligned": 5, "import-only": 1}` | [`testmod-dd33b8e7f08d`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/models/test_stocks.py` | 8 | keep | `{"aligned": 8}` | `{"aligned": 8}` | [`testmod-1b19b352a043`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/services/test_fr_320_integrity.py` | 6 | update | `{"aligned": 2, "update": 4}` | `{"aligned": 2, "fake": 1, "self-fulfilling": 3}` | [`testmod-680c22319fef`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/stores/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-c166a2b2e9d8`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/stores/test_bars.py` | 4 | update | `{"aligned": 3, "update": 1}` | `{"aligned": 3, "import-only": 1}` | [`testmod-71d63fe7ef74`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/stores/test_base.py` | 16 | keep | `{"aligned": 16}` | `{"aligned": 16}` | [`testmod-0dff34a8e2b7`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/stores/test_coverage_stores.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-446f3b6d60dc`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/stores/test_legacy_index_sector_fetch_retirement.py` | 1 | update | `{"update": 1}` | `{"incomplete": 1}` | [`testmod-a4c1d5678722`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/test_assets_manifest.py` | 3 | keep | `{"aligned": 3}` | `{"aligned": 3}` | [`testmod-6d48607534cb`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/test_coverage_helper.py` | 3 | keep | `{"aligned": 3}` | `{"aligned": 3}` | [`testmod-e05bb79b8f6a`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/test_coverage_sqlite.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-3d40924904e3`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/test_fr_290_adjust_limit.py` | 7 | update | `{"update": 7}` | `{"import-only": 1, "self-fulfilling": 6}` | [`testmod-d4df629b12aa`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/test_helper.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-cff555dcc14f`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/test_init_data.py` | 2 | update | `{"aligned": 1, "update": 1}` | `{"aligned": 1, "spec-gap": 1}` | [`testmod-b1c855a1c4ca`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/test_sqlite.py` | 30 | keep | `{"aligned": 30}` | `{"aligned": 30}` | [`testmod-b78ed4507adf`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/test_sqlite_market_data_retirement.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-9a5a5d66ebe5`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/utils/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-7b1ba1aaccb4`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/utils/test_coverage_resampler.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-9862e5620efc`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/utils/test_fr_480_resampler.py` | 8 | update | `{"aligned": 7, "update": 1}` | `{"aligned": 7, "incomplete": 1}` | [`testmod-af1492f72f5d`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/data/utils/test_fr_484_research_tools.py` | 7 | update | `{"aligned": 5, "update": 2}` | `{"aligned": 5, "incomplete": 2}` | [`testmod-5497c607c6ea`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/notify/test_fr_0701_notify_channels.py` | 5 | update | `{"aligned": 4, "update": 1}` | `{"aligned": 4, "incomplete": 1}` | [`testmod-a9642c2cd41d`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/notify/test_fr_481_notification.py` | 9 | update | `{"aligned": 7, "update": 2}` | `{"aligned": 7, "incomplete": 2}` | [`testmod-c1ce7ca839f1`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/notify/test_mail.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-c3b3ae71b7c0`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/service/test_abstract_broker.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-122612f0bc3f`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/service/test_backtest_broker.py` | 25 | update | `{"aligned": 21, "update": 4}` | `{"aligned": 21, "incomplete": 4}` | [`testmod-ae4245a4623d`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/service/test_backtest_logs.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-35e7c2479927`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/service/test_discovery.py` | 3 | keep | `{"aligned": 3}` | `{"aligned": 3}` | [`testmod-dd5badbb955c`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/service/test_forming_daily_bars.py` | 12 | keep | `{"aligned": 12}` | `{"aligned": 12}` | [`testmod-682f4f56c969`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/service/test_fr0401_coverage.py` | 3 | keep | `{"aligned": 3}` | `{"aligned": 3}` | [`testmod-9217e80661c8`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/service/test_fr0402_coverage.py` | 3 | keep | `{"aligned": 3}` | `{"aligned": 3}` | [`testmod-f0fe6c4e37f8`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/service/test_fr0403_coverage.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-be6389e14548`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/service/test_fr0404_coverage.py` | 6 | keep | `{"aligned": 6}` | `{"aligned": 6}` | [`testmod-67d58e6bbf71`](test-trace/tests-unit-02.json) |
| `tests/unit/quantide/service/test_fr_015_020_complete.py` | 20 | update | `{"aligned": 17, "update": 3}` | `{"aligned": 17, "import-only": 1, "incomplete": 1, "self-fulfilling": 1}` | [`testmod-76ec21594f94`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_020_discovery_unit.py` | 12 | update | `{"aligned": 3, "update": 9}` | `{"aligned": 3, "self-fulfilling": 9}` | [`testmod-6cf7f071c182`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_050_060_070_080_order_modes.py` | 12 | update | `{"aligned": 9, "update": 3}` | `{"aligned": 9, "import-only": 3}` | [`testmod-fc80daeeb8da`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_115_125_driver_contract.py` | 10 | update | `{"aligned": 7, "update": 3}` | `{"aligned": 7, "incomplete": 2, "self-fulfilling": 1}` | [`testmod-9e1449b707ff`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_130_risk_strategy.py` | 4 | update | `{"aligned": 3, "update": 1}` | `{"aligned": 3, "incomplete": 1}` | [`testmod-3184b48c9efa`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_140_price_limit.py` | 8 | update | `{"aligned": 1, "update": 7}` | `{"aligned": 1, "incomplete": 7}` | [`testmod-648862322973`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_150_quantity.py` | 8 | update | `{"aligned": 4, "update": 4}` | `{"aligned": 4, "incomplete": 4}` | [`testmod-2d7faa6d0f55`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_160_time_t1.py` | 6 | update | `{"aligned": 4, "update": 2}` | `{"aligned": 4, "incomplete": 2}` | [`testmod-8e046456591e`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_170_halt.py` | 4 | update | `{"aligned": 2, "update": 2}` | `{"aligned": 2, "incomplete": 2}` | [`testmod-7fc9ac6cad01`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_180_funds.py` | 9 | update | `{"aligned": 5, "update": 4}` | `{"aligned": 5, "import-only": 2, "incomplete": 2}` | [`testmod-d547b59640bb`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_185_cost_basis.py` | 7 | keep | `{"aligned": 7}` | `{"aligned": 7}` | [`testmod-837b37749573`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_190_parity.py` | 4 | update | `{"aligned": 1, "update": 3}` | `{"aligned": 1, "incomplete": 3}` | [`testmod-07769a21128f`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_200_slippage.py` | 5 | update | `{"aligned": 4, "update": 1}` | `{"aligned": 4, "incomplete": 1}` | [`testmod-a2dfb05e10ba`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_210_220_virtual_account.py` | 6 | keep | `{"aligned": 6}` | `{"aligned": 6}` | [`testmod-a3d259a3020b`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_230_240_250_lifecycle.py` | 9 | update | `{"aligned": 7, "update": 2}` | `{"aligned": 7, "incomplete": 2}` | [`testmod-44aa40a9b1c3`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_340_350_metrics.py` | 12 | update | `{"aligned": 10, "update": 2}` | `{"aligned": 10, "import-only": 1, "incomplete": 1}` | [`testmod-f08827bd84fb`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_360_risk_events.py` | 11 | keep | `{"aligned": 11}` | `{"aligned": 11}` | [`testmod-df5fc04a2acb`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_360_triple_barrier.py` | 17 | update | `{"aligned": 16, "update": 1}` | `{"aligned": 16, "incomplete": 1}` | [`testmod-3e31376bb27c`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_fr_440_450_dry_run_notification.py` | 6 | update | `{"aligned": 5, "update": 1}` | `{"aligned": 5, "import-only": 1}` | [`testmod-e656749d32dd`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_grid_search.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-7134c6daafc9`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_init_wizard.py` | 19 | update | `{"aligned": 16, "update": 3}` | `{"aligned": 16, "incomplete": 3}` | [`testmod-7c7085fb6b78`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_livequote.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-5c6b5be51778`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_metrics.py` | 8 | update | `{"aligned": 7, "update": 1}` | `{"aligned": 7, "incomplete": 1}` | [`testmod-c2fd9f1126e0`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_runner.py` | 3 | keep | `{"aligned": 3}` | `{"aligned": 3}` | [`testmod-2481993fd21c`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_sim_broker_cleanup.py` | 3 | keep | `{"aligned": 3}` | `{"aligned": 3}` | [`testmod-750cd15ebd36`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_sim_broker_paper.py` | 6 | keep | `{"aligned": 6}` | `{"aligned": 6}` | [`testmod-7ba94f593197`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_sim_broker_paper_lifecycle.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-524305412081`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_strategy_runtime.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-733d3abfa185`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/service/test_stream_stop.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-1fb78f5570e7`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/strategies/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-de42aa4edaf9`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/strategies/example/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-8691c48fa02d`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/strategies/example/test_fr_0702_builtin_strategies.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-5504acbb923e`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/strategies/example/test_fr_090_dual_ma.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-0357d03fcaa1`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/test_app_factory.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-bc659d00d00e`](test-trace/tests-unit-03.json) |
| `tests/unit/quantide/test_fr_010_020_030_040_sdk_discovery.py` | 22 | keep | `{"aligned": 22}` | `{"aligned": 22}` | [`testmod-c34d96afdac3`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/test_nfr_010_050_nonfunctional.py` | 15 | update | `{"aligned": 11, "update": 4}` | `{"aligned": 11, "fake": 1, "incomplete": 2, "spec-gap": 1}` | [`testmod-8b9593f3a1fb`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/test_nfr_060_runtime_injectability.py` | 11 | keep | `{"aligned": 11}` | `{"aligned": 11}` | [`testmod-6a7d52d6718b`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-30796e6038a4`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/apis/analysis/test_kline_retirement.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-ffbc98d9b86c`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/apis/analysis/test_search_retirement.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-d98204cba550`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/components/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-f9ae7c6d5de2`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/components/analysis/test_backtest_charts.py` | 9 | keep | `{"aligned": 9}` | `{"aligned": 9}` | [`testmod-6363f6871e20`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/components/analysis/test_kline_chart.py` | 3 | keep | `{"aligned": 3}` | `{"aligned": 3}` | [`testmod-ecb7acb4297e`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/components/analysis/test_stock_list.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-f82c52180ade`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/components/common/test_common.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-ace1fe4042e5`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/components/test_runtime_params.py` | 14 | update | `{"aligned": 13, "update": 1}` | `{"aligned": 13, "import-only": 1}` | [`testmod-a3f45339c04e`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/components/test_toast.py` | 13 | keep | `{"aligned": 13}` | `{"aligned": 13}` | [`testmod-b22570c33e21`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/pages/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-702c47ac6dae`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/pages/system/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-78b43499f7ec`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/pages/system/test_calendar.py` | 16 | keep | `{"aligned": 16}` | `{"aligned": 16}` | [`testmod-5f3ccffe6a52`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/pages/system/test_datasource.py` | 7 | keep | `{"aligned": 7}` | `{"aligned": 7}` | [`testmod-7d7259796143`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/pages/system/test_gateway.py` | 12 | keep | `{"aligned": 12}` | `{"aligned": 12}` | [`testmod-30587c87fcdd`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/pages/system/test_jobs.py` | 5 | keep | `{"aligned": 5}` | `{"aligned": 5}` | [`testmod-e6b76f26a78d`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/pages/system/test_market.py` | 6 | keep | `{"aligned": 6}` | `{"aligned": 6}` | [`testmod-5f3b33e3a3a3`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/pages/system/test_risk_events.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-9c0334820a48`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/pages/system/test_runtime_monitor.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-16276c41f756`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/pages/system/test_stocks.py` | 9 | keep | `{"aligned": 9}` | `{"aligned": 9}` | [`testmod-2fa687fb16bb`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/services/__init__.py` | 0 | keep-helper | `{}` | `{}` | [`testmod-78d3c6440955`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/services/test_account_overview.py` | 10 | keep | `{"aligned": 10}` | `{"aligned": 10}` | [`testmod-d5b9ccbe59cb`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/services/test_accounts.py` | 18 | update | `{"aligned": 17, "update": 1}` | `{"aligned": 17, "import-only": 1}` | [`testmod-35bb8b304769`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/services/test_auth_session.py` | 12 | keep | `{"aligned": 12}` | `{"aligned": 12}` | [`testmod-f42025054381`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/services/test_backtest_progress.py` | 12 | update | `{"aligned": 11, "update": 1}` | `{"aligned": 11, "import-only": 1}` | [`testmod-e1304c1480bd`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/services/test_backtest_progress_fr0380.py` | 6 | keep | `{"aligned": 6}` | `{"aligned": 6}` | [`testmod-57426545fba9`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/services/test_backtest_reports.py` | 10 | keep | `{"aligned": 10}` | `{"aligned": 10}` | [`testmod-8074c1b8202f`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/services/test_dashboard.py` | 10 | keep | `{"aligned": 10}` | `{"aligned": 10}` | [`testmod-2e275a62cb63`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/services/test_gateway.py` | 12 | update | `{"aligned": 6, "update": 6}` | `{"aligned": 6, "import-only": 2, "incomplete": 4}` | [`testmod-db12dbc4b9a4`](test-trace/tests-unit-04.json) |
| `tests/unit/quantide/web/services/test_integrity.py` | 7 | update | `{"aligned": 6, "update": 1}` | `{"aligned": 6, "import-only": 1}` | [`testmod-4cbaa696a1c4`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/services/test_layout.py` | 7 | update | `{"aligned": 5, "update": 2}` | `{"aligned": 5, "import-only": 2}` | [`testmod-0f7f1affd8d7`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/services/test_notifications.py` | 11 | update | `{"aligned": 6, "update": 5}` | `{"aligned": 6, "import-only": 3, "incomplete": 2}` | [`testmod-b4424d153c84`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/services/test_risk_events.py` | 10 | update | `{"aligned": 8, "update": 2}` | `{"aligned": 8, "incomplete": 2}` | [`testmod-5279df012efd`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/services/test_routing.py` | 10 | keep | `{"aligned": 10}` | `{"aligned": 10}` | [`testmod-f4b6fabd22e5`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/services/test_runtime_control.py` | 20 | update | `{"aligned": 18, "update": 2}` | `{"aligned": 18, "incomplete": 2}` | [`testmod-ec17111e1cfd`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/services/test_scheduling.py` | 6 | keep | `{"aligned": 6}` | `{"aligned": 6}` | [`testmod-c526aa461521`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/services/test_stock_query.py` | 12 | keep | `{"aligned": 12}` | `{"aligned": 12}` | [`testmod-8737fbcb39f5`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/services/test_strategy_management.py` | 17 | keep | `{"aligned": 17}` | `{"aligned": 17}` | [`testmod-cb5f52fb478b`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/services/test_tasks.py` | 10 | update | `{"aligned": 7, "update": 3}` | `{"aligned": 7, "import-only": 1, "incomplete": 2}` | [`testmod-a9d6a6ada258`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/services/test_trade.py` | 19 | keep | `{"aligned": 19}` | `{"aligned": 19}` | [`testmod-1a3ea4f7694e`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/services/test_trade_history.py` | 11 | keep | `{"aligned": 11}` | `{"aligned": 11}` | [`testmod-c170d654a268`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/test_degradation.py` | 28 | keep | `{"aligned": 28}` | `{"aligned": 28}` | [`testmod-957de2aa44a1`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/test_errors.py` | 6 | keep | `{"aligned": 6}` | `{"aligned": 6}` | [`testmod-044ebdbe4745`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/test_events_and_storage.py` | 17 | update | `{"aligned": 14, "update": 3}` | `{"aligned": 14, "import-only": 3}` | [`testmod-4b48794d1b42`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/test_header.py` | 2 | keep | `{"aligned": 2}` | `{"aligned": 2}` | [`testmod-3648f8c2d568`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/test_init_wizard.py` | 24 | update | `{"aligned": 22, "update": 2}` | `{"aligned": 22, "import-only": 1, "incomplete": 1}` | [`testmod-9387eb156fee`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/test_nfr_accessibility.py` | 10 | keep | `{"aligned": 10}` | `{"aligned": 10}` | [`testmod-3939bf0de264`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/test_nfr_error_degradation.py` | 8 | update | `{"aligned": 7, "update": 1}` | `{"aligned": 7, "import-only": 1}` | [`testmod-191249dbd49b`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/test_nfr_long_task.py` | 7 | keep | `{"aligned": 7}` | `{"aligned": 7}` | [`testmod-1245e3b52d82`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/test_nfr_partial_refresh.py` | 9 | keep | `{"aligned": 9}` | `{"aligned": 9}` | [`testmod-11c6491553d6`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/test_nfr_responsive.py` | 9 | keep | `{"aligned": 9}` | `{"aligned": 9}` | [`testmod-2831de14cf24`](test-trace/tests-unit-05.json) |
| `tests/unit/quantide/web/test_nfr_state_persistence.py` | 8 | update | `{"aligned": 6, "update": 2}` | `{"aligned": 6, "incomplete": 2}` | [`testmod-464b5e805a43`](test-trace/tests-unit-06.json) |
| `tests/unit/quantide/web/test_nfr_visual.py` | 23 | update | `{"aligned": 13, "update": 10}` | `{"aligned": 13, "import-only": 10}` | [`testmod-f368642d72bb`](test-trace/tests-unit-06.json) |
| `tests/unit/quantide/web/test_strategy.py` | 37 | keep | `{"aligned": 37}` | `{"aligned": 37}` | [`testmod-454117450b5f`](test-trace/tests-unit-06.json) |
| `tests/unit/quantide/web/test_trade.py` | 120 | update | `{"aligned": 116, "update": 4}` | `{"aligned": 116, "import-only": 1, "incomplete": 2, "self-fulfilling": 1}` | [`testmod-110b8cf2a76f`](test-trace/tests-unit-06.json) |
| `tests/unit/strategies/test_fr_090_100_110_builtin_strategies.py` | 11 | update | `{"aligned": 9, "update": 2}` | `{"aligned": 9, "incomplete": 2}` | [`testmod-e8dcad5b0ac1`](test-trace/tests-unit-06.json) |
| `tests/unit/test_app.py` | 1 | keep | `{"aligned": 1}` | `{"aligned": 1}` | [`testmod-fcbbe89d576b`](test-trace/tests-unit-06.json) |
| `tests/unit/test_env_fixture_smoke.py` | 4 | keep | `{"aligned": 4}` | `{"aligned": 4}` | [`testmod-1f890b766e44`](test-trace/tests-unit-06.json) |
