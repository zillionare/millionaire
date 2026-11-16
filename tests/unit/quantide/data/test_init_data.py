from pathlib import Path

import pytest

import quantide.data as data_module


def test_init_data_uses_fixed_config_db_by_default(monkeypatch, tmp_path: Path):
    data_home = tmp_path / "market-home"
    config_db_path = tmp_path / "config" / "quantide.db"
    captured: dict[str, Path | tuple[str, str]] = {}

    monkeypatch.setattr(data_module, "get_app_db_path", lambda: config_db_path)
    monkeypatch.setattr(data_module.calendar, "load", lambda path: captured.setdefault("calendar", Path(path)))
    monkeypatch.setattr(data_module.stock_list, "load", lambda path: captured.setdefault("stocks", Path(path)))
    monkeypatch.setattr(
        data_module.daily_bars,
        "connect",
        lambda store_path, calendar_path: captured.setdefault(
            "daily",
            (str(store_path), str(calendar_path)),
        ),
    )
    def _fake_store_init(self, path, cal):
        captured.setdefault("index", Path(str(path)))
    monkeypatch.setattr(data_module.IndexBarsStore, "__init__", _fake_store_init)
    monkeypatch.setattr(data_module.db, "init", lambda path: captured.setdefault("db", Path(path)))

    data_module.init_data(data_home)

    assert captured["calendar"] == data_home / "data" / "calendar.parquet"
    assert captured["stocks"] == data_home / "data" / "stock_list.parquet"
    assert captured["db"] == config_db_path
    assert (data_home / "data" / "bars" / "daily").exists()
    assert (data_home / "data" / "bars" / "index").exists()


def test_init_data_allows_explicit_db_override(monkeypatch, tmp_path: Path):
    data_home = tmp_path / "market-home"
    explicit_db_path = tmp_path / "custom" / "override.db"
    captured: dict[str, Path] = {}

    monkeypatch.setattr(data_module.calendar, "load", lambda path: None)
    monkeypatch.setattr(data_module.stock_list, "load", lambda path: None)
    monkeypatch.setattr(data_module.daily_bars, "connect", lambda store_path, calendar_path: None)
    monkeypatch.setattr(data_module.IndexBarsStore, "__init__", lambda self, path, cal: None)
    monkeypatch.setattr(data_module.db, "init", lambda path: captured.setdefault("db", Path(path)))

    data_module.init_data(data_home, db_path=explicit_db_path)

    assert captured["db"] == explicit_db_path


@pytest.fixture
def offline_data_loader(monkeypatch):
    """Keep path integration tests offline while retaining real directory creation."""
    loaded = []
    monkeypatch.setattr(data_module.calendar, "load", lambda path: loaded.append(Path(path)))
    monkeypatch.setattr(data_module.stock_list, "load", lambda path: loaded.append(Path(path)))
    monkeypatch.setattr(data_module.daily_bars, "connect", lambda *args: None)
    monkeypatch.setattr(data_module.daily_basic, "_path", None)
    return loaded


@pytest.mark.parametrize("arguments", [(), (None,), ("",), ("   ",)])
def test_blank_home_reads_saved_config_even_after_database_restart(
    monkeypatch, tmp_path, db, offline_data_loader, arguments
):
    from quantide.data.models.app_state import AppState

    previous = db.db_path
    target = tmp_path / "config/quantide.db"
    target.parent.mkdir()
    market = tmp_path / "saved-market"
    monkeypatch.setattr(data_module, "get_app_db_path", lambda: target)
    monkeypatch.setenv("QUANTIDE_DATA_HOME", str(tmp_path / "environment-market"))
    monkeypatch.chdir(tmp_path)
    try:
        db.init(target)
        db["app_state"].upsert(AppState(app_home=str(market)).to_dict(), pk="id")
        db.close()
        db._initialized = False
        data_module.init_data(*arguments)
        assert offline_data_loader == [market / "data/calendar.parquet", market / "data/stock_list.parquet"]
        assert (market / "data/bars/daily").is_dir()
        assert not (tmp_path / "data").exists()
        assert not (tmp_path / "environment-market").exists()
    finally:
        db.init(previous)


def test_no_home_uses_environment_then_tmp_without_creating_cwd_data(
    monkeypatch, tmp_path, offline_data_loader
):
    from quantide.config import paths, settings

    monkeypatch.setattr(settings, "_load_app_state", lambda: None)
    monkeypatch.setattr(paths, "temporary_runtime_dir", lambda: tmp_path / "fallback")
    monkeypatch.setenv("QUANTIDE_DATA_HOME", str(tmp_path / "environment"))
    monkeypatch.chdir(tmp_path)
    data_module.init_data("", init_db=False)
    assert (tmp_path / "environment/data/bars/daily").is_dir()
    monkeypatch.delenv("QUANTIDE_DATA_HOME")
    data_module.init_data(init_db=False)
    assert (tmp_path / "fallback/market/data/bars/daily").is_dir()
    assert not (tmp_path / "data").exists()


def test_daily_basic_resolves_saved_configuration_lazily(monkeypatch, tmp_path):
    from quantide.config import settings
    from quantide.data.models.app_state import AppState

    monkeypatch.setattr(data_module.daily_basic, "_path", None)
    monkeypatch.setattr(settings, "_load_app_state", lambda: AppState(app_home=str(tmp_path)))
    assert data_module.daily_basic.path == tmp_path / "data/daily_basic.parquet"


def test_explicit_memory_database_remains_supported(tmp_path, db, offline_data_loader):
    previous = db.db_path
    try:
        data_module.init_data(tmp_path / "market", db_path=":memory:")
        assert db.db_path == ":memory:"
        assert db["app_state"].count == 0
    finally:
        db.init(previous)
