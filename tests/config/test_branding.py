from importlib.metadata import PackageNotFoundError

import quantide.config.branding as branding_module


def test_get_branding_defaults_to_millionaire(monkeypatch):
    monkeypatch.delenv(branding_module.EDITION_ENV_VAR, raising=False)
    monkeypatch.delenv(branding_module.EDITION_OVERRIDE_ENV_VAR, raising=False)

    branding = branding_module.get_branding()

    assert branding.edition == "millionaire"
    assert branding.product_name == "Millionaire"
    assert branding.release_package == "quantide-millionaire"
    assert branding.runtime_name == "quantide"


def test_get_branding_prefers_packaged_edition_over_stale_env(monkeypatch):
    monkeypatch.setenv(branding_module.EDITION_ENV_VAR, "zillionaire")
    monkeypatch.delenv(branding_module.EDITION_OVERRIDE_ENV_VAR, raising=False)
    monkeypatch.setattr(
        branding_module,
        "_get_installed_release_package",
        lambda: "quantide-millionaire",
    )
    monkeypatch.setattr(branding_module, "_load_source_tree_release_package", lambda: None)

    branding = branding_module.get_branding()

    assert branding.edition == "millionaire"
    assert branding.product_name == "Millionaire"
    assert branding.release_package == "quantide-millionaire"


def test_get_branding_accepts_zillionaire_with_explicit_override(monkeypatch):
    monkeypatch.setenv(branding_module.EDITION_ENV_VAR, "zillionaire")
    monkeypatch.setenv(branding_module.EDITION_OVERRIDE_ENV_VAR, "1")
    monkeypatch.setattr(
        branding_module,
        "_get_installed_release_package",
        lambda: "quantide-millionaire",
    )
    monkeypatch.setattr(branding_module, "_load_source_tree_release_package", lambda: None)

    branding = branding_module.get_branding()

    assert branding.edition == "zillionaire"
    assert branding.product_name == "Zillionaire"
    assert branding.release_package == "quantide-zillionaire"


def test_get_runtime_version_tries_release_package_before_runtime(monkeypatch):
    monkeypatch.delenv(branding_module.EDITION_ENV_VAR, raising=False)
    monkeypatch.delenv(branding_module.EDITION_OVERRIDE_ENV_VAR, raising=False)

    calls: list[str] = []

    def fake_version(package_name: str) -> str:
        calls.append(package_name)
        if package_name == "quantide-millionaire":
            raise PackageNotFoundError
        if package_name == "quantide":
            return "0.1.0"
        raise AssertionError(package_name)

    monkeypatch.setattr(branding_module, "version", fake_version)

    assert branding_module.get_runtime_version() == "0.1.0"
    assert calls == ["quantide-millionaire", "quantide"]