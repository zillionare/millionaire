# Aaron decision record — AD-01..AD-06

> Aaron decided on 2026-07-13 that all six legacy files are **RETAIN**. This record does not approve a waiver or change production behavior. Tests must be added for the current implementation contract, not invented behavior.

## Decision AD-07 (added 2026-07-13) — Protocol file coverage

**Scope.** Three Protocol declaration files in `quantide/core/ports/`:
- `clock.py` (ClockPort) — current coverage 73%
- `data_fetcher.py` (DataFetcherPort) — current coverage 65%
- `market_data.py` (MarketDataPort) — current coverage 62%

**Decision.** **Protocol-waive** the 80% per-file threshold for these three files. The remaining statements are the literal `...` (Ellipsis) method bodies that the `typing.Protocol` grammar requires; they are not executable. The per-file coverage floor of 80% applies to **executable statements**, not to Protocol placeholders. All executable statements (the `def` method signatures and protocol class definition) are reached and covered; the corresponding conformance is verified by the 26 hand-written fake tests under `tests/unit/quantide/core/ports/test_protocol_structural.py`.

**Conformance verification (C1.2).**
- `test_port_protocols_expose_the_documented_structural_method_sets` (FR-0207 AC-1/3/5): every required method exists on each Protocol.
- `test_protocol_method_bodies_are_pass_placeholders` (FR-0207 AC-10): documents the `...` body convention.
- `test_fake_implementations_pass_protocol_conformance` (FR-0207 AC-11): every fake exposes the full method set consumers rely on.
- 8 ClockPort / DataFetcherPort / MarketDataPort behavior tests plus 9 enum + structural tests cover the surface.

**Constraints.** This waiver does NOT cover:
- v0.2-added production files (>=95% target, no waiver).
- Pre-v0.2 retained files that are not Protocols (>=80% target, must be hit by tests or by a future per-file waiver following FR-1801).
- Implementations of any of these protocols, when added later — those must hit >=80%.

**approved_by:** Aaron
**approved_at:** 2026-07-13
**evidence:** `tests/unit/quantide/core/ports/test_protocol_structural.py` (28 tests, all green); C1.2 commit `e1ed126`.

## Resolution summary

| ID | Exact path | Status | Decision | approved_by | approved_at | Corrected-shard evidence | Coverage target |
|---|---|---|---|---|---|---|---|
| AD-01 | `quantide/web/auth/admin_routes.py` | RESOLVED | RETAIN | Aaron | 2026-07-13 | `quantide-web-01.json`, `prod-f4c5b6766c15`, source anchors `admin_routes.py:14-294,779-783` | `percent_covered >=80.0` |
| AD-02 | `quantide/web/auth/forms.py` | RESOLVED | RETAIN | Aaron | 2026-07-13 | `quantide-web-01.json`, `prod-2222692b50e2`, source anchors `forms.py:51-727` | `percent_covered >=80.0` |
| AD-03 | `quantide/web/auth/repository.py` | RESOLVED | RETAIN | Aaron | 2026-07-13 | `quantide-web-01.json`, `prod-5793dc5849e8`, source anchors `repository.py:5-209` | `percent_covered >=80.0` |
| AD-04 | `quantide/web/auth/utils.py` | RESOLVED | RETAIN | Aaron | 2026-07-13 | `quantide-web-01.json`, `prod-478f19f91ad5`, source anchors `utils.py:8-48` | `percent_covered >=80.0` |
| AD-05 | `quantide/core/utils.py` | RESOLVED | RETAIN | Aaron | 2026-07-13 | `quantide-core-02.json`, `prod-5c4b6a15a6b7`, source anchors `utils.py:7-40` | `percent_covered >=80.0` and present in the coverage manifest |
| AD-06 | `quantide/web/pages/analysis.py` | RESOLVED | RETAIN | Aaron | 2026-07-13 | `quantide-web-02.json`, `prod-da64e6c5652e`, source anchors `analysis.py:15-74`; route `app_factory.py:409` | `percent_covered >=80.0` |

## Evidence contract applying to every retained row

- **Required Red evidence:** a failing test that references and expects the row's current-implementation behavior below. A failure caused only by an invented expectation, coverage threshold, import error, or unrelated setup does not qualify.
- **Required Green evidence:** the same test passes while asserting the same behavior under isolated and deterministic dependencies/state.
- **Required full-suite regression evidence:** the same traceable revision records a green full-suite run, with the normative `--timeout` option, in the same accepted coverage run used for the per-file threshold.
- **Threshold:** each executable retained file must report `percent_covered >=80.0`; no threshold is loosened.
- **Test direction:** tests must be added for the current implementation contract, not invented behavior.
- **Prohibitions:** follow current implementation; no invented behavior; no coverage tricks; no broad exclusions. `coverage-waivers.json` remains empty.

## AD-01 — optional multi-user admin registrar

- **decision:** RETAIN
- **approved_by:** Aaron
- **approved_at:** 2026-07-13
- **governing contract:** Retain `AdminRoutes(auth_manager)` and its optional registrar exactly as recorded in corrected shard `prod-f4c5b6766c15`. The shipped app leaves `include_admin=False`, so the default app has no admin routes. Explicit `include_admin=True` registers the coded GET/POST user list/create/edit/delete handlers and preserves the current decorator asymmetry, HTML results, query-string 303 error redirects, and absence of transaction cleanup.
- **required evidence:** Red must fail while referencing this default-disabled/explicitly-enabled route behavior; Green must assert that same behavior with isolated auth/repository state; the same revision must have a green full suite with `--timeout` and this file at `>=80.0%`.
- **test-direction:** tests must be added for the current implementation contract, not invented behavior; follow current implementation; no coverage tricks; no broad exclusions.

## AD-02 — mixed active and legacy auth form renderers

- **decision:** RETAIN
- **approved_by:** Aaron
- **approved_at:** 2026-07-13
- **governing contract:** Retain the current FastHTML renderers in corrected shard `prod-2222692b50e2`: active login/profile forms emit their coded actions, fields, selected login errors, redirect field, and password/profile fields; registration/forgot/reset forms remain gated legacy renderers; `create_message_alert` remains a renderer helper; this module registers no route and performs no persistence or auth decision.
- **required evidence:** Red must fail while referencing those current rendered nodes/fields/actions; Green must assert the same output under deterministic isolated rendering; the same revision must have a green full suite with `--timeout` and this file at `>=80.0%`.
- **test-direction:** tests must be added for the current implementation contract, not invented behavior; follow current implementation; no coverage tricks; no broad exclusions.

## AD-03 — consumed authentication repository

- **decision:** RETAIN
- **approved_by:** Aaron
- **approved_at:** 2026-07-13
- **governing contract:** Retain `UserRepository` as recorded in corrected shard `prod-5793dc5849e8`: parameterized username lookup; hashing during create and non-hash password update; authentication updates `last_login` and returns the pre-update user; CRUD/search/list/count produce the coded mutations and materialized values; last-admin deletion is refused; coded broad exceptions return `None`, `False`, empty collections, or zero counts, while create/password-verification failures may propagate.
- **required evidence:** Red must fail while referencing one of these current repository outcomes/fallbacks; Green must assert the same outcome against isolated deterministic storage; the same revision must have a green full suite with `--timeout` and this file at `>=80.0%`.
- **test-direction:** tests must be added for the current implementation contract, not invented behavior; follow current implementation; no coverage tricks; no broad exclusions.

## AD-04 — unconsumed auth helper module

- **decision:** RETAIN
- **approved_by:** Aaron
- **approved_at:** 2026-07-13
- **governing contract:** Retain the four source callables from corrected shard `prod-478f19f91ad5`: `generate_token` returns a random alphanumeric string of requested length and returns empty for a negative length; `validate_email` applies the source regex; `validate_password` requires non-empty input, length at least 8, a digit, and uppercase and returns the coded `(bool, message)`; `sanitize_username` removes non-alphanumeric/non-underscore characters and lowercases; regex/type errors propagate. The module has no product route, facade export, persistence, or cleanup.
- **required evidence:** Red must fail while referencing those current values/errors; Green must assert the same behavior with randomness controlled and all state isolated; the same revision must have a green full suite with `--timeout` and this file at `>=80.0%`.
- **test-direction:** tests must be added for the current implementation contract, not invented behavior; follow current implementation; no coverage tricks; no broad exclusions.

## AD-05 — legacy date/time conversion helpers

- **decision:** RETAIN
- **approved_by:** Aaron
- **approved_at:** 2026-07-13
- **governing contract:** Retain all five pure helpers from corrected shard `prod-5c4b6a15a6b7`: `str2date` accepts exactly 8 `YYYYMMDD` characters; `str2time` accepts exactly 14 `YYYYMMDDhhmmss` characters; formatters zero-pad to 8/14 digits; `time2minute` forces seconds to `00`; wrong lengths, non-digits, and invalid calendar values raise `ValueError`; missing object fields raise `AttributeError`; there is no mutation or cleanup.
- **required evidence:** Red must fail while referencing those current conversions or built-in failures; Green must assert the same pure deterministic behavior in isolation; the same revision must have a green full suite with `--timeout`, the file present in the coverage manifest, and this file at `>=80.0%`.
- **test-direction:** tests must be added for the current implementation contract, not invented behavior; follow current implementation; no coverage tricks; no broad exclusions.

## AD-06 — registered analysis retirement notice

- **decision:** RETAIN
- **approved_by:** Aaron
- **approved_at:** 2026-07-13
- **governing contract:** Retain corrected shard `prod-da64e6c5652e`: authenticated `GET /analysis` calls the current renderer and returns HTTP 200 HTML stating sector/index analysis is retired while pointing to the remaining stock/strategy/paper/gateway-live paths. Optional session auth affects header display; the page accepts no query/form input, performs no analysis data read/write, and has no event or cleanup behavior.
- **required evidence:** Red must fail while referencing that current routed HTTP response/message; Green must assert the same response under isolated deterministic branding/session state; the same revision must have a green full suite with `--timeout` and this file at `>=80.0%`.
- **test-direction:** tests must be added for the current implementation contract, not invented behavior; follow current implementation; no coverage tricks; no broad exclusions.

## Final disposition

All six rows are **RESOLVED RETAIN**. No file is deleted, quarantined, redirected, promoted to new behavior, or waived. The empty waiver registry is authoritative.

---

# Aaron decision record — v0.2-004 release-package resolution (2026-07-17)

These four items resolve the open contradictions (SC-01..SC-04) and the package-level release gates. They were decided in conversation on 2026-07-17 and are recorded here as authoritative for v0.2-004.

## SC-01 — Coverage release metric

- **decision:** Use `coverage.json.totals.percent_covered` (combined statement + branch) as the single release metric.
- **approved_by:** Aaron
- **approved_at:** 2026-07-17
- **rationale:** Branch coverage is enabled in `pyproject.toml` (`branch = true`); the combined metric is the only single source of truth that does not let statement/line pass while the executable gate fails. The strict threshold remains `> 95.0`.
- **binding:** `spec.md` NFR-1001, `acceptance.md` AC-NFR1001-01, `interfaces.md` §2, `tests/unit/_checkers/per_file_coverage.py`, `.github/workflows/unit-coverage.yml`, and the evidence schema must all reference `totals.percent_covered` and use `> 95.0`.
- **prohibition:** No `--force` or `--fail-under` override is permitted for release evidence.

## SC-02 — RW registry model (planning vs. exit)

- **decision:** Keep `recovery/devon-work-items.json` as the immutable, hash-pinned planning baseline containing the 196 open `RW-*` work items. Add a separately versioned runtime/exit registry that records closed/superseded state and Red/Green/full-suite evidence.
- **approved_by:** Aaron
- **approved_at:** 2026-07-17
- **rationale:** The pinned planning file preserves the original 196 work items for audit; a separate, versioned runtime registry avoids mutating the pinned hash and provides the closed/superseded state the exit verifier needs.
- **binding:** The exit verifier validates both the immutable baseline pin and the runtime/exit registry closure state. `tests/unit/_checkers/exit_evidence.py` must fail closed if either is missing or inconsistent.
- **schema note (deferred):** The runtime/exit registry schema, atomic-write semantics, and supersession rules will be defined in a follow-up versioned transition. The pinned planning file must not be mutated in place.

## SC-03 — Candidate/waiver truth and AD-07 status

- **decision (A, with AD-07 qualification):** Treat the 55 `pending` Sage candidate statuses and the prior closure blocking summary as stale diagnostic history. The new authoritative truth is the 55-row resolution table recorded in `recovery/sage-semantic-review.md` (Sage 2026-07-13), where every candidate maps to a higher-priority spec, the current-implementation contract, or an external consumer, and is not release-blocking on its own.
- **AD-07 is preserved** as a **Protocol-waive** (not a coverage waiver). It applies to the three Protocol declaration files in `quantide/core/ports/` (`clock.py`, `data_fetcher.py`, `market_data.py`); the 80% per-file floor applies to executable statements only, not to the `...` (Ellipsis) placeholders required by `typing.Protocol`. Conformance is verified by `tests/unit/quantide/core/ports/test_protocol_structural.py`.
- **approved_by:** Aaron
- **approved_at:** 2026-07-17
- **binding:**
  - `coverage-waivers.json` remains empty. AD-07 is not a coverage waiver and must never be inserted there.
  - Evidence schemas and the exit verifier must distinguish Protocol waivers from coverage waivers.
  - The next repin of `recovery/production-file-inventory.json`, `recovery/coverage-closure.json`, and any closure matrix must use the 55-row Sage resolution as the live truth and drop the 55 `pending` labels.
  - The AD-07 evidence pointer (`test_protocol_structural.py`, 28 tests, all green) and its conformance details remain authoritative for the Protocol files.

## SC-04 — Strategy callback contract

- **decision:** Canonical API is `BaseStrategy.on_bar(tm)`. `BacktestRunner` and `StrategyRuntime` must call `await strategy.on_bar(tm)`. Strategies pull data through `get_bars(..., frame_type=...)`; `on_bar` does not receive `quote` or `frame_type` arguments.
- **approved_by:** Aaron
- **approved_at:** 2026-07-17
- **rationale:** The locked v0.2-001 strategy-framework contract specifies a pull-based, time-driven `on_bar` with no quote payload; the three-argument call site in the runtime is the deviation, not the strategy implementations.
- **binding:**
  - Update `quantide/service/runner.py` to call `strategy.on_bar(bar_tm)`.
  - Update `quantide/service/strategy_runtime.py` to call `strategy.on_bar(now)`.
  - Before each callback, set `strategy._current_time`, broker clock, and any required market-data state.
  - Update test-only three-argument strategies and direct E2E callback invocations to the single-argument API.
  - Do not add signature introspection or dual-dispatch compatibility in production code.
- **existing production impact:**
  - `DualMAStrategy` already implements `on_bar(tm)` and will run once the runner call is corrected.
  - `CostStopLossStrategy` and `PullbackSellStrategy` use `on_check(positions, tm)` and are unaffected.
  - User-authored three-argument strategies in the wider ecosystem are a migration break; document the API change in the next version notes and do not silently re-enable the legacy signature.
- **separate known gap (not caused by SC-04):** `PaperBroker.get_history()` currently supports only `1d`, and `StrategyRuntime` does not yet implement correct 30m boundary driving. Paper/live 30m pull-based strategies remain an independent implementation task.

## Release-package resolution (binding summary)

1. SC-01: combine statement+branch is the only release metric; threshold strictly `> 95.0`.
2. SC-02: planning registry stays immutable; a separately versioned runtime/exit registry holds closed/superseded state and evidence.
3. SC-03: 55 Sage candidate `pending` statuses are stale; AD-07 is a Protocol-waive, not a coverage waiver; `coverage-waivers.json` remains empty.
4. SC-04: `on_bar(tm)` is canonical; runners/runtimes use the single-argument API; data is pulled through `get_bars(..., frame_type=...)`.

These decisions are authoritative for v0.2-004 and must be reflected in the next versioned repin of the affected artifacts (`spec.md`, `acceptance.md`, `interfaces.md`, `test-plan.md`, the coverage/per-file/waiver/source-manifest checkers, `recovery/sage-semantic-review.md`, and the next repin of the production inventory and trace).
