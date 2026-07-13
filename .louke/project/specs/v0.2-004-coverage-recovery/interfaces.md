# Millionaire Coverage Recovery — Interface Contracts

- **Spec ID**: `v0.2-004-coverage-recovery`
- **阶段**: M-ARCH
- **范围**: recovery CLI、JSON artifacts、exit evidence；业务 API 继续由 v0.2-001/002/003 interfaces 与 fixed corrected shards 定义
- **规则**: 本文件只列外部可观察 contract；所有路径相对 repository root；所有失败返回非零 exit 并输出 machine-readable reason

## Interfaces Scope / 接口范围

- 接口类型：CLI command、data schema、file format、process exit code；本 recovery 不新增 API endpoint、public business function 或 log event。
- 包含：canonical pytest invocation、coverage/per-file/source-manifest gates、固定 artifact readers、RW registry writer、waiver schema、evidence package 与 binary verifier。
- 继承：业务 Python/HTTP/event/data contracts 来自 v0.2-001/002/003 `interfaces.md` 与 13 个 fixed corrected production shards。
- 排除：内部类层次、私有方法、调度状态机、缓存/数据库实现、未来业务 API。

## 1. Test framework command

| Contract | Value |
|---|---|
| Canonical command | `poetry run pytest tests/unit --cov=quantide --cov-fail-under=95 --timeout=60 -o faulthandler_timeout=90 --cov-report=term-missing --cov-report=json:coverage.json --cov-report=html:htmlcov` |
| Required environment | `HOME=<run_tmp>/home`, `XDG_CONFIG_HOME=<run_tmp>/xdg`, application config/data/db/log/pid paths under `<run_tmp>`, `COVERAGE_PROCESS_START=pyproject.toml` |
| Success | exit `0`; pytest `failed=0`, `errors=0`; generated `coverage.json` and `htmlcov/` |
| Coverage acceptance | only artifacts from this exit-0 invocation; `coverage.json.totals.percent_covered > 95.0` |
| Failure | nonzero exit or any failed/error; generated coverage is `diagnostic`, never accepted |
| Config source | `pyproject.toml [tool.pytest.ini_options]` and `[tool.coverage.*]`; no alternate pytest config |

## 2. Per-file checker command

```bash
poetry run python tests/unit/_checkers/per_file_coverage.py \
  coverage.json \
  .louke/project/specs/v0.2-004-coverage-recovery/coverage-waivers.json \
  --inventory .louke/project/specs/v0.2-004-coverage-recovery/recovery/production-file-inventory.json \
  --report artifacts/coverage-recovery/$RUN_ID/per-file-coverage.json
```

| Input/exit | Contract |
|---|---|
| `coverage.json` | pytest-cov JSON from canonical exit-0 run; required `totals` and `files` |
| inventory | exact index hash `8410d32fb4b64c0d38ef21f947c45be7164185dcaa09f36a7061bc99b9c8bfbe`; classification/origin is authoritative |
| Success exit `0` | overall `>95.0`; all v0.2-added executable rows `>=95.0`; all retained pre-v0.2 executable rows `>=80.0` or one valid waiver; 0-statement rows marked `threshold_not_applicable`; 169 report rows |
| Failure exit nonzero | missing/extra/duplicate path; executable file absent from coverage; overall `<=95.0`; below target; invalid waiver; malformed input |
| Output | JSON object with `schema`, `spec_id`, `run_id`, `coverage_sha256`, `inventory_sha256`, `overall`, `rows[169]`, `counts`, `verdict`, `reasons` |
| Row fields | `path`, `classification`, `origin`, `num_statements`, `covered_lines`, `percent_covered`, `target`, `threshold_applicable`, `waiver_id|null`, `status`, `reasons[]` |

## 3. Recovery artifact reader command

```bash
poetry run python tests/unit/_checkers/recovery_artifacts.py verify \
  --spec-dir .louke/project/specs/v0.2-004-coverage-recovery \
  --report artifacts/coverage-recovery/$RUN_ID/recovery-hashes.json
```

| Artifact | Exact SHA-256 / manifest SHA-256 | Required reconstruction |
|---|---|---|
| `recovery/production-file-inventory.json` | `8410d32fb4b64c0d38ef21f947c45be7164185dcaa09f36a7061bc99b9c8bfbe` | 13 shards、169 unique path/record id、169 source-grounded、0 pseudo-import API、0 mangled signature、0 missing anchor |
| production shard manifest | `4ec8dbdbf8eaabfe1d8a355df778ae438e03b6dc3b18b0038955ba91472cac39` | canonical JSON `shards` array in lexicographic shard-path order |
| `recovery/test-trace-data.json` | `3d7ebc07cc8d014aab8981c025a142f1112c7d7cfb05390254de02c19da38fd0` | 11 shards、240 modules、1651 functions、1455 aligned、196 update、0 needs-Sage-contract |
| test shard manifest | `f48b15e808737352ad6a5c4d8da2b2a5f9b97fa3fb56a4ca2881463ec2380352` | canonical JSON `shards` array in lexicographic shard-path order |
| `recovery/devon-work-items.json` input | `bac42a69bcd6359afe16fbcdc8ae710314ad00ced431dff9c1625186cb2bd088` | 196 unique open RW、196 unique update function、one-to-one difference/duplicates=0 |

| Hash rule | Contract |
|---|---|
| Index/registry hash | SHA-256 of exact file bytes |
| Individual shard hash | SHA-256 of exact shard bytes; compare index row `sha256` |
| Record hash | compact UTF-8 JSON, recursively sorted object keys, array order preserved |
| Manifest hash | compact UTF-8 canonical JSON of `shards` array sorted lexicographically by `path` |
| Verification failure | missing shard, byte hash/count/id/path mismatch, duplicate/missing record, pin mismatch → nonzero exit; no automatic repin |
| Report fields | `schema`, `spec_id`, `checked_at`, `artifacts[] {path, expected_sha256, actual_sha256, status}`, `reconstructions`, `verdict`, `reasons[]` |

## 4. Source-manifest equality command

```bash
poetry run python tests/unit/_checkers/source_manifest.py check \
  --source quantide \
  --inventory .louke/project/specs/v0.2-004-coverage-recovery/recovery/production-file-inventory.json \
  --coverage coverage.json \
  --report artifacts/coverage-recovery/$RUN_ID/source-manifest.json
```

| Normalization | Contract |
|---|---|
| Disk set | every regular `quantide/**/*.py`, repository-relative POSIX path; includes `__init__.py`, marker and 0-statement files |
| Inventory set | all reconstructed production shard row `path` values; not index summary text |
| Coverage set | normalized `coverage.json.files` keys under `quantide/` |
| Success exit `0` | `disk == inventory == coverage`; each count `169`; duplicate/missing/extra counts `0` |
| Failure exit nonzero | any inequality, malformed path, duplicate path, executable file without coverage record |
| Output fields | `schema`, `run_id`, `commit_sha`, `disk`, `inventory`, `coverage`, `counts`, `disk_minus_inventory`, `inventory_minus_disk`, `inventory_minus_coverage`, `coverage_minus_inventory`, `pins`, `verdict` |

## 5. Devon RW registry writer contract

```bash
poetry run python tests/unit/_checkers/rw_registry.py close \
  --registry .louke/project/specs/v0.2-004-coverage-recovery/recovery/devon-work-items.json \
  --work-item RW-NNNN \
  --evidence artifacts/coverage-recovery/$RUN_ID/rw/RW-NNNN.json
```

| Field | Type | Constraint |
|---|---|---|
| `work_item_id` | string | `^RW-[0-9]{4}$`; exists exactly once |
| `status` | enum | input `open`; output `closed` or `superseded` only |
| `function_ids` | string array | exactly one update function for v1 registry; unchanged on close |
| `test_modules` | string array | nonempty and contains bound function module |
| `production_targets` | string array | nonempty; path exists or is the single explicit infra target |
| `defect_category`, `quality_finding` | enum/string | unchanged from pinned input |
| `ac_refs` | string array | nonempty, spec-qualified, unchanged unless trace artifact is synchronously reviewed |
| `red` | object | AC-derived failing command, exit, assertion, revision, artifact hash; unrelated/import/threshold failures invalid |
| `green` | object | same behavior/function; isolated command exit 0; independent assertion; artifact hash |
| `full_suite` | object | canonical command, same revision, exit 0, summary, coverage hash, per-file report hash |
| `superseded_by` | string/null | required only for `superseded`; replacement has reciprocal `supersedes` and inherits all obligations |
| Write semantics | rule | validate all 196 bindings before and after; write temporary file, fsync, atomic replace; on failure leave bytes unchanged |
| Success output | JSON stdout | `work_item_id`, `old_status`, `new_status`, `registry_sha256`, `evidence_sha256`, `verdict=pass` |
| Failure output | JSON stderr | `verdict=fail`, nonempty `reasons[]`; nonzero exit |

## 6. Subprocess coverage setup

| Interface | Value/constraint |
|---|---|
| Parent env | `COVERAGE_PROCESS_START=pyproject.toml` |
| Coverage config | `source=["quantide"]`, `branch=true`, `parallel=true`, multiprocessing/subprocess support compatible with installed coverage.py |
| Worker behavior | inherits env/config; writes parallel data on normal/managed shutdown |
| Merge ownership | pytest-cov in the same canonical invocation; one final `coverage.json` |
| Required assertion | known worker-executed lines attributed to `quantide/service/grid_search.py`; no live ProcessPool worker after teardown |
| Prohibited substitute | in-process/synchronous monkeypatch of worker pool for accepted subprocess coverage |
| Failure | missing worker attribution, unmerged data, live worker, or cross-run combine → accepted run FAIL |

## 7. AC namespace allocation

| Spec | Reserved/used namespace | Collision rule |
|---|---|---|
| v0.2-001-strategy-framework | legacy 3-digit business IDs and its published AC tokens | cross-spec references include `v0.2-001-strategy-framework` |
| v0.2-002-ui | `FR-0010..FR-0460`, `NFR-0010..NFR-0070` and published AC tokens | cross-spec references include `v0.2-002-ui` |
| v0.2-003-coverage | `FR-0001`, `FR-0101..FR-0703`, `NFR-0010..NFR-0030` | cross-spec references include `v0.2-003-coverage` |
| v0.2-004-coverage-recovery | `AC-FR1001-01..AC-FR1901-03`; `AC-NFR1001-01..AC-NFR1301-02` as enumerated in acceptance | only IDs present in `acceptance.md` are valid; total 64; no `AC-FR0801-*`/`AC-FR0802-*` aliases created |
| Story compatibility labels | `FR-0801`, `FR-0802` | non-AC aliases only; map through architecture §2.1 and never appear as unqualified test anchors |

## 8. Waiver registry schema

```json
{
  "schema": "coverage-waivers/v1",
  "spec_id": "v0.2-004-coverage-recovery",
  "waivers": [
    {
      "module": "quantide/path/file.py",
      "current_coverage": 79.5,
      "reason": "file-specific blocker",
      "evidence": ["artifacts/coverage-recovery/<run_id>/..."],
      "approved_by": "Aaron",
      "approved_at": "2026-07-13T00:00:00Z",
      "expires_at": "2026-07-27T00:00:00Z",
      "followup_issue": "https://github.com/zillionare/millionaire/issues/NNN"
    }
  ]
}
```

| Rule | Required result |
|---|---|
| Current registry | `waivers=[]`; AD-01..AD-06 have no waiver |
| Eligible module | unique retained pre-v0.2 path present in fixed production inventory |
| Ineligible | any v0.2-added path, unknown/duplicate path, generic glob/family/module prefix |
| Required fields | `module`, `current_coverage`, `reason`, `evidence`, `approved_by`, `approved_at`, `expires_at`, `followup_issue` |
| Approval | exact `approved_by="Aaron"`; valid timestamps; unexpired at run time |
| Evidence/issue | nonempty evidence paths/hashes; HTTPS GitHub issue URL |
| Failure | missing field, invalid type/range/time, non-Aaron, expired, duplicate, unknown, v0.2-added, generic waiver → nonzero exit and module-specific reason |
| Prohibited bypass | no `--force`; no generic waiver; no omit/exclude expansion |

## 9. Evidence-package writer contract

```bash
poetry run python tests/unit/_checkers/evidence_package.py write \
  --run-id "$RUN_ID" \
  --output "artifacts/coverage-recovery/$RUN_ID" \
  --coverage coverage.json \
  --spec-dir .louke/project/specs/v0.2-004-coverage-recovery
```

| Output path | Required fields/content |
|---|---|
| `run.json` | `schema`, `spec_id`, `run_id`, full `commit_sha`, `dirty`, UTC timestamps, Python/pytest/pytest-cov/coverage versions, exact command, allowlisted env, pytest exit and summary |
| `coverage.json` | byte-for-byte accepted pytest-cov output |
| `coverage.sha256` | lowercase 64-char SHA-256 + two spaces + `coverage.json` + newline |
| `source-manifest.json` | §4 fields; all sets/counts/diffs; production pins |
| `per-file-coverage.json` | §2 report; 169 rows and counts |
| `waiver-validation.json` | waiver file SHA-256, evaluated rows, invalid count, verdict |
| `trace-matrix.json` | 64 AC outlets, 1651 test functions, 196 update/RW bindings/status, test/RW pins, orphan counts |
| `anti-patterns.json` | scanned paths, config diff baseline, findings by category, blocking count |
| `aaron-decisions.json` | AD id/path/decision/approver/date/shard record/current contract/R-G-F hashes/per-file result |
| `closure-summary.json` | iteration, blocker category counts, total blockers, unique `PASS|FAIL`, reasons |
| `required-check.json` | #118 availability, check name, conclusion, commit SHA, URL; required when capability ships |
| `manifest.json` | `schema`, `spec_id`, `run_id`, `commit_sha`, sorted `files[] {path,size,sha256}`, `manifest_sha256` |

| Hashing/writing rule | Contract |
|---|---|
| File hash | SHA-256 of exact bytes after file close |
| Manifest order | relative POSIX path, lexicographic; manifest excludes its own `manifest_sha256` field while canonical hash is calculated |
| Canonical JSON | UTF-8, recursively sorted keys, compact separators for computed object hashes; emitted evidence may be pretty JSON but byte hash uses emitted bytes |
| Provenance | every derived file repeats `run_id`, `commit_sha`, source artifact hashes |
| Immutability | output directory must not pre-exist; atomic rename from sibling temporary directory; overwrite forbidden |
| Writer success | exit `0` only when every required input already has PASS and hashes agree |
| Writer failure | nonzero; no final output directory; reasons nonempty |

## 10. Exit evidence check command

```bash
poetry run python tests/unit/_checkers/exit_evidence.py verify \
  --package "artifacts/coverage-recovery/$RUN_ID" \
  --require-check unit-coverage \
  --report "artifacts/coverage-recovery/$RUN_ID/exit-verification.json"
```

| Signal | PASS condition |
|---|---|
| Full suite | canonical command exact match; exit 0; failed/errors 0 |
| Coverage | same run/revision; overall `>95.0`; coverage byte hash match |
| Manifest | disk=inventory=coverage=169; production pins match |
| Per-file | all applicable v0.2-added `>=95`; retained pre-v0.2 `>=80` or valid file waiver; AD files `>=80` |
| Waivers | registry valid; current accepted package expects empty unless Aaron-specific review exists |
| Trace | 64 AC covered; 1651 function refs; no orphan; 196 RW valid and closed/superseded with R/G/F |
| Anti-pattern | zero blocking findings; no broad exclusion/config weakening |
| Aaron | 6/6 `RESOLVED RETAIN`, current-implementation contract, no deletion/waiver |
| Closure | every blocker category 0; summary verdict PASS |
| Hashes | every manifest file byte hash and all fixed pins match |
| Required check | **once Louke issue #118 ships**: provider reports `unit-coverage` success for exact package commit SHA and supplies nonempty URL/id; before #118, field is explicit `unavailable_pending_issue_118` and cannot masquerade as verified |
| Command exit | `0` only if all currently enforceable signals PASS; after #118 ships, missing/failed/SHA-mismatched required check is blocking; otherwise nonzero with reasons |

## 11. AC trace and anti-pattern command

```bash
lk agent archer ci-scan \
  --acceptance .louke/project/specs/v0.2-004-coverage-recovery/acceptance.md \
  --tests tests/
```

| Output | Contract |
|---|---|
| Success | valid spec-qualified references; acceptance/test closure; no blocking anti-pattern finding |
| Failure | unknown/colliding AC, orphan acceptance/test, fake/import-only/pass/assert-true or other blocking pattern; nonzero exit |
| Runtime command rule | only `lk agent archer ci-scan ...`; deprecated top-level agent form is invalid |

## 12. AC outlet allocation

| Namespace | Count | Observable exit(s) |
|---|---:|---|
| `AC-FR1001-*` | 4 | recovery hash report + source-manifest report |
| `AC-FR1101-*` | 4 | production reconstruction classification rows |
| `AC-FR1201-*` | 7 | corrected contract reconstruction rows/reasons |
| `AC-FR1301-*` | 6 | quality report + RW binding report + anti-pattern report |
| `AC-FR1401-*` | 4 | RW writer output + R/G/F evidence hashes |
| `AC-FR1501-*` | 9 | Aaron decision rows + per-file results |
| `AC-FR1601-*` | 8 | test reconstruction + trace matrix + `ci-scan` exit |
| `AC-FR1701-*` | 3 | closure matrix/summary + generated blocker work links |
| `AC-FR1801-*` | 4 | waiver validation positive/negative outcomes |
| `AC-FR1901-*` | 3 | exit verifier PASS/FAIL and failure injection reasons |
| `AC-NFR1001-*` | 4 | accepted coverage + per-file + 0-statement rows |
| `AC-NFR1101-*` | 3 | anti-pattern/config-diff report |
| `AC-NFR1201-*` | 3 | isolation/determinism/resource/subprocess reports |
| `AC-NFR1301-*` | 2 | evidence manifest + replay verifier |

## 13. Binary failure rules

- Missing, empty, malformed, duplicate, unhashed, cross-revision or cross-run required field/artifact → FAIL.
- Failing pytest coverage, even above thresholds → diagnostic only and FAIL.
- A single below-target executable path without valid eligible waiver → FAIL.
- Any open/invalid 196 RW binding or nonzero closure blocker → FAIL.
- Any generic waiver, broad exclusion, fake test or invented RETAIN behavior → FAIL.
- No command supports `--force`, threshold reduction, issue-count override or manual PASS.
