"""Edition-aware branding helpers for the shared quantide runtime.

This module keeps user-facing product branding separate from the stable
technical runtime identifiers such as the ``quantide`` Python namespace and
runtime directories.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

RUNTIME_NAME = "quantide"
DEFAULT_EDITION = "millionaire"
EDITION_ENV_VAR = "QUANTIDE_EDITION"
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


def _normalize_edition(value: str | None) -> str:
    """Normalize the configured edition value."""
    text = str(value or "").strip().lower()
    if text in SUPPORTED_EDITIONS:
        return text
    return DEFAULT_EDITION


def get_runtime_edition() -> str:
    """Return the active product edition for this runtime."""
    return _normalize_edition(os.getenv(EDITION_ENV_VAR))


def get_branding() -> Branding:
    """Return effective branding metadata for the current runtime."""
    edition = get_runtime_edition()
    product_name = "Zillionaire" if edition == "zillionaire" else "Millionaire"
    return Branding(
        edition=edition,
        runtime_name=RUNTIME_NAME,
        product_name=product_name,
        release_package=f"quantide-{edition}",
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
    "RUNTIME_NAME",
    "SUPPORTED_EDITIONS",
    "get_branding",
    "get_runtime_edition",
    "get_runtime_version",
]