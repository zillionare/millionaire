"""Edition-aware branding helpers for the shared quantide runtime.

This module keeps user-facing product branding separate from the stable
technical runtime identifiers such as the ``quantide`` Python namespace and
runtime directories.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, packages_distributions, version
from pathlib import Path
import tomllib

RUNTIME_NAME = "quantide"
DEFAULT_EDITION = "millionaire"
EDITION_ENV_VAR = "QUANTIDE_EDITION"
EDITION_OVERRIDE_ENV_VAR = "QUANTIDE_ENABLE_EDITION_OVERRIDE"
SUPPORTED_EDITIONS = {"millionaire", "zillionaire"}


@dataclass(frozen=True)
class Branding:
    """Branding metadata for the active product edition.

    Attributes:
        edition: Active edition name.
        runtime_name: Stable technical runtime name.
        product_name: User-facing product name.
        release_package: Distribution package name.
        company_name: Company name shown in the UI.
        support_email: Public support or business contact address.
    """

    edition: str
    runtime_name: str
    product_name: str
    release_package: str
    company_name: str
    support_email: str


def _get_supported_edition(value: str | None) -> str | None:
    """Return a supported edition name when the input is valid."""
    text = str(value or "").strip().lower()
    if text in SUPPORTED_EDITIONS:
        return text
    return None


def _is_truthy(value: str | None) -> bool:
    """Return whether an environment flag should be treated as enabled."""
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _get_release_package_edition(package_name: str | None) -> str | None:
    """Extract a supported edition from a release package name."""
    text = str(package_name or "").strip().lower()
    prefix = f"{RUNTIME_NAME}-"
    if not text.startswith(prefix):
        return None
    return _get_supported_edition(text.removeprefix(prefix))


@lru_cache(maxsize=1)
def _get_installed_release_package() -> str | None:
    """Return the installed release package that owns the runtime namespace."""
    distribution_names = packages_distributions().get(RUNTIME_NAME, [])
    for distribution_name in distribution_names:
        if _get_release_package_edition(distribution_name) is not None:
            return distribution_name
    return None


@lru_cache(maxsize=1)
def _load_source_tree_release_package() -> str | None:
    """Read the source-tree release package name from pyproject metadata."""
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as stream:
            pyproject = tomllib.load(stream)
    except (FileNotFoundError, OSError, tomllib.TOMLDecodeError):
        return None

    package_name = pyproject.get("tool", {}).get("poetry", {}).get("name")
    if isinstance(package_name, str):
        return package_name if _get_release_package_edition(package_name) else None
    return None


def _get_packaged_release_package() -> str:
    """Resolve the release package name pinned to this runtime."""
    for package_name in (
        _get_installed_release_package(),
        _load_source_tree_release_package(),
    ):
        if package_name is not None:
            return package_name
    return f"{RUNTIME_NAME}-{DEFAULT_EDITION}"


def _get_override_edition() -> str | None:
    """Return the explicit development override edition when enabled."""
    if not _is_truthy(os.getenv(EDITION_OVERRIDE_ENV_VAR)):
        return None
    return _get_supported_edition(os.getenv(EDITION_ENV_VAR))


def get_runtime_edition() -> str:
    """Return the active product edition for this runtime."""
    override_edition = _get_override_edition()
    if override_edition is not None:
        return override_edition

    packaged_edition = _get_release_package_edition(_get_packaged_release_package())
    return packaged_edition or DEFAULT_EDITION


def get_branding() -> Branding:
    """Return effective branding metadata for the current runtime."""
    override_edition = _get_override_edition()
    release_package = _get_packaged_release_package()
    edition = _get_release_package_edition(release_package) or DEFAULT_EDITION
    if override_edition is not None:
        edition = override_edition
        release_package = f"{RUNTIME_NAME}-{edition}"

    product_name = "Zillionaire" if edition == "zillionaire" else "Millionaire"
    return Branding(
        edition=edition,
        runtime_name=RUNTIME_NAME,
        product_name=product_name,
        release_package=release_package,
        company_name="Zillionare",
        support_email="business@quantide.cn",
    )


def get_runtime_version() -> str:
    """Resolve the installed version for the active edition runtime."""
    branding = get_branding()
    for package_name in (branding.release_package, branding.runtime_name):
        try:
            return version(package_name)
        except PackageNotFoundError:
            continue
    return "0.0.0"


__all__ = [
    "Branding",
    "DEFAULT_EDITION",
    "EDITION_ENV_VAR",
    "EDITION_OVERRIDE_ENV_VAR",
    "RUNTIME_NAME",
    "SUPPORTED_EDITIONS",
    "get_branding",
    "get_runtime_edition",
    "get_runtime_version",
]