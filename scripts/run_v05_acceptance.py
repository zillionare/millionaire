"""Run the exact v0.5 acceptance nodes plus the CE release-gate journey once."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from quantide.audit.acceptance import collect_manifest, collect_nodeids_for, matrix
from scripts import check_test_results

_MARKERS = "e2e and release_gate and not private_only and not e2e_live_smoke"
_SOCKET_ARGS = (
    "--disable-socket",
    "--allow-unix-socket",
    "--allow-hosts=127.0.0.1,::1,localhost",
)


def _collected(arguments: list[str]) -> list[str]:
    return sorted(collect_nodeids_for(arguments))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--matrix-json", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args(argv)
    manifest = collect_manifest()
    v05_nodes = sorted(
        {node for ac, nodes in manifest.items() if ac.startswith("AC-50") for node in nodes}
    )
    release_nodes = _collected(["tests/e2e", "-m", _MARKERS])
    nodes = sorted(set(v05_nodes) | set(release_nodes))
    if not nodes:
        raise SystemExit("acceptance selection is empty")
    args.junit.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        *nodes,
        "--strict-markers",
        "--runxfail",
        f"--timeout={args.timeout}",
        *_SOCKET_ARGS,
        f"--junitxml={args.junit}",
    ]
    completed = subprocess.run(
        command,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if completed.returncode != 0:
        return completed.returncode
    try:
        check_test_results.validate(args.junit)
    except ValueError as exc:
        print(f"Acceptance JUnit failed: {exc}", file=sys.stderr)
        return 1
    payload = matrix([args.junit], manifest, declared=manifest, scope="v05")
    args.matrix_json.parent.mkdir(parents=True, exist_ok=True)
    args.matrix_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{payload['covered']}/{payload['total']} v0.5 acceptance criteria covered")
    return 0 if payload["release_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
