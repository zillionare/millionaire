"""B08-core-ports-3: Tests for quantide/core/ports/data_fetcher.py."""

from __future__ import annotations

from typing import Protocol as _Protocol

from quantide.core.ports.data_fetcher import DataFetcherPort


def test_data_fetcher_port_is_a_protocol():
    assert issubclass(DataFetcherPort, _Protocol)


def test_data_fetcher_port_has_fetch_calendar():
    assert hasattr(DataFetcherPort, "fetch_calendar")


def test_data_fetcher_port_has_fetch_stock_list():
    assert hasattr(DataFetcherPort, "fetch_stock_list")


def test_data_fetcher_port_has_fetch_adjust_factor():
    assert hasattr(DataFetcherPort, "fetch_adjust_factor")


def test_data_fetcher_port_has_fetch_bars():
    assert hasattr(DataFetcherPort, "fetch_bars")


def test_data_fetcher_port_has_fetch_limit_price():
    assert hasattr(DataFetcherPort, "fetch_limit_price")


def test_data_fetcher_port_has_fetch_st_info():
    assert hasattr(DataFetcherPort, "fetch_st_info")


def test_data_fetcher_port_has_fetch_bars_ext():
    assert hasattr(DataFetcherPort, "fetch_bars_ext")


class _FakeDataFetcher:
    def fetch_calendar(self, epoch):
        import pandas as pd
        return pd.DataFrame()

    def fetch_stock_list(self):
        import pandas as pd
        return pd.DataFrame()

    def fetch_adjust_factor(self, dates):
        import pandas as pd
        return pd.DataFrame(), []

    def fetch_bars(self, dates):
        import pandas as pd
        return pd.DataFrame(), []

    def fetch_limit_price(self, dates):
        import pandas as pd
        return pd.DataFrame(), []

    def fetch_st_info(self, dates):
        import pandas as pd
        return pd.DataFrame(), []

    def fetch_bars_ext(self, dates, phase_callback=None):
        import pandas as pd
        return pd.DataFrame(), []


def test_fake_data_fetcher_has_all_required_methods():
    fetcher = _FakeDataFetcher()
    for name in (
        "fetch_calendar",
        "fetch_stock_list",
        "fetch_adjust_factor",
        "fetch_bars",
        "fetch_limit_price",
        "fetch_st_info",
        "fetch_bars_ext",
    ):
        assert callable(getattr(fetcher, name, None)), f"missing {name}"
