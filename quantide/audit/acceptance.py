"""Machine-readable acceptance matrix for CE v0.4/v0.5 contracts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from quantide.audit.acceptance_v05 import _V05_EVIDENCE


@dataclass(frozen=True)
class AcceptanceEntry:
    ac: str
    requirement: str
    behavior: str
    evidence: tuple[str, ...] = ()
    status: str = "mapped"
    note: str = ""

    def as_dict(self, *, status: str | None = None) -> dict[str, Any]:
        return {
            "ac": self.ac,
            "requirement": self.requirement,
            "behavior": self.behavior,
            "evidence": list(self.evidence),
            "status": status or self.status,
            "note": self.note,
        }


T = "tests/unit/quantide"
A = f"{T}/audit"
S = f"{T}/service"
F = f"{T}/factors"
W = f"{T}/web/pages"

ENTRIES: tuple[AcceptanceEntry, ...] = (
    AcceptanceEntry(
        "AC-4001",
        "FR-4001",
        "period contracts and diagnostics",
        (f"{A}/test_audit_contracts.py", f"{S}/test_strategy_next_open_p0.py"),
    ),
    AcceptanceEntry(
        "AC-4002",
        "FR-4002",
        "future perturbation invariance",
        (f"{A}/test_future_perturbation.py", f"{A}/test_factor_audit.py"),
    ),
    AcceptanceEntry(
        "AC-4003",
        "FR-4002",
        "signal/model/cache future leakage",
        (f"{A}/test_mutations.py", f"{A}/test_future_perturbation.py"),
    ),
    AcceptanceEntry(
        "AC-4004",
        "FR-4003",
        "synthetic signal and null distribution",
        (f"{A}/test_synthetic.py", f"{A}/test_statistics.py"),
    ),
    AcceptanceEntry(
        "AC-4005",
        "FR-4003",
        "zero-drift control and matched benchmark",
        (f"{A}/test_synthetic.py",),
    ),
    AcceptanceEntry(
        "AC-4006", "FR-4004", "3x10 independent oracle", (f"{A}/test_three_by_ten_oracle.py",)
    ),
    AcceptanceEntry(
        "AC-4007",
        "FR-4004",
        "independent account oracle",
        (f"{A}/test_account_ledger.py", f"{A}/test_performance_attribution.py"),
    ),
    AcceptanceEntry(
        "AC-4008",
        "FR-4005",
        "ledger invariants and idempotency",
        (f"{A}/test_account_ledger.py", f"{S}/test_sim_broker_cleanup.py"),
    ),
    AcceptanceEntry(
        "AC-4009", "FR-4006", "key mutations killed with evidence", (f"{A}/test_mutations.py",)
    ),
    AcceptanceEntry(
        "AC-4010",
        "FR-4007",
        "account-fact attribution by asset/strategy",
        (f"{S}/test_attribution_facts.py",),
    ),
    AcceptanceEntry(
        "AC-4011",
        "FR-4007",
        "cash flow, split, dividend, Carino",
        (f"{A}/test_performance_attribution.py", f"{S}/test_attribution_facts.py"),
    ),
    AcceptanceEntry(
        "AC-4012",
        "FR-4007",
        "benchmark and separated SHAP",
        (f"{S}/test_attribution_facts.py", f"{S}/test_attribution.py"),
    ),
    AcceptanceEntry(
        "AC-4013",
        "FR-4008",
        "JSON/readable report fingerprint",
        (f"{A}/test_audit_contracts.py", f"{A}/test_factor_audit.py"),
    ),
    AcceptanceEntry(
        "AC-4014",
        "NFR-4001/2/4/5",
        "three-platform deterministic release gate",
        (".github/workflows/ci.yml", "scripts/check_test_results.py"),
        status="manual",
        note="platform runners execute on CI; local review did not publish",
    ),
    AcceptanceEntry(
        "AC-4015",
        "NFR-4003/6",
        "quality budgets and no real trading",
        (f"{A}/test_mutations.py", "tests/quality"),
    ),
    AcceptanceEntry(
        "AC-4016",
        "FR-4009",
        "custom panels and batch independence",
        (f"{F}/test_factor_research.py", f"{S}/test_factor_study.py"),
    ),
    AcceptanceEntry(
        "AC-4017",
        "FR-4009",
        "Pearson/Rank/ICIR and diagnostics",
        (f"{F}/test_factor_research.py", f"{S}/test_factor_tracking.py"),
    ),
    AcceptanceEntry(
        "AC-4018", "FR-4010", "1M only, forming/closed and 13 bars", (f"{S}/test_monthly_bars.py",)
    ),
    AcceptanceEntry(
        "AC-4019",
        "FR-4010",
        "month-end aggregation and next-session execution",
        (f"{S}/test_monthly_bars.py",),
    ),
    AcceptanceEntry(
        "AC-4020",
        "FR-4010",
        "three-path monthly intent recovery",
        (f"{S}/test_monthly_bars.py", "tests/e2e/three_mode/test_ce_parity.py"),
    ),
    AcceptanceEntry(
        "AC-5001",
        "FR-5001",
        "external plugins discovered in Web and same-interval backtests",
        (f"{F}/test_plugins.py", f"{S}/test_v0204_svc2_discovery_gaps.py"),
    ),
    AcceptanceEntry(
        "AC-5002",
        "FR-5001/NFR-5002",
        "bad external files isolated with precise diagnostics",
        (f"{F}/test_plugins.py", f"{S}/test_v0204_svc2_discovery_gaps.py"),
    ),
    AcceptanceEntry(
        "AC-5003",
        "FR-5001/NFR-5003",
        "source changes invalidate caches and evidence",
        (f"{S}/test_factor_tracking.py", f"{S}/test_factor_audit_badge.py"),
    ),
    AcceptanceEntry(
        "AC-5004",
        "FR-5002",
        "contracts, isolation, truncations and cold/warm invariance",
        (f"{A}/test_plugin_audit.py", f"{S}/test_factor_wind_tunnel.py"),
    ),
    AcceptanceEntry(
        "AC-5005",
        "FR-5002",
        "leaky and cross-sectional plugins fail with first difference",
        (f"{A}/test_plugin_audit.py", f"{S}/test_factor_wind_tunnel.py"),
    ),
    AcceptanceEntry(
        "AC-5006",
        "FR-5003",
        "orthogonality top peers and missing-value controls",
        (f"{F}/test_factor_research.py", f"{S}/test_factor_wind_tunnel.py"),
    ),
    AcceptanceEntry(
        "AC-5007",
        "FR-5004",
        "named presets reject missing or broken factors",
        (f"{S}/test_v05_factor_presets.py", f"{S}/test_v05_ai_studio.py"),
    ),
    AcceptanceEntry(
        "AC-5008",
        "FR-5004",
        "fixed-condition ablation and SHAP contribution",
        (f"{S}/test_v05_factor_presets.py", f"{S}/test_v05_ai_studio.py"),
    ),
    AcceptanceEntry(
        "AC-5009",
        "FR-5005/NFR-5001",
        "offline demo bundle quick start",
        (f"{S}/test_v05_demo_bundle.py", "tests/e2e/web/test_demo_bundle_flow.py"),
    ),
    AcceptanceEntry(
        "AC-5010",
        "FR-5005/NFR-5004",
        "demo mode isolation and visible indicator",
        ("tests/e2e/web/test_demo_bundle_flow.py", f"{T}/web/test_demo_bundle_pages.py"),
    ),
    AcceptanceEntry(
        "AC-5011",
        "FR-5006",
        "CLI JSON envelopes and 0/2/3/4 exit semantics",
        (f"{T}/test_research_cli.py",),
    ),
    AcceptanceEntry(
        "AC-5012",
        "FR-5006",
        "official Skill end-to-end research without touching paper state",
        ("tests/e2e/test_v05_research_cli_skill.py", f"{T}/test_research_cli.py"),
    ),
    AcceptanceEntry(
        "AC-5013",
        "FR-5007",
        "five-state wind-tunnel badges and staleness",
        (f"{S}/test_factor_audit_badge.py", f"{W}/test_factors.py"),
    ),
    AcceptanceEntry(
        "AC-5014",
        "FR-5008",
        "README/index four-pillar story and no-token quick start",
        ("tests/quality/test_v05_release_surface.py",),
    ),
    AcceptanceEntry(
        "AC-5015",
        "FR-5009",
        "BaoStock SQEP daily data and explicit liquidity fallback",
        ("tests/unit/quantide/data/fetchers/test_baostock_daily.py", f"{S}/test_init_wizard.py"),
    ),
    AcceptanceEntry(
        "AC-5016",
        "FR-5009",
        "point-in-time universe uses only information known at t0",
        (f"{T}/strategies/test_v05_pit_and_labels.py", f"{S}/test_strategy_runtime.py"),
    ),
    AcceptanceEntry(
        "AC-5017",
        "FR-5010",
        "three label kinds, independent oracle and model keys",
        (
            f"{T}/strategies/test_v05_pit_and_labels.py",
            f"{T}/strategies/example/test_ml_momentum_reversal.py",
        ),
    ),
    AcceptanceEntry(
        "AC-5018",
        "FR-5011",
        "risk extension registry empty by default and opt-in example",
        (
            f"{T}/providers/test_risk_extensions.py",
            f"{T}/web/test_risk_extension_page.py",
        ),
    ),
    AcceptanceEntry(
        "AC-5019",
        "FR-5012",
        "closed 30m bars trigger shadow replay exactly once",
        (f"{S}/test_shadow_intraday.py",),
    ),
    AcceptanceEntry(
        "AC-5020",
        "FR-5012",
        "30m lunch, T+1, gaps and restart ledger parity",
        (f"{S}/test_shadow_intraday.py",),
    ),
    AcceptanceEntry(
        "AC-5021",
        "FR-5012",
        "unsigned install guidance and synchronized user docs",
        ("tests/quality/test_v05_release_surface.py",),
    ),
    AcceptanceEntry(
        "AC-5022",
        "version boundary",
        "CE/pro defaults and open user extensions",
        ("tests/quality/test_v05_edition_boundary.py",),
    ),
    AcceptanceEntry(
        "AC-5023",
        "scope control",
        "no OpenAPI range CLI or alert-linkage UI",
        ("tests/quality/test_v05_edition_boundary.py",),
    ),
    AcceptanceEntry(
        "AC-5024",
        "NFR-5004/NFR-5006",
        "key mutations and full offline gates",
        (
            "tests/unit/quantide/audit/test_mutations.py",
            "tests/quality/test_v05_edition_boundary.py",
        ),
    ),
    AcceptanceEntry(
        "AC-5025",
        "FR-5013",
        "wizard persists writable data/factor/strategy homes",
        (
            f"{S}/test_init_wizard.py",
            f"{S}/test_v0204_svc4_init_wizard_gaps.py",
            "tests/e2e/web/test_directories_settings.py",
        ),
    ),
    AcceptanceEntry(
        "AC-5026",
        "FR-5013/NFR-5007",
        "optional AI configuration, accurate errors and secret redaction",
        (
            f"{S}/test_v05_ai_agent.py",
            f"{S}/test_v05_ai_studio.py",
            "tests/e2e/web/test_network_settings.py",
        ),
    ),
    AcceptanceEntry(
        "AC-5027",
        "FR-5014/NFR-5001",
        "Web AI closed loop repairs, reports and runs ablation",
        ("tests/e2e/web/test_ai_studio_closed_loop.py", f"{S}/test_v05_ai_agent.py"),
    ),
    AcceptanceEntry(
        "AC-5028",
        "FR-5014/NFR-5007",
        "AI sandbox containment, persistence and cancellation",
        (
            f"{S}/test_v05_ai_agent.py",
            f"{S}/test_v05_ai_studio.py",
            "tests/e2e/web/test_ai_studio_closed_loop.py",
        ),
    ),
    AcceptanceEntry(
        "AC-4301",
        "FR-4301",
        "primary navigation order",
        (f"{W}/test_factors.py", f"{T}/test_app_factory.py"),
    ),
    AcceptanceEntry(
        "AC-4302",
        "FR-4305",
        "legacy alpha-ledger removed",
        (f"{T}/web/pages/system/test_alpha_ledger_removed.py",),
    ),
    AcceptanceEntry("AC-4303", "FR-4302", "grouped factor sidebar", (f"{W}/test_factors.py",)),
    AcceptanceEntry(
        "AC-4304", "FR-4303", "factor overview empty/current state", (f"{W}/test_factors.py",)
    ),
    AcceptanceEntry("AC-4305", "FR-4304", "two tabs and URL state", (f"{W}/test_factors.py",)),
    AcceptanceEntry(
        "AC-4306",
        "FR-4310/4320/4321",
        "structured metadata and card",
        (f"{F}/test_factor_metadata.py", f"{W}/test_factors.py"),
    ),
    AcceptanceEntry(
        "AC-4307", "FR-4330-4334", "single tracking profile", (f"{S}/test_factor_tracking.py",)
    ),
    AcceptanceEntry(
        "AC-4308",
        "FR-4340-4343",
        "background maintenance and isolation",
        (f"{S}/test_factor_tracking.py", f"{S}/test_factor_runs.py"),
    ),
    AcceptanceEntry(
        "AC-4309",
        "FR-4344/4355",
        "per-horizon as_of_date",
        (f"{S}/test_factor_tracking.py", f"{F}/test_factor_research.py"),
    ),
    AcceptanceEntry(
        "AC-4310", "FR-4350-4353", "report summary and charts", (f"{W}/test_factors.py",)
    ),
    AcceptanceEntry(
        "AC-4311",
        "FR-4335/4354",
        "custom study isolation",
        (f"{W}/test_factors.py", f"{S}/test_factor_study.py", f"{S}/test_factor_study_tasks.py"),
    ),
    AcceptanceEntry(
        "AC-4312",
        "FR-4360-4362",
        "status matrix and retry",
        (f"{S}/test_factor_tracking.py", f"{W}/test_factors.py"),
    ),
    AcceptanceEntry(
        "AC-4313", "FR-4344/4355", "maturity boundary oracle", (f"{F}/test_factor_research.py",)
    ),
    AcceptanceEntry(
        "AC-4314",
        "FR-4333/4341/4345",
        "source revisions and atomic publish",
        (f"{S}/test_factor_tracking.py", f"{S}/test_factor_sources.py"),
    ),
    AcceptanceEntry(
        "AC-4315", "FR-4335/4354", "custom-to-rolling confirmation", (f"{W}/test_factors.py",)
    ),
    AcceptanceEntry(
        "AC-4316",
        "FR-4310/4330-4334",
        "defaults and normalization",
        (f"{S}/test_factor_tracking.py", f"{F}/test_factor_metadata.py"),
    ),
    AcceptanceEntry(
        "AC-4317",
        "FR-4009/4321/4355",
        "equal-day deciles and endpoints",
        (f"{F}/test_factor_research.py", f"{A}/test_three_by_ten_oracle.py"),
    ),
    AcceptanceEntry(
        "AC-4318",
        "FR-4340-4345/4361",
        "incremental/restart/lease recovery",
        (
            f"{S}/test_factor_runs.py",
            f"{S}/test_factor_tracking.py",
            f"{S}/test_factor_study_tasks.py",
        ),
    ),
    AcceptanceEntry(
        "AC-4319",
        "FR-4341/4345",
        "permissions, budgets, artifacts",
        (
            f"{S}/test_factor_runs.py",
            f"{S}/test_factor_study_tasks.py",
            f"{W}/test_factors.py",
        ),
    ),
    AcceptanceEntry(
        "AC-4320",
        "FR-4350-4355",
        "accessibility and audit boundaries",
        (f"{W}/test_factors.py", f"{F}/test_factor_research.py"),
    ),
)


ENTRIES = tuple(
    replace(entry, evidence=_V05_EVIDENCE.get(entry.ac, entry.evidence)) for entry in ENTRIES
)


def _classname_file(classname: str | None) -> str | None:
    if not classname:
        return None
    parts = classname.split(".")
    for index, part in enumerate(parts):
        if not part.startswith("test_"):
            continue
        candidate = "/".join(parts[: index + 1]) + ".py"
        if Path(candidate).is_file():
            return candidate
    return None


def _relative_source(path: Path) -> str:
    if not path.is_absolute():
        return str(path)
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _case_nodeid(case: ET.Element) -> str | None:
    source = case.get("file")
    name = case.get("name")
    path = _relative_source(Path(source)) if source else None
    classes: list[str] = []
    classname = case.get("classname")
    if classname:
        parts = classname.split(".")
        for index, part in enumerate(parts):
            if not part.startswith("test_"):
                continue
            candidate = "/".join(parts[: index + 1]) + ".py"
            if Path(candidate).is_file():
                path = candidate
                classes = parts[index + 1 :]
                break
    if not path or not name or not Path(path).is_file():
        return None
    return path + "::" + "::".join([*classes, name])


def _case_outcome(case: ET.Element) -> str:
    if any(case.find(tag) is not None for tag in ("failure", "error")):
        return "failed"
    if case.find("skipped") is not None:
        return "skipped"
    return "passed"


def _junit_outcomes(paths: Iterable[str | Path]) -> dict[str, str]:
    scores = {"passed": 0, "skipped": 1, "failed": 2}
    outcomes: dict[str, str] = {}
    for path in paths:
        root = ET.parse(path).getroot()
        for case in root.iter("testcase"):
            nodeid = _case_nodeid(case)
            if nodeid is None:
                continue
            outcome = _case_outcome(case)
            if nodeid not in outcomes or scores[outcome] > scores[outcomes[nodeid]]:
                outcomes[nodeid] = outcome
    return outcomes


def _evidence_source(evidence: str) -> str:
    return evidence.split("::", 1)[0]


def _node_in_evidence(nodeid: str, evidence: str) -> bool:
    source = nodeid.split("::", 1)[0]
    evidence_source = _evidence_source(evidence)
    candidate = Path(evidence_source)
    if candidate.is_file():
        if source != evidence_source:
            return False
    elif not source.startswith(evidence_source.rstrip("/") + "/"):
        return False
    if "::" not in evidence:
        return True
    selector = evidence.split("::", 1)[1]
    tail = nodeid[len(source) + 2 :]
    if tail == selector or tail.startswith(selector + "["):
        return True
    return selector.endswith(("::", "_")) and tail.startswith(selector)


def collect_nodeids_for(arguments: Iterable[str]) -> set[str]:
    """Run pytest collection with explicit arguments and return real node ids."""
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *arguments,
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env=environment,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip()[-1000:] or "pytest collection failed")
    return {
        line.strip()
        for line in completed.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    }


def collect_nodeids(paths: Iterable[str | Path]) -> set[str]:
    """Collect the exact nodeid set for the current ref and pytest configuration."""
    targets = sorted({str(path) for path in paths if Path(path).exists()})
    return collect_nodeids_for(targets) if targets else set()


def collect_manifest(
    entries: tuple[AcceptanceEntry, ...] = ENTRIES,
) -> dict[str, list[str]]:
    """Build expected AC nodeid groups from the same checkout's collection."""
    paths = {
        source
        for entry in entries
        for source in map(_evidence_source, entry.evidence)
        if source.startswith("tests/") and Path(source).exists()
    }
    nodeids = collect_nodeids(paths)
    for entry in entries:
        for evidence in entry.evidence:
            if "::" in evidence and not any(
                _node_in_evidence(nodeid, evidence) for nodeid in nodeids
            ):
                raise ValueError(f"{entry.ac} selector matched no test: {evidence}")
    return {
        entry.ac: sorted(
            nodeid
            for nodeid in nodeids
            if any(_node_in_evidence(nodeid, path) for path in entry.evidence)
        )
        for entry in entries
    }


def _entry_status(
    entry: AcceptanceEntry,
    outcomes: dict[str, str],
    expected: Mapping[str, Iterable[str]],
    declared: Mapping[str, Iterable[str]] | None = None,
) -> str:
    missing = [
        source for source in map(_evidence_source, entry.evidence) if not Path(source).exists()
    ]
    if missing:
        return "missing_evidence"
    if entry.status in {"manual", "partial"}:
        return entry.status
    required = set(expected.get(entry.ac, ()))
    if entry.ac.startswith("AC-50") and declared is not None:
        expanded = set(declared.get(entry.ac, ()))
        if not required or not expanded or required != expanded:
            return "mapped"
    if required and all(outcomes.get(nodeid) == "passed" for nodeid in required):
        return "covered"
    return "mapped"


def validate_manifest(
    manifest: Mapping[str, Iterable[str]],
    declared: Mapping[str, Iterable[str]],
    *,
    entries: tuple[AcceptanceEntry, ...] = ENTRIES,
) -> None:
    """Reject manifests that add unknown nodes or omit declared node instances."""
    v05 = {entry.ac for entry in entries if entry.ac.startswith("AC-50")}
    for ac in v05:
        required = set(declared.get(ac, ()))
        supplied = set(manifest.get(ac, ()))
        if not supplied or supplied != required:
            raise ValueError(
                f"{ac} manifest does not match the current collection "
                f"(missing={sorted(required - supplied)[:3]}, "
                f"unknown={sorted(supplied - required)[:3]})"
            )


def _read_manifest(path: Path) -> dict[str, list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest must be a JSON object")
    return {
        str(ac): [str(nodeid) for nodeid in nodeids]
        for ac, nodeids in payload.items()
        if isinstance(nodeids, list)
    }


def matrix(
    results: Iterable[str | Path] | None = None,
    manifest: Mapping[str, Iterable[str]] | None = None,
    *,
    declared: Mapping[str, Iterable[str]] | None = None,
    scope: str = "all",
) -> dict[str, Any]:
    result_paths = list(results or ())
    outcomes = _junit_outcomes(result_paths) if result_paths else {}
    expected = manifest or {}
    selected = (
        tuple(entry for entry in ENTRIES if entry.ac.startswith("AC-50"))
        if scope == "v05"
        else ENTRIES
    )
    entries = [
        entry.as_dict(status=_entry_status(entry, outcomes, expected, declared))
        for entry in selected
    ]
    pending = [entry["ac"] for entry in entries if entry["status"] != "covered"]
    return {
        "schema_version": "1.3.0",
        "scope": scope,
        "total": len(selected),
        "covered": len(selected) - len(pending),
        "pending": pending,
        "release_ready": not pending,
        "results": [str(path) for path in result_paths],
        "manifest_ac_count": len(expected),
        "entries": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the CE acceptance matrix")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--results", action="append", default=[])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--scope", choices=("all", "v05"), default="all")
    args = parser.parse_args(argv)
    try:
        declared = collect_manifest() if args.results or args.scope == "v05" else None
        manifest = (
            _read_manifest(args.manifest)
            if args.manifest is not None
            else declared
            if args.results
            else None
        )
        if manifest is not None and declared is not None:
            validate_manifest(manifest, declared)
    except (OSError, ValueError, RuntimeError, ET.ParseError) as exc:
        print(f"Acceptance manifest failed: {exc}", file=sys.stderr)
        return 1
    payload = matrix(args.results, manifest, declared=declared, scope=args.scope)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{payload['covered']}/{payload['total']} covered; pending={payload['pending']}")
    return 0 if payload["release_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
