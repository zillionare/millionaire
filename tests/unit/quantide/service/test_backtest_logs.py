import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from quantide.config.paths import (
    clear_app_config_dir_override,
    get_backtest_log_path,
    set_app_config_dir_override,
)
from quantide.core.enums import BrokerKind
from quantide.data.sqlite import Portfolio
from quantide.service import backtest_logs as backtest_logs_service


@pytest.fixture(autouse=True)
def isolated_backtest_log_home(tmp_path: Path):
    set_app_config_dir_override(tmp_path / "config")
    backtest_logs_service._FILE_FAILURE_WARNED.clear()
    try:
        yield
    finally:
        backtest_logs_service._FILE_FAILURE_WARNED.clear()
        clear_app_config_dir_override()


def _insert_portfolio(db, portfolio_id: str) -> None:
    db.insert_portfolio(
        Portfolio(
            portfolio_id=portfolio_id,
            kind=BrokerKind.BACKTEST,
            start=datetime.date(2024, 1, 1),
            end=datetime.date(2024, 1, 31),
            name="DemoStrategy",
        )
    )


def test_record_backtest_log_writes_db_and_saved_file(db) -> None:
    portfolio_id = f"bt-log-{uuid4().hex}"
    _insert_portfolio(db, portfolio_id)

    backtest_logs_service.record_backtest_log(
        portfolio_id=portfolio_id,
        level="INFO",
        source="runner",
        message="回测启动",
        dt=datetime.datetime(2024, 1, 2, 9, 0),
        extra={"stage": "start"},
        save_to_file=True,
    )

    logs_df = db.get_backtest_logs(portfolio_id)
    assert logs_df.height == 1
    assert logs_df.row(0, named=True)["message"] == "回测启动"

    saved_path = get_backtest_log_path(portfolio_id)
    assert saved_path.exists()

    loaded_rows = backtest_logs_service.load_saved_backtest_logs(portfolio_id)
    assert loaded_rows[0]["message"] == "回测启动"
    assert loaded_rows[0]["source"] == "runner"


def test_delete_saved_backtest_log_removes_file(db) -> None:
    portfolio_id = f"bt-log-{uuid4().hex}"
    _insert_portfolio(db, portfolio_id)

    backtest_logs_service.record_backtest_log(
        portfolio_id=portfolio_id,
        level="INFO",
        source="runner",
        message="test",
        dt=datetime.datetime(2024, 1, 2, 9, 0),
        save_to_file=True,
    )

    assert backtest_logs_service.saved_backtest_log_exists(portfolio_id) is True
    backtest_logs_service.delete_saved_backtest_log(portfolio_id)
    assert backtest_logs_service.saved_backtest_log_exists(portfolio_id) is False


def test_delete_saved_backtest_log_idempotent() -> None:
    backtest_logs_service.delete_saved_backtest_log("non-existent-id")
    assert backtest_logs_service.saved_backtest_log_exists("non-existent-id") is False


def test_record_backtest_log_warns_once_when_file_write_fails(db, monkeypatch) -> None:
    portfolio_id = f"bt-log-{uuid4().hex}"
    _insert_portfolio(db, portfolio_id)

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(backtest_logs_service, "_append_entry_to_file", _boom)

    backtest_logs_service.record_backtest_log(
        portfolio_id=portfolio_id,
        level="INFO",
        source="runner",
        message="第一条日志",
        dt=datetime.datetime(2024, 1, 2, 9, 0),
        save_to_file=True,
    )
    backtest_logs_service.record_backtest_log(
        portfolio_id=portfolio_id,
        level="INFO",
        source="runner",
        message="第二条日志",
        dt=datetime.datetime(2024, 1, 2, 9, 1),
        save_to_file=True,
    )

    rows = backtest_logs_service.list_backtest_logs(portfolio_id, limit=10)
    messages = [row["message"] for row in rows]

    assert "第一条日志" in messages
    assert "第二条日志" in messages
    assert len([msg for msg in messages if "写入回测日志文件失败" in msg]) == 1
