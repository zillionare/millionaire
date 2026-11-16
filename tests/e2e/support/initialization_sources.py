"""Small, complete historical source universe for wizard pipeline acceptance."""

import datetime
from contextlib import contextmanager
from unittest.mock import patch

import pandas as pd

from tests.e2e.support.tushare_stub import TushareStubConfig, patched_tushare_fetcher


class FixtureMinuteFetcher:
    """Expand the same daily fixture into complete, explicitly synthetic sessions."""

    def __init__(self, bars):
        self.bars = bars
        self.closed = False

    def fetch_minute_bars(self, asset, start, end, frequency="30"):
        bars = self.bars[
            (self.bars["asset"] == asset)
            & (self.bars["date"] >= pd.Timestamp(start))
            & (self.bars["date"] <= pd.Timestamp(end))
        ]
        rows = []
        for bar in bars.to_dict("records"):
            for opening in (datetime.time(9, 30), datetime.time(13)):
                for offset in range(int(frequency), 121, int(frequency)):
                    rows.append({
                        **bar,
                        "date": pd.Timestamp(datetime.datetime.combine(bar["date"].date(), opening)
                                     + datetime.timedelta(minutes=offset)),
                    })
        return pd.DataFrame(rows)

    def fetch_trading_status(self, asset, start, end):
        raise AssertionError("This fixture should provide every expected session")

    def close(self):
        self.closed = True


@contextmanager
def complete_initialization_sources():
    """Exercise every durable stage using a one-security source universe."""
    with patched_tushare_fetcher(TushareStubConfig(assets=("000001.SZ",))) as source:
        minutes = FixtureMinuteFetcher(source._bars)
        with patch("quantide.data.fetchers.baostock_minute.BaostockMinuteFetcher", return_value=minutes):
            yield source, minutes
