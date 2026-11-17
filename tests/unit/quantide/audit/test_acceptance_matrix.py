"""Acceptance matrix must depend on execution evidence, not static labels."""

from __future__ import annotations

import subprocess
import sys

import pytest

from quantide.audit.acceptance import (
    AcceptanceEntry,
    _evidence_source,
    _node_in_evidence,
    collect_nodeids,
    matrix,
    validate_manifest,
)

_ALPHA = "tests/unit/quantide/web/pages/system/test_alpha_ledger_removed.py"
_ALPHA_NODE = f"{_ALPHA}::test_alpha_ledger_page_removed"


def test_matrix_without_results_reports_mapped_not_covered() -> None:
    payload = matrix()
    assert payload["covered"] == 0
    assert not payload["release_ready"]
    assert "AC-4014" in payload["pending"]
    assert {entry["status"] for entry in payload["entries"]} <= {
        "mapped",
        "manual",
        "partial",
        "missing_evidence",
    }


def _report(
    tmp_path,
    name: str,
    child: str = "",
    suffix: str = "",
    *,
    classname: str = "tests.unit.quantide.web.pages.system.test_alpha_ledger_removed",
    nodes: tuple[str, ...] = (_ALPHA_NODE,),
) -> dict:
    report = tmp_path / f"results-{name}-{suffix or 'pass'}.xml"
    report.write_text(
        f'<testsuites><testsuite><testcase classname="{classname}" '
        f'name="{name}">{child}</testcase></testsuite></testsuites>',
        encoding="utf-8",
    )
    return matrix([report], {"AC-4302": nodes})


def test_matrix_requires_full_passing_file_evidence(tmp_path) -> None:
    payload = _report(tmp_path, "test_alpha_ledger_page_removed")
    statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
    assert statuses["AC-4302"] == "covered"


def test_acceptance_rejects_failed_skipped_error_and_unknown_cases(tmp_path) -> None:
    for label, child in (
        ("failure", '<failure message="x"/>'),
        ("error", '<error message="x"/>'),
        ("skipped", "<skipped/>"),
    ):
        payload = _report(tmp_path, "test_alpha_ledger_page_removed", child, label)
        statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
        assert statuses["AC-4302"] == "mapped"

    payload = _report(tmp_path, "not_real")
    statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
    assert statuses["AC-4302"] == "mapped"


def test_acceptance_rejects_partial_class_execution(tmp_path) -> None:
    file_path = _ALPHA
    classname = "tests.unit.quantide.web.pages.system.test_alpha_ledger_removed.TestLedger"
    nodes = (f"{file_path}::TestLedger::test_one", f"{file_path}::TestLedger::test_two")
    payload = _report(
        tmp_path,
        "test_one",
        classname=classname,
        nodes=nodes,
    )
    statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
    assert statuses["AC-4302"] == "mapped"


def test_acceptance_does_not_merge_parameter_skip_with_passed_instance(tmp_path) -> None:
    nodes = (
        f"{_ALPHA}::test_alpha_ledger_page_removed[p1]",
        f"{_ALPHA}::test_alpha_ledger_page_removed[p2]",
    )
    report = tmp_path / "params.xml"
    report.write_text(
        "<testsuites><testsuite>"
        '<testcase classname="tests.unit.quantide.web.pages.system.test_alpha_ledger_removed" '
        'name="test_alpha_ledger_page_removed[p1]" />'
        '<testcase classname="tests.unit.quantide.web.pages.system.test_alpha_ledger_removed" '
        'name="test_alpha_ledger_page_removed[p2]"><skipped /></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    payload = matrix([report], {"AC-4302": nodes})
    statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
    assert statuses["AC-4302"] == "mapped"


def test_real_pytest_partial_parameterization_is_not_covered(tmp_path) -> None:
    synthetic = "tests/unit/quantide/audit/test_synthetic.py"
    statistics = "tests/unit/quantide/audit/test_statistics.py"
    expected = collect_nodeids([synthetic, statistics])
    report = tmp_path / "partial.xml"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            synthetic,
            statistics,
            "--deselect="
            "tests/unit/quantide/audit/test_synthetic.py::"
            "test_pearson_power_recovers_positive_and_negative_signals[-0.25]",
            "-q",
            "-p",
            "no:cacheprovider",
            "--disable-socket",
            "--allow-unix-socket",
            "--allow-hosts=127.0.0.1,::1,localhost",
            f"--junitxml={report}",
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    manifest = {
        "AC-4004": sorted(
            nodeid
            for nodeid in expected
            if nodeid.startswith(synthetic + "::") or nodeid.startswith(statistics + "::")
        ),
        "AC-4005": sorted(nodeid for nodeid in expected if nodeid.startswith(synthetic + "::")),
    }
    payload = matrix([report], manifest)
    statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
    assert statuses["AC-4004"] == "mapped"
    assert statuses["AC-4005"] == "mapped"


def test_skipped_instance_cannot_be_overwritten_by_later_pass(tmp_path) -> None:
    skipped = tmp_path / "skipped.xml"
    passed = tmp_path / "passed.xml"
    body = (
        "<testsuites><testsuite><testcase "
        'classname="tests.unit.quantide.web.pages.system.test_alpha_ledger_removed" '
        'name="test_alpha_ledger_page_removed">{}</testcase></testsuite></testsuites>'
    )
    skipped.write_text(body.format("<skipped />"), encoding="utf-8")
    passed.write_text(body.format(""), encoding="utf-8")
    payload = matrix([skipped, passed], {"AC-4302": [_ALPHA_NODE]})
    statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
    assert statuses["AC-4302"] == "mapped"


def test_v05_acceptance_declares_all_28_evidence_entries() -> None:
    from pathlib import Path

    from quantide.audit.acceptance import ENTRIES

    expected = {f"AC-50{index:02d}" for index in range(1, 29)}
    entries = {entry.ac: entry for entry in ENTRIES}
    assert expected <= set(entries)
    for ac in sorted(expected):
        entry = entries[ac]
        assert entry.requirement
        assert entry.behavior
        assert entry.evidence
        assert all(Path(_evidence_source(path)).exists() for path in entry.evidence), (
            ac,
            entry.evidence,
        )
        assert all("::" in path for path in entry.evidence), (ac, entry.evidence)
        assert entry.status not in {"skip", "xfail"}


def test_exact_node_evidence_expands_parameterized_instances() -> None:
    path = "tests/unit/quantide/strategies/test_v05_pit_and_labels.py"
    evidence = f"{path}::test_panel_cache_fingerprint_tracks_all_pit_input_files"
    assert _node_in_evidence(
        f"{path}::test_panel_cache_fingerprint_tracks_all_pit_input_files[a]", evidence
    )
    assert not _node_in_evidence(
        f"{path}::test_panel_cache_fingerprint_tracks_all_pit_input_files_extra", evidence
    )
    assert not _node_in_evidence(f"{path}::test_other", evidence)


def test_manifest_cannot_delete_parameter_instances_or_add_unknown_nodes() -> None:
    path = "tests/unit/quantide/strategies/test_v05_pit_and_labels.py"
    declared = {
        "AC-5016": [
            f"{path}::test_panel_cache_fingerprint_tracks_all_pit_input_files[a]",
            f"{path}::test_panel_cache_fingerprint_tracks_all_pit_input_files[b]",
        ]
    }
    entries = (AcceptanceEntry("AC-5016", "FR-5009", "listing contract"),)
    with pytest.raises(ValueError, match="AC-5016"):
        validate_manifest(
            {"AC-5016": [f"{path}::test_panel_cache_fingerprint_tracks_all_pit_input_files[a]"]},
            declared,
            entries=entries,
        )
    with pytest.raises(ValueError, match="AC-5016"):
        validate_manifest(
            {
                "AC-5016": [
                    f"{path}::test_panel_cache_fingerprint_tracks_all_pit_input_files[a]",
                    f"{path}::test_panel_cache_fingerprint_tracks_all_pit_input_files[b]",
                    f"{path}::test_not_real",
                ]
            },
            declared,
            entries=entries,
        )


def test_matrix_with_declared_v05_manifest_requires_exact_instance_set(tmp_path) -> None:
    path = "tests/unit/quantide/strategies/test_v05_pit_and_labels.py"
    node = f"{path}::test_panel_cache_fingerprint_tracks_all_pit_input_files[a]"
    other = f"{path}::test_panel_cache_fingerprint_tracks_all_pit_input_files[b]"
    report = tmp_path / "v05.xml"
    report.write_text(
        "<testsuites><testsuite>"
        '<testcase classname="tests.unit.quantide.strategies.test_v05_pit_and_labels" '
        'name="test_panel_cache_fingerprint_tracks_all_pit_input_files[a]" />'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    payload = matrix(
        [report],
        {"AC-5016": [node]},
        declared={"AC-5016": [node, other]},
        scope="v05",
    )
    statuses = {entry["ac"]: entry["status"] for entry in payload["entries"]}
    assert statuses["AC-5016"] == "mapped"
    assert payload["total"] == 28


def test_v05_scope_covered_count_matches_selected_entries() -> None:
    payload = matrix(scope="v05")
    assert payload["total"] == 28
    assert payload["covered"] == 0
    assert payload["total"] == payload["covered"] + len(payload["pending"])


def test_a_misspelled_required_selector_cannot_hide_behind_a_real_one(monkeypatch) -> None:
    from quantide.audit import acceptance

    source = "tests/unit/quantide/service/test_v05_c1_identity.py"
    good = f"{source}::test_model_key_encodes_effective_seed"
    bad = f"{source}::test_typo_not_a_real_test"
    monkeypatch.setattr(acceptance, "collect_nodeids", lambda paths: {good})
    entry = acceptance.AcceptanceEntry("AC-5017", "FR-5010", "seed identity", (good, bad))
    with pytest.raises(ValueError, match="selector matched no test"):
        acceptance.collect_manifest((entry,))
    assert acceptance.collect_manifest((acceptance.replace(entry, evidence=(good,)),)) == {
        "AC-5017": [good]
    }
