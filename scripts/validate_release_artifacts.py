"""Validate CE wheel and sdist contents after a package build."""

from __future__ import annotations

import argparse
import re
import tarfile
import zipfile
from pathlib import Path

from scripts.artifact_paths import artifact_root

EXCLUDED_TOP_LEVEL = {
    ".louke",
    "tests",
    "notebooks",
    "data",
    "dist",
    "site",
    "review",
    "quality-reports",
    "packaging",
    "build",
}

# These are the private risk implementations removed from the CE tree. The
# check is deliberately explicit so a future reintroduced file or persisted
# private program ID fails the release job instead of silently shipping.
PRIVATE_RISK_PATH_PARTS = frozenset(
    {
        "triple_barrier.py",
        "triple_barrier_risk.py",
        "cost_stop_loss.py",
        "pullback_sell.py",
    }
)
PRIVATE_RISK_ID_MARKERS = (
    "TripleBarrierRiskStrategy",
    "CostStopLossStrategy",
    "PullbackSellStrategy",
    "quantide.strategies.triple_barrier_risk",
    "SAGE-PROD-",
)
PRIVATE_RISK_MARKER_RE = re.compile(
    "|".join(re.escape(marker) for marker in PRIVATE_RISK_ID_MARKERS),
    re.IGNORECASE,
)


def _artifact_files(path: Path) -> list[tuple[str, bytes]]:
    """Return archive member names and bytes for a wheel or source archive."""
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return [(info.filename, archive.read(info)) for info in archive.infolist()]
    if path.name.endswith((".tar.gz", ".tar.bz2", ".tar.xz", ".tar")):
        with tarfile.open(path) as archive:
            result: list[tuple[str, bytes]] = []
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                stream = archive.extractfile(member)
                if stream is not None:
                    result.append((member.name, stream.read()))
            return result
    raise ValueError(f"unsupported release artifact: {path}")


def _validate_artifact(path: Path) -> list[str]:
    """Return validation errors for one archive."""
    errors: list[str] = []
    try:
        members = _artifact_files(path)
    except (OSError, tarfile.TarError, zipfile.BadZipFile, ValueError) as exc:
        return [f"{path.name}: cannot read artifact: {exc}"]

    for name, content in members:
        parts = Path(name).parts
        relative = parts if path.suffix == ".whl" else parts[1:]
        if relative and relative[0] in EXCLUDED_TOP_LEVEL:
            errors.append(f"{path.name}: development/generated content: {name}")
            continue
        if any(Path(part).name in PRIVATE_RISK_PATH_PARTS for part in Path(name).parts):
            errors.append(f"{path.name}: private risk source path: {name}")
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        match = PRIVATE_RISK_MARKER_RE.search(text)
        if match:
            errors.append(f"{path.name}: private risk ID marker {match.group(0)!r} in {name}")
    return errors


def main() -> int:
    """Validate all wheel and source archives in a distribution directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist_dir", type=Path, nargs="?", default=artifact_root() / "dist")
    args = parser.parse_args()

    artifacts = sorted(
        path
        for path in args.dist_dir.glob("*")
        if path.suffix == ".whl" or path.name.endswith((".tar.gz", ".tar.bz2", ".tar.xz"))
    )
    if not artifacts:
        parser.error(f"no wheel or sdist found in {args.dist_dir}")

    errors = [error for artifact in artifacts for error in _validate_artifact(artifact)]
    if errors:
        print("CE release artifact validation failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"CE release artifact validation passed ({len(artifacts)} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
