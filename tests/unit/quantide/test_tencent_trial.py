"""Non-renewable opt-in and HTTP enforcement, without contacting Tencent."""

import datetime
from unittest.mock import Mock

import pytest

from quantide.config.tencent_trial import configure_trial, trial_status
from quantide.data.fetchers.tencent import TencentDataFetcher, to_tencent_symbol
from quantide.data.sqlite import db

START = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path):
    db.init(tmp_path / "trial.db")
    yield
    db.close()


def test_default_disabled_and_disabling_does_not_start_trial():
    assert not trial_status(START).enabled
    assert not configure_trial(False, START).first_enabled_at


def test_restart_reconfiguration_and_toggling_cannot_renew(tmp_path):
    first = configure_trial(True, START)
    configure_trial(False, START + datetime.timedelta(days=3))
    db.close()
    db._initialized = False
    db.init(tmp_path / "trial.db")
    again = configure_trial(True, START + datetime.timedelta(days=10))
    assert again.expires_at == first.expires_at
    assert trial_status(START + datetime.timedelta(days=29)).enabled
    assert not trial_status(START + datetime.timedelta(days=30)).enabled
    with pytest.raises(ValueError, match="演示期已结束"):
        configure_trial(True, START + datetime.timedelta(days=31))
    assert not trial_status(START).enabled  # expiry remains sticky after clock rollback


def test_http_is_blocked_before_any_network_request():
    session = Mock()
    fetcher = TencentDataFetcher(session=session)
    assert fetcher.fetch_quote_snapshot(["000001.SZ"]) == {}
    session.get.assert_not_called()


@pytest.mark.parametrize("asset,expected", [
    ("920000.BJ", "bj920000"), ("000001.SH", "sh000001"),
    ("000001.SZ", "sz000001"), ("830001.BJ", "bj830001"),
])
def test_exchange_mapping(asset, expected):
    assert to_tencent_symbol(asset) == expected
