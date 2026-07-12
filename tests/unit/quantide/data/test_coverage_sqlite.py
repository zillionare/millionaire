"""FR-0303 AC-5/6: SQLite portfolio persistence uses a fresh tmp_path database."""

import datetime as dt

from quantide.core.enums import BidType, BrokerKind, OrderSide
from quantide.data.models.entities import Asset, Order, Portfolio, Position
from quantide.data.sqlite import SQLiteDB


def test_sqlite_portfolio_records_filter_update_and_cascade_in_isolated_file(tmp_path):
    """FR-0303 AC-5/6: cascade deletes one portfolio while preserving another."""
    database = SQLiteDB()
    database.init(tmp_path / "data.db")
    first = Portfolio("p1", BrokerKind.BACKTEST, dt.date(2024, 1, 1))
    second = Portfolio("p2", BrokerKind.BACKTEST, dt.date(2024, 1, 1))
    database.insert_portfolio(first)
    database.insert_portfolio(second)
    database.upsert_asset(Asset("p1", dt.date(2024, 1, 2), 100, 80, 0, 20, 100))
    database.upsert_positions(Position("p1", dt.date(2024, 1, 2), "A", 2, 2, 10, 0, 20))
    order = Order("p1", "A", OrderSide.BUY, 2, BidType.LATEST)
    database.insert_order(order)
    database.update_order(order.qtoid, status_msg="accepted")

    assert database.get_order(order.qtoid).status_msg == "accepted"
    assert database.query_assets("p1").height == 1
    assert database.query_positions("p1").height == 1
    database.delete_portfolio_cascade("p1")

    assert database.get_portfolio("p1") is None
    assert database.orders_all("p1").is_empty()
    assert database.get_portfolio("p2").portfolio_id == "p2"
