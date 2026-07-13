# Sage semantic review of recovery contracts

- Review revision: `59a3cd4`
- Base production index SHA-256: `dea992b446a352d7f48253af03cc6f472d632a661c9d68bfd771cf729a079dd4`
- Base production shard-manifest SHA-256: `56ee03f245e931478fc2d6ca5f1e8e6cacdb79813a7d70ae466a01961d710616`
- Result: all 13 shards and all 169 path records reviewed; 9 records required no semantic correction and 160 records require the normative corrections below.

The immutable Archer index and shards are the path-keyed evidence base. This review is the normative interpretation layer: where generated prose conflicts with this file, this file wins; where upstream v0.2-001/002/003 conflicts with either recovery artifact, the locked upstream contract wins.

## Shard review closure

| Shard | Records | Review |
|---|---:|---|
| `production-contracts/quantide-config.json` | 5 | read and compared with source/public consumers |
| `production-contracts/quantide-core-01.json` | 24 | read and compared with source/public consumers |
| `production-contracts/quantide-core-02.json` | 5 | read and compared with source/public consumers |
| `production-contracts/quantide-data.json` | 20 | read and compared with source/public consumers |
| `production-contracts/quantide-notify.json` | 3 | read and compared with source/public consumers |
| `production-contracts/quantide-root.json` | 3 | read and compared with source/public consumers |
| `production-contracts/quantide-service.json` | 15 | read and compared with source/public consumers |
| `production-contracts/quantide-strategies.json` | 3 | read and compared with source/public consumers |
| `production-contracts/quantide-web-01.json` | 25 | read and compared with source/routes/consumers |
| `production-contracts/quantide-web-02.json` | 26 | read and compared with source/routes/consumers |
| `production-contracts/quantide-web-03.json` | 14 | read and compared with source/routes/consumers |
| `production-contracts/quantide-web-04.json` | 18 | read and compared with source/routes/consumers |
| `production-contracts/quantide-web-05.json` | 8 | read and compared with source/routes/consumers |

## Normative corrections for the 160 generated records

The 160 records are exactly those with a generated `schema/re-export` surface for an imported dependency, a concatenated/mangled callable signature, or a generated private-symbol omission presented as public-surface evidence. Apply all of these corrections path by path:

1. A name introduced only by `import`/`from ... import ...` is an implementation dependency, **not** this module's public API. It is a public re-export only when the module explicitly exposes it through `__all__`, or when a package `__init__.py` imports it as its documented package surface and a real consumer imports it from that package. Generated wildcard (`*`), `annotations`, typing names, decorators, framework HTML classes, loggers, database handles, and imported service/model classes are therefore removed from `public_symbols`, accepted inputs, observable outputs, and proposed AC surfaces unless that explicit re-export rule is met.
2. A callable's accepted input is its source declaration with punctuation preserved: positional-only `/`, keyword-only `*`, `self`/`cls`, `async`, defaults, `*args`, and `**kwargs` must not be concatenated (for example, generated `stopself` or `functionarg: type` text is non-normative). Route decorators plus the source callable declaration define HTTP method/path and parameters.
3. Leading-underscore definitions and constants are implementation details unless a locked upstream contract or an actual cross-module production consumer names them. Their mere AST presence is neither a missing public symbol nor an AC outlet.
4. Generated return-expression text describes an implementation observation only. It does not create a promised value, error, DTO field, persistence mutation, route, or fallback. Such behavior is normative only when corroborated by the record's highest-precedence upstream source or listed real production consumer. Imported dependency behavior and unreachable/private branches are not promoted.
5. For classes and dataclasses, the public contract is the source constructor/public methods and the locked DTO/schema fields; imported decorators/base classes are excluded. For protocols, only protocol members are public. For marker modules, import success and explicit package re-exports are the complete path-local surface.
6. The nine hand-written path contracts already present in `spec.md` remain authoritative. AD-01 through AD-06 remain pending; generated prose cannot choose retain/delete/waiver or turn excluded registration/reset behavior into a success path.

After these corrections, each of the 169 path keys still has concrete accepted input/boundary, observable output, failure/fallback, state/cleanup and precedence fields: the fields are read from its shard record, corrected by the six rules above, then constrained by the locked upstream source. A reconstruction that reads the index without all 13 verified shards, or that fails to apply this review layer, is invalid.

## Test functions previously requiring Sage contract

The base test trace is the immutable Archer evidence at index SHA-256 `02d1ff2e51d4ca7d824e04f06cfa17b33c7b7737554e5e4841667e644c4e002a` and shard-manifest SHA-256 `f8305dfdc251d1d15fb934fd981966ed336419af7ac9fb56e0d4ab2eab9fa07f`. The following is the function-keyed normative overlay for all 57 `needs-Sage-contract` records. `Aligned` means replace that disposition with `aligned` and set the stated spec-qualified target refs. `Update` means replace it with `update`; Devon must rewrite or remove it under FR-1301/FR-1601, and it cannot count toward AC closure before that work is independently reviewed.

### Aligned — 40

- `tests/e2e/paper/test_fr_440_450_200_360_e2e.py::{test_fr_450_notification_event_5_constants,test_fr_450_notification_event_values_match_spec}` → `v0.2-001-strategy-framework FR-450 / AC-450-01`.
- `tests/e2e/test_ci_workflow_e2e.py::{test_workflow_python_matrix_3_13_plus,test_workflow_triggers_on_releases_branches}` → `v0.2-003-coverage FR-0601 / AC-FR0601-01`; `test_workflow_invokes_coverage_checker` → `v0.2-003-coverage FR-0601 / AC-FR0601-04`; `test_workflow_no_continue_on_error_on_coverage_gate` → `v0.2-003-coverage FR-0601 / AC-FR0601-05`.
- `tests/e2e/test_gateway.py::test_missing_gateway_disables_live_trade_but_keeps_gateway_page_available` → `v0.2-002-ui FR-0180 / AC-FR0180-02` and `v0.2-002-ui FR-0180 / AC-FR0180-07`.
- `tests/e2e/test_isolation_e2e.py::test_random_order_yields_identical_totals` → `v0.2-003-coverage FR-0104 / AC-FR0104-04` and `v0.2-003-coverage NFR-0020 / AC-NFR0020-02`.
- `tests/ground_truth/test_purity.py::{test_ground_truth_does_not_import_quantide,test_ground_truth_files_exist}` → `v0.2-003-coverage FR-0001 / AC-FR0001-02` and `v0.2-003-coverage FR-0103 / AC-FR0103-01`; these protect independent oracle inputs, not production behavior by themselves.
- `tests/unit/quantide/core/domain/test_events.py::test_events_preserve_supplied_public_fields` → `v0.2-003-coverage FR-0201 / AC-FR0201-01`; `test_event_defaults_and_error_details_are_instance_isolated` → `v0.2-003-coverage FR-0201 / AC-FR0201-02` and `v0.2-003-coverage FR-0201 / AC-FR0201-03`.
- `tests/unit/quantide/core/test_fr_010_base_strategy_unit.py::test_lifecycle_can_be_called` → `v0.2-001-strategy-framework FR-010 / AC-010-02`; `{test_subclass_default_config,test_log_method_callable,test_log_with_tm,test_record_method_callable}` → `v0.2-001-strategy-framework FR-010 / AC-010-03`.
- All 17 functions in `tests/unit/quantide/core/test_wizard_steps_v2.py`: step count/order/name and metadata lookup functions → `v0.2-002-ui FR-0460 / AC-FR0460-02`; required/optional/completion and download-parent functions → `v0.2-002-ui FR-0460 / AC-FR0460-02` and `AC-FR0460-03`; reconfiguration field functions → `v0.2-002-ui FR-0460 / AC-FR0460-05`.
- `tests/unit/quantide/data/test_assets_manifest.py::test_manifest_tracks_existing_asset_files` → `v0.2-003-coverage FR-0103 / AC-FR0103-01`.
- `tests/unit/quantide/test_nfr_010_050_nonfunctional.py::test_nfr_020_notification_event_is_string_enum` → `v0.2-001-strategy-framework FR-450 / AC-450-01`; `test_nfr_020_order_execution_mode_is_string_enum` → `v0.2-001-strategy-framework FR-010 / AC-010-04`.
- `tests/unit/test_env_fixture_smoke.py::{test_env_helper_is_trade_day,test_env_helper_count_trading_days,test_env_helper_day_shift}` → `v0.2-003-coverage FR-0103 / AC-FR0103-01`; these validate the versioned independent calendar fixture and do not replace production calendar tests.

### Update — 17

- `tests/e2e/test_live_smoke.py::test_live_smoke_contract_for_real_broker_path` → M-DEV `incomplete`: OS/environment assertions do not exercise the referenced wizard/gateway/promotion behavior; rewrite against `v0.2-002-ui FR-0340 / AC-FR0340-06`, `FR-0420 / AC-FR0420-01`, and `FR-0460 / AC-FR0460-04`, or delete after the five FR-1601 evidence fields are complete.
- `tests/e2e/test_smoke.py::test_login_redirects_into_strategy_workspace` → M-DEV `conflicting`: `/strategy/` contradicts the locked login destinations in `v0.2-002-ui FR-0110 / AC-FR0110-02` and `FR-0120 / AC-FR0120-01`; update expected routing.
- All four functions in `tests/unit/quantide/data/services/test_fr_320_integrity.py` → M-DEV `fake/self-fulfilling`: list arithmetic, `assert True`, and deliberate `1/0` do not exercise the integrity service; rewrite against `v0.2-001-strategy-framework FR-320 / AC-320-01` or `AC-320-02`.
- All six functions in `tests/unit/quantide/data/test_fr_290_adjust_limit.py` → M-DEV `self-fulfilling`: local arithmetic does not call adjustment/limit production behavior; rewrite against `v0.2-001-strategy-framework FR-290 / AC-290-01` or `AC-290-02`.
- `tests/unit/quantide/data/test_init_data.py::test_init_data_allows_explicit_db_override` → M-DEV `spec-gap`: no locked AC establishes this override as public behavior; identify a real consumer/upstream AC or delete only after FR-1601 evidence review.
- `tests/unit/quantide/data/utils/test_fr_484_research_tools.py::test_edge_single_asset` → M-DEV `incomplete`: it asserts a locally split frame without establishing the production `train_test_split` call; rewrite against `v0.2-003-coverage FR-0404 / AC-FR0404-02`.
- `tests/unit/quantide/core/test_gateway_protocol_contract.py::test_no_htmx_request_patterns_in_quantide_source` → M-DEV `conflicting`: v0.2-002 explicitly permits HTMX partial requests; replace the repository-wide text ban with behavior assertions under `v0.2-003-coverage FR-0504 / AC-FR0504-04` and `AC-FR0504-05`.
- `tests/unit/quantide/test_nfr_010_050_nonfunctional.py::test_nfr_040_no_unused_imports_notifications` → M-DEV `spec-gap`: lint cleanliness is not an inherited product AC; move to lint tooling or delete after FR-1601 evidence review.
- `tests/unit/quantide/test_nfr_010_050_nonfunctional.py::test_nfr_010_performance_marker_exists` → M-DEV `fake`: `or True` makes the assertion unconditional; rewrite as a real marker/config assertion only if a locked AC is identified, otherwise delete after FR-1601 evidence review.

No row above authorizes deletion. The 17 update rows are future Devon work and remain blockers until repaired or independently approved under the deletion standard. The six Aaron decisions remain unresolved.

## Existing 179 update records: normative M-DEV categories

The Archer trace's 179 `update` functions are mandatory M-DEV work, not generic recommendations: 85 `incomplete` functions must add missing observable assertions/branches; 52 `self-fulfilling` functions must replace implementation-derived/local tautological expected values with independent fixtures/formulas; 41 `import-only` functions must exercise an AC behavior or become deletion candidates with all five evidence fields; 1 `fake` function must replace its unconditional assertion with an AC-derived assertion or become such a deletion candidate. Every row retains its function id, target behavior, quality evidence and target refs from the verified shard and must receive an open work item before M-DEV closure.
