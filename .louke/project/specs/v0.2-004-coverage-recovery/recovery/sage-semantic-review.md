# Sage semantic review of source-grounded recovery contracts

- Production index SHA-256: `8410d32fb4b64c0d38ef21f947c45be7164185dcaa09f36a7061bc99b9c8bfbe`
- Production shard-manifest SHA-256: `4ec8dbdbf8eaabfe1d8a355df778ae438e03b6dc3b18b0038955ba91472cac39`
- Test index SHA-256: `3d7ebc07cc8d014aab8981c025a142f1112c7d7cfb05390254de02c19da38fd0`
- Test shard-manifest SHA-256: `f48b15e808737352ad6a5c4d8da2b2a5f9b97fa3fb56a4ca2881463ec2380352`
- Devon work registry SHA-256: `bac42a69bcd6359afe16fbcdc8ae710314ad00ced431dff9c1625186cb2bd088`
- Production closure: 13 shards, 169 unique disk-exact paths, 169 source-grounded contracts, 0 pseudo-import APIs, 0 mangled signatures, 0 missing anchors.
- Test closure: 240 modules, 1651 functions, 1455 aligned, 196 update, 0 needs-Sage-contract; 196 update functions bind one-to-one to 196 open `RW-*` items.

## Precedence and disposition rule

Each candidate was reviewed under the locked order: v0.2-001/002/003 spec+acceptance, then interfaces, then story, then actual public consumers/current implementation. A higher source converts contrary code into an implementation defect; it is not an Aaron product question. A lower source is used only when all higher sources are silent. The corrected shard row remains the normative path contract; this review records why a candidate does or does not require Aaron and is not a generic contract overlay.

## Additional 55-candidate resolution table

| Candidate | Path | Resolved by | Normative resolution |
|---|---|---|---|
| SAGE-PROD-15036E03E523 | `quantide/core/init_wizard_steps.py` | spec | v0.2-002 FR-0460 ten-step `wizard_steps_v2` is authoritative; the consumed six-step schema is compatibility-only and must not drive the product flow. |
| SAGE-PROD-01435F6276F5 | `quantide/core/runtime/gateway_broker.py` | spec | v0.2-001 FR-050/060/070 fixes paper/live auction and next-open semantics; unavailable live-open data is an implementation defect, not permission to characterize historical auction-like pricing. |
| SAGE-PROD-027974B1CCDE | `quantide/data/fetchers/__init__.py` | current-compatibility | The explicit wildcard package import is the current compatibility facade for source-defined Tushare helpers; imported dependencies/private names are excluded and no broader API is inferred. |
| SAGE-PROD-89E180C24ABE | `quantide/notify/dingtalk.py` | spec | v0.2-001 FR-481 limits `ding` messages to text and markdown `{title,text}`; unsupported shapes must be rejected deterministically and incidental `KeyError`/unbound-local failures are defects. |
| SAGE-PROD-BACFFEB485FE | `quantide/notify/mail.py` | current-compatibility | Existing implementation and compatibility tests establish sender-based SMTP authentication; the unused `username` fallback is not a second product behavior and the implementation/signature mismatch is remediation work. |
| SAGE-PROD-CF608C440483 | `quantide/service/datafeed.py` | spec | v0.2-001 AC-010/115 requires `1d` in all modes, `30m` in paper/live, and explicit backtest rejection; silently serving DAY for non-DAY is an implementation defect. |
| SAGE-PROD-A436A1459981 | `quantide/service/discovery.py` | spec | v0.2-001 FR-020 enumeration metadata, diagnostics, non-recursive scan and user-over-builtin precedence are canonical; `StrategyLoader` remains compatibility/internal where consumed. |
| SAGE-PROD-5B3A3D325D59 | `quantide/service/grid_search.py` | current-compatibility | The public result is one row per successful combination with metrics and params; no ranking guarantee exists. The dead lowercase `sharpe` branch is not normative and must not contradict the emitted `Sharpe Ratio` DTO. |
| SAGE-PROD-2272E540793C | `quantide/service/livequote.py` | current-compatibility | Source payload semantics identify 1d volume/amount as cumulative snapshots, so cache updates replace those fields; additive accumulation is an implementation defect. |
| SAGE-PROD-17252C8BA6C1 | `quantide/service/metrics.py` | current-compatibility | Existing consumers and implementation use `None` for insufficient history; retain that compatibility boundary while non-empty output remains the metrics DataFrame contract. |
| SAGE-PROD-28D4861467F3 | `quantide/service/registry.py` | interfaces | v0.2-001 interfaces define `portfolio_id` as UUID, so colon is outside the valid identifier domain; registry keys need not support arbitrary colon-bearing IDs. |
| SAGE-PROD-F85C02B60215 | `quantide/service/runner.py` | spec | Locked lifecycle/resource contracts require `on_stop` once and observable failed-run cleanup; leaving broker/portfolio finalization incomplete after failure is an implementation defect. |
| SAGE-PROD-E6909E7D5207 | `quantide/service/sim_broker.py` | spec | v0.2-001 `trade_target_pct(0)` means liquidate the target position under normal sell rules; wrong positional forwarding is an implementation defect. |
| SAGE-PROD-4EBC3E5E77A8 | `quantide/service/strategy_runtime.py` | spec | Persisted runtime restore must preserve safety blocks and expose failure; corrupt state may not silently fail open by discarding blocks. |
| SAGE-PROD-D341CA7496AE | `quantide/service/trade_lightning.py` | spec | v0.2-002 FR-0420 fixes the reference-price choices; v0.2-003 AC-FR0404 rejects illegal `price_ref`. Unknown values must not persist as zero-price fallback. |
| SAGE-PROD-DD9DA7FDD598 | `quantide/service/triple_barrier.py` | spec | v0.2-001 FR-013/360 locks formulas and v0.2-003 FR-0404 keeps this service in scope; runtime wiring is implementation work, not a product disposition or dead-code decision. |
| SAGE-PROD-2547002D3646 | `quantide/web/apis/analysis/kline.py` | interfaces | v0.2-002 interfaces make `/system/stocks/{symbol}/kline` canonical; legacy `/api/v1/kline/*` may only be a tested compatibility redirect/adapter, not a competing API. |
| SAGE-PROD-6887921CC187 | `quantide/web/apis/broker.py` | consumer | Registered routes with real home/E2E consumers remain compatibility APIs, but must satisfy v0.2-003 FR-0504 input/status/schema/ErrorEnvelope rules; incomplete handlers are defects. |
| SAGE-PROD-9F9D0F1081ED | `quantide/web/auth/routes.py` | interfaces | Canonical behavior is POST `/login`, POST `/logout`, safe `next`, and 303 destinations; `/auth/*` may only adapt compatibly. GET logout and unvalidated redirect targets are defects. |
| SAGE-PROD-82C6D31D5D38 | `quantide/web/components/analysis/kline_chart.py` | spec | v0.2-003 FR-0501 fixes constructor inputs `chart_id/data/width/height` and stable empty rendering; source/tests with another signature must be updated. |
| SAGE-PROD-C864FFF98FDA | `quantide/web/events.py` | interfaces | v0.2-002 fixes GET `/events/stream` and replay/snapshot SSE semantics; DTO-only source means the endpoint is missing implementation, not optional release scope. |
| SAGE-PROD-75E42FE985B3 | `quantide/web/middleware_feature.py` | spec | v0.2-002 FR-0180 governs canonical paper/live degradation routes; matching only legacy `/trade/simulation` is an implementation defect. |
| SAGE-PROD-9821DD3FC75B | `quantide/web/middleware_init.py` | interfaces | Uninitialized requests use 303 `/wizard`; `/init-wizard` is compatibility-only. Current 302/path behavior must converge. |
| SAGE-PROD-7AD9A9E9B8DB | `quantide/web/middleware.py` | spec | v0.2-003 FR-0504 requires ErrorEnvelope output without sensitive details; raw traceback/exception text is never production HTTP behavior. |
| SAGE-PROD-8F002113F409 | `quantide/web/pages/accounts.py` | interfaces | Canonical routes and confirmation contracts are `/accounts*`; `/system/accounts*` may only be compatibility adapters and destructive actions must validate confirmation server-side. |
| SAGE-PROD-C75ACF006267 | `quantide/web/pages/data_market.py` | spec | v0.2-003 FR-0503 keeps market data verify/update/progress in scope with deterministic service fixtures and task isolation; stub verification/global progress are implementation defects. |
| SAGE-PROD-302FAB608470 | `quantide/web/pages/history_trades.py` | interfaces | v0.2-002 FR-0400 and `/trade/trades?from&to` require the complete time range; ignoring `end_date` is an implementation defect. |
| SAGE-PROD-967460246B4C | `quantide/web/pages/init_wizard.py` | interfaces | `/wizard*` and the method table are canonical; state-changing step/download/complete/reset operations must not be exposed by GET/HEAD. |
| SAGE-PROD-0748D3304030 | `quantide/web/pages/live.py` | spec | v0.2-002 excludes local live-account creation; the create tombstone is not a supported success endpoint and may only provide non-mutating compatibility/retirement behavior. |
| SAGE-PROD-AB0406173054 | `quantide/web/pages/paper.py` | interfaces | Paper components must target paper routes; reuse that submits/refreshes `/trade/live/*` is an implementation defect. |
| SAGE-PROD-2D3B6262FDAA | `quantide/web/pages/strategy.py` | interfaces | v0.2-002 `/strategy*` methods/DTOs are canonical and v0.2-003 makes service policies the business layer; overlapping legacy behavior must adapt rather than compete. |
| SAGE-PROD-1390E20AAD1D | `quantide/web/pages/system/datasource.py` | spec | Mutating sync is a state-changing operation subject to v0.2-003 HTTP/middleware safety; GET/HEAD mutation is an implementation defect. |
| SAGE-PROD-23700ED1EB6D | `quantide/web/pages/system/gateway.py` | spec | v0.2-002 FR-0340 explicitly requires automatic test-before-save and save only after success; direct untested persistence is an implementation defect. |
| SAGE-PROD-518824298F03 | `quantide/web/pages/system/jobs.py` | interfaces | Task mutations use POST under the canonical task contract; GET/HEAD toggle/run behavior is invalid compatibility behavior. |
| SAGE-PROD-29C34A02177C | `quantide/web/pages/system/runtime_monitor.py` | spec | v0.2-003 requires runtime failure reason through state/row/risk event or ErrorEnvelope; swallowing exceptions into success-shaped content is an implementation defect. |
| SAGE-PROD-2FA210E1DBF4 | `quantide/web/pages/trade_main.py` | interfaces | v0.2-002 OrderRequest/Response and `/trade/order` validation are canonical; unknown side/mode cannot enter fallback branches. |
| SAGE-PROD-AEFE0EF82EDC | `quantide/web/services/account_overview.py` | spec | v0.2-002 account overview requires `strategy_type` filtering; this v0.2 service is a required business-contract layer and ignored filtering/no integration are implementation defects. |
| SAGE-PROD-B54910B60313 | `quantide/web/services/accounts.py` | spec | v0.2-002 FR-0411 fixes account hide eligibility, including risk-control restrictions; declared-but-ignored fields and missing integration are defects. |
| SAGE-PROD-95733CA1182E | `quantide/web/services/auth_session.py` | spec | v0.2-003 keeps `web/services` DTO/pure policy contracts in scope; shipped auth must adapt to the locked login/session behavior rather than treating this as optional product scope. |
| SAGE-PROD-988B50E845F3 | `quantide/web/services/backtest_progress.py` | spec | v0.2-002 FR-0080/NFR-0060 requires bounded progress and re-entry; unconsumed service and values above 100 are implementation defects. |
| SAGE-PROD-76E0F28664F6 | `quantide/web/services/backtest_reports.py` | spec | v0.2-002 report sort/delete/confirmation behavior is locked; the service must be integrated and need not itself perform persistence deletion. |
| SAGE-PROD-B04F16F9FE6B | `quantide/web/services/dashboard.py` | spec | v0.2-002 FR-0201~0203 fixes dashboard ViewModel behavior; independent root rendering must consume/adapt it. |
| SAGE-PROD-798CA7E2A24E | `quantide/web/services/gateway.py` | spec | v0.2-002 FR-0340 makes this validator/test-before-save policy normative; the shipped page bypass is an implementation defect. |
| SAGE-PROD-D848F8E3739F | `quantide/web/services/integrity.py` | spec | v0.2-003 FR-0503 explicitly includes integrity service/page output; missing producer/display integration is implementation work. |
| SAGE-PROD-A1B065322010 | `quantide/web/services/layout.py` | spec | v0.2-002 profile/password/sidebar persistence contracts govern; validation-only and absent localStorage/password integration are defects. |
| SAGE-PROD-29D92499D4A1 | `quantide/web/services/notifications.py` | spec | v0.2-002 FR-0450 requires subscription binding/persistence behavior; validation-only implementation is incomplete. |
| SAGE-PROD-856151242B3E | `quantide/web/services/risk_events.py` | spec | v0.2-002 risk-event filtering and v0.2-001 excess-return windows govern; runtime/page DTO mismatch is an implementation defect. |
| SAGE-PROD-5A3EA0494ADF | `quantide/web/services/routing.py` | interfaces | v0.2-002 route table fixes `/wizard`, `/login`, `/dashboard` and safe-next behavior; policy literals and app routing must converge to it. |
| SAGE-PROD-2D8079C7B50C | `quantide/web/services/runtime_control.py` | spec | v0.2-002 runtime/backtest/promotion rules are normative; integration through an otherwise unconsumed scheduling model is implementation work. |
| SAGE-PROD-8A5063510667 | `quantide/web/services/scheduling.py` | spec | v0.2-002 strategy scheduling/list/filter contracts require this ViewModel behavior; lack of a production importer is an implementation gap, not deletion authority. |
| SAGE-PROD-0BCC092FC87F | `quantide/web/services/stock_query.py` | interfaces | `/system/stocks` search and K-line routes are canonical; this DTO/predicate module must back or adapt to those routes and is not a separate product API. |
| SAGE-PROD-D105BD52BCFB | `quantide/web/services/strategy_management.py` | spec | v0.2-002 FR-0010~0013 and v0.2-003 FR-0504 make this policy normative; shipped `/strategy` divergence is implementation work. |
| SAGE-PROD-FF6EA2D19774 | `quantide/web/services/tasks.py` | spec | v0.2-002 task-management and v0.2-003 system-page contracts govern; `/system/jobs` must adapt rather than leave this service test-only. |
| SAGE-PROD-60A64D86FC7A | `quantide/web/services/trade_history.py` | interfaces | v0.2-002 `/trade/orders` and `/trade/trades` filters, including `from/to`, are canonical; pages must consume/adapt this filter contract. |
| SAGE-PROD-DDE49EED52E7 | `quantide/web/services/trade.py` | interfaces | v0.2-002 OrderRequest board-lot/strategy validation is canonical; shipped order handlers bypassing it are implementation defects. |

## Resolution counts

- Resolved by locked spec/acceptance: **33**
- Resolved by interfaces: **16**
- Resolved by story: **0**
- Resolved by actual public consumers: **1**
- Resolved by current compatibility behavior: **5**
- Promoted to new Aaron decision: **0**
- Total additional candidates: **55**

## Final Aaron-decision set

No additional candidate requires a user-observable product choice after precedence review. Aaron resolved the exact final set—`AD-01` through `AD-06`—as **RETAIN** on 2026-07-13. The resolution does not approve deletion, waiver, quarantine, redirect, or invented replacement behavior.

## Normative test trace and M-DEV binding

The corrected test index/shards already materialize all function dispositions; no external generic overlay is required. Every one of 1651 functions has at least one spec-qualified AC reference. The final distribution is 1455 aligned and 196 update, with quality findings 87 incomplete, 61 self-fulfilling, 41 import-only, 3 fake, 2 conflicting and 2 spec-gap.

`recovery/devon-work-items.json` is normative M-DEV input. Its 196 unique open `RW-*` records bind the 196 update function IDs exactly once each. A work item is complete only with AC-derived Red, Green, and full isolated suite/per-file gate evidence for the same traceable revision, or when superseded by a bidirectionally linked replacement that carries the same function ID, AC refs and evidence obligations. GitHub issue/list completion alone is not DoD, and no update binding authorizes deletion.

## Aaron RETAIN resolution — 2026-07-13

Aaron resolved the final six decision candidates as **RETAIN**. The corrected shard row remains the governing current-implementation contract. Tests must be added for the current implementation contract, not invented behavior. Every row requires: a failing Red test referencing that current behavior; Green asserting the same behavior under isolation/determinism; a green same-revision full-suite run with `--timeout`; `percent_covered >=80.0`; no coverage tricks or broad exclusions. No waiver is approved.

| ID | Status | decision | approved_by | approved_at | Corrected-shard evidence | Current-implementation contract implication | Required evidence |
|---|---|---|---|---|---|---|---|
| AD-01 | RESOLVED | RETAIN | Aaron | 2026-07-13 | `prod-f4c5b6766c15`; `admin_routes.py:14-294,779-783` | Default app keeps admin routes unregistered; explicit `include_admin=True` keeps the coded GET/POST registrar, current role-guard asymmetry, HTML/303 fallbacks, and no transaction cleanup. | Red against that enable/disable behavior; isolated deterministic Green for the same behavior; green full suite with `--timeout`; file `>=80.0%`. |
| AD-02 | RESOLVED | RETAIN | Aaron | 2026-07-13 | `prod-2222692b50e2`; `forms.py:51-727` | Login/profile and gated legacy renderers keep their coded FastHTML fields/actions/errors; the module registers no route and performs no auth decision/persistence. | Red against current rendered output; isolated deterministic Green for the same output; green full suite with `--timeout`; file `>=80.0%`. |
| AD-03 | RESOLVED | RETAIN | Aaron | 2026-07-13 | `prod-5793dc5849e8`; `repository.py:5-209` | Current lookup/hash/authentication/CRUD/search/list/count, `last_login` update, last-admin refusal, and coded exception fallbacks remain. | Red against a current repository outcome; isolated deterministic-storage Green for the same outcome; green full suite with `--timeout`; file `>=80.0%`. |
| AD-04 | RESOLVED | RETAIN | Aaron | 2026-07-13 | `prod-478f19f91ad5`; `auth/utils.py:8-48` | Current token length/random alphabet, source email regex, password result/messages, username sanitization, negative-length empty token, and propagating type/regex errors remain. | Red against those current values/errors; deterministic-randomness Green for the same behavior; green full suite with `--timeout`; file `>=80.0%`. |
| AD-05 | RESOLVED | RETAIN | Aaron | 2026-07-13 | `prod-5c4b6a15a6b7`; `core/utils.py:7-40` | Five pure helpers keep strict 8/14-character parsing, zero-padded formatting, minute seconds `00`, and current `ValueError`/`AttributeError` boundaries. | Red against those conversions/errors; isolated deterministic Green for the same behavior; green full suite with `--timeout`; file present in manifest and `>=80.0%`. |
| AD-06 | RESOLVED | RETAIN | Aaron | 2026-07-13 | `prod-da64e6c5652e`; `analysis.py:15-74`; `app_factory.py:409` | Authenticated `GET /analysis` remains the current HTTP 200 HTML retirement notice, with optional session header state and no analysis data I/O. | Red against that current response; isolated deterministic branding/session Green for the same response; green full suite with `--timeout`; file `>=80.0%`. |

The final Aaron-decision set is now six resolved RETAIN decisions and zero unresolved decisions. `coverage-waivers.json` remains an empty registry.
