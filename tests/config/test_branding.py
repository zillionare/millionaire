from importlib.metadata import PackageNotFoundError

import quantide.config.branding as branding_module


def test_get_branding_defaults_to_millionaire(monkeypatch):
    monkeypatch.delenv(branding_module.EDITION_ENV_VAR, raising=False)

    branding = branding_module.get_branding()

    assert branding.edition == "millionaire"
    assert branding.product_name == "Millionaire"
    assert branding.release_package == "quantide-millionaire"
    assert branding.runtime_name == "quantide"


def test_get_branding_accepts_zillionaire(monkeypatch):
    monkeypatch.setenv(branding_module.EDITION_ENV_VAR, "zillionaire")

    branding = branding_module.get_branding()

    assert branding.edition == "zillionaire"
    assert branding.product_name == "Zillionaire"
    assert branding.release_package == "quantide-zillionaire"


def test_get_runtime_version_tries_release_package_before_runtime(monkeypatch):
    monkeypatch.delenv(branding_module.EDITION_ENV_VAR, raising=False)

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