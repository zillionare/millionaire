"""sqlite 数据库封装类及ORM。开启 wal和多线程访问模式。初始化数据库表。

本模块定义了常用的数据模型，比如 Order, Trade, Position, Asset 等。同时还通过 Model class
实现了ORM。

## 01 Model class 及数据库表定义

sqlite_utils 赋予应用无须事先创建表结构的能力，但是，为了性能和数据类型精确性考虑，
手动创建数据库表是更好的方式。

Model class 自动将 dataclass 转换为数据库字段(schema)声明，从而可以用于创建数据库表结构（基于
sqlite_utils）。与 sqlalchemy 不同之处在于，我们利用 dataclass
的字段类型注解来自动推导数据库字段类型，而无须使用额外的语法。

具体的Entity 在继承 Entity 之后，可根据需要改写__post_init__方法，以完成数据库类型与 python
类型的转换。

Example:
```python
db = SQLiteDB("path/to/sqlite.db")

order = OrderModel(...)
db["orders"].insert(order)
```

所有读写操作都代理给 sqlite_utils 库的 Database 对象。

## API惯例

get_表明通过主键查询
get_*_by_*表明通过某个字段查询
*_all 表明查询所有数据

## 并发和多线程安全

数据库启用了 wal 模式，支持多进程、多线程并发读写。在高并发情况下，可能遇到 busy timeout
错误，此时需要进行重试，暂未实现。

本方案实现了一个基于线程的连接池。每一个线程都有自己的数据库连接，
因此不需要锁可以在多线程环境下并发执行。在使用时无须考虑申请和释放，直接使用 db 实例对象即可。
"""

import datetime
import sqlite3
import threading
import uuid
from collections.abc import Iterable
from dataclasses import fields
from pathlib import Path
from typing import (
    Any,
    TypeVar,
    cast,
)

import polars as pl
import sqlite_utils as su

from quantide.config.output_paths import external_runtime_path
from quantide.core.singleton import singleton
from quantide.data import portfolio_ledger
from quantide.data.models.app_state import AppState
from quantide.data.models.base import Entity, new_uuid_id
from quantide.data.models.entities import (
    Asset,
    BacktestLogEntry,
    Order,
    Portfolio,
    Position,
    StrategyLog,
    Trade,
)
from quantide.data.models.strategy_config import StrategyConfig, StrategyInfo
from quantide.data.models.sync_task import DataSyncTask

T = TypeVar("T")


@singleton
class SQLiteDB:
    def __init__(self) -> None:
        # 每个线程都有自己的数据库连接
        self._thread_local = threading.local()
        self._lock = threading.RLock()
        self._connection_generation = 0
        self._connections: set[sqlite3.Connection] = set()
        self.db_path: str = ""
        self._initialized = False

    def is_initialized_for(self, db_path: str | Path) -> bool:
        next_path = (
            ":memory:" if str(db_path) == ":memory:" else str(external_runtime_path(db_path))
        )
        return self._initialized and self.db_path == next_path and next_path != ":memory:"

    def init(self, db_path: str | Path) -> None:
        next_path = (
            ":memory:" if str(db_path) == ":memory:" else str(external_runtime_path(db_path))
        )
        with self._lock:
            if self.is_initialized_for(next_path):
                return

            # A connection may have been opened by this thread before the
            # application was rebound to another config directory.  Close it
            # before changing generations; connections owned by other threads
            # are retired lazily by ``db`` below, in their owning threads.
            self._close_thread_connection()
            self._connection_generation += 1
            self._initialized = False

            # 初始化数据库连接
            self.db_path = next_path

            self._connection_uri = (
                f"file:quantide-{uuid.uuid4().hex}?mode=memory&cache=shared"
                if self.db_path == ":memory:"
                else self.db_path
            )
            conn = self._open_connection()
            db = self._initialize_connection(conn, db_path)
            self._thread_local.conn = conn
            self._thread_local.db = db
            self._thread_local.generation = self._connection_generation
            self._initialized = True

    def _initialize_connection(
        self, connection: sqlite3.Connection, db_path: str | Path
    ) -> su.Database:
        try:
            database = su.Database(connection)
            if db_path != ":memory:":
                database.enable_wal()  # type: ignore[no-untyped-call]
            self._init_tables(database)
            connection.commit()
            connection.execute("PRAGMA foreign_keys = ON")
            return database
        except BaseException:
            connection.close()
            self._connections.discard(connection)
            raise

    def _close_thread_connection(self) -> None:
        """Close the current thread's connection, if one is open."""
        conn = getattr(self._thread_local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            finally:
                self._connections.discard(conn)
                del self._thread_local.conn
                if hasattr(self._thread_local, "db"):
                    del self._thread_local.db
                if hasattr(self._thread_local, "generation"):
                    del self._thread_local.generation
        # ``conn`` is normally resolved by ``__getattr__`` from the current
        # thread-local Database.  Remove any instance-level shadow so a
        # retired connection cannot bypass that proxy after a rebind.
        self.__dict__.pop("conn", None)

    @property
    def db(self) -> su.Database:
        """获取当前线程的数据库连接"""
        with self._lock:
            if not self._initialized:
                raise RuntimeError("SQLiteDB has not been initialized. Call init(db_path) first.")

            generation = self._connection_generation
            conn = getattr(self._thread_local, "conn", None)
            if (
                conn is not None
                and getattr(self._thread_local, "generation", None) == generation
                and self._connection_is_alive(conn)
            ):
                return cast(su.Database, self._thread_local.db)

            # A TestClient (and production ASGI servers) may handle a request
            # on a different thread from the one that initialized the app.
            # Rebind stale thread-local state instead of allowing a connection
            # from a previous app/config generation to leak into the request.
            self._close_thread_connection()
            conn = self._open_connection()

            # 启用外键约束
            conn.execute("PRAGMA foreign_keys = ON")

            self._thread_local.conn = conn
            self._thread_local.db = su.Database(conn)
            self._thread_local.generation = generation

            return cast(su.Database, self._thread_local.db)

    @staticmethod
    def _connection_is_alive(conn: sqlite3.Connection) -> bool:
        """Return whether a cached SQLite connection is still usable."""
        try:
            conn.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            return False
        return True

    def _open_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._connection_uri,
            uri=self.db_path == ":memory:",
            timeout=30,
            check_same_thread=False,
        )
        self._connections.add(connection)
        return connection

    def close(self) -> None:
        """Close all connections after the owner has quiesced request/background workers.

        Queries still use one connection per thread. Cross-thread close is enabled
        solely so idle thread-pool connections cannot retain files after shutdown.
        """
        with self._lock:
            for connection in tuple(self._connections):
                connection.close()
            self._connections.clear()
            self._close_thread_connection()

    def _init_tables(self, db: su.Database) -> None:
        """Initialize declared tables, adding compatible columns and indexes in place."""
        self._drop_obsolete_market_tables(db)
        db.execute(portfolio_ledger.SNAPSHOT_SCHEMA)
        for entity in (
            Order,
            Trade,
            Asset,
            Position,
            Portfolio,
            StrategyLog,
            BacktestLogEntry,
            StrategyConfig,
            StrategyInfo,
            AppState,
            DataSyncTask,
        ):
            self._ensure_entity_table(db, entity)

    def _ensure_entity_table(self, database: su.Database, entity: type[Entity]) -> None:
        table = cast(su.db.Table, database[entity.__table_name__])
        schema = entity.to_db_schema()
        table.create(schema, pk=entity.__pk__, if_not_exists=True)
        for column, kind in schema.items():
            if column not in table.columns_dict:
                table.add_column(column, kind)
        if entity.__indexes__ is not None:
            columns, unique = entity.__indexes__
            if columns:
                table.create_index(columns, unique=unique, if_not_exists=True)
        for foreign_key in getattr(entity, "__foreign_keys__", ()) or ():
            if len(foreign_key) == 3:
                source, destination, column = foreign_key
                table.add_foreign_key(source, destination, column, ignore=True)
                self._ensure_index_for_column(table, source)

    @staticmethod
    def _ensure_index_for_column(table: su.db.Table, column: str) -> None:
        """确保外键子表列有索引，避免删除父表行时逐行全表扫描。"""
        indexed_columns = {index.columns[0] for index in table.indexes if index.columns}
        if column not in indexed_columns:
            table.create_index([column], if_not_exists=True)

    def _drop_obsolete_market_tables(self, db: su.Database) -> None:
        """删除不再允许保存在 SQLite 中的行情和板块/指数元数据表。"""
        for table_name in (
            "sector_bars",
            "index_bars",
            "sectors",
            "sector_constituents",
            "indices",
        ):
            db.execute(f"DROP TABLE IF EXISTS {table_name}")

    def __getitem__(self, table_name: str) -> su.db.Table:
        """代理获取表对象"""
        return self.db[table_name]  # type: ignore

    def __getattr__(self, name: str) -> Any:
        """代理其他方法调用"""
        return getattr(self.db, name)

    def upsert_positions(self, positions: Iterable[Position] | Position) -> None:
        """保存(更新)持仓信息

        Args:
            positions: 持仓信息或持仓信息列表
        """
        if isinstance(positions, Position):
            self["positions"].upsert(positions.to_dict(), pk=Position.__pk__)
        else:
            self["positions"].upsert_all([p.to_dict() for p in positions], pk=Position.__pk__)

    def replace_positions(
        self,
        portfolio_id: str,
        dt: datetime.date,
        positions: Iterable[Position],
    ) -> None:
        """Replace the complete position snapshot for one portfolio/date.

        ``upsert_positions`` only inserts or updates rows.  A position that is
        sold to zero during the day would otherwise remain in the table and be
        picked up by the next history-fill run as a ghost holding.  Every date
        must therefore be written as a complete end-of-day snapshot.
        """
        portfolio_ledger.replace_positions(self.db.conn, portfolio_id, dt, positions)

    def save_portfolio_snapshot(self, asset: Asset, positions: Iterable[Position]) -> None:
        """Commit the complete account snapshot atomically."""
        portfolio_ledger.save_snapshot(self.db.conn, asset, positions)

    def save_paper_execution(
        self, order: Order, trade: Trade, asset: Asset, positions: Iterable[Position]
    ) -> None:
        """Commit execution and account facts atomically."""
        portfolio_ledger.save_execution(self.db.conn, order, trade, asset, positions)

    def get_positions(
        self, dt: datetime.date | None = None, portfolio_id: str | None = None
    ) -> pl.DataFrame:
        """获取持仓信息

        Args:
            dt: 指定日期，如果为 None 则获取最新一个日期的持仓
            portfolio_id: 指定组合 ID，如果为 None 则不限制组合
        """
        if dt is not None:
            return self.query_positions(portfolio_id=portfolio_id, start=dt, end=dt)

        # Legacy nonempty snapshots participate until an explicit empty marker
        # supersedes them. Each portfolio resolves its own latest date.
        latest = (
            "SELECT MAX(dt) FROM ("
            "SELECT dt FROM position_snapshots WHERE portfolio_id = positions.portfolio_id "
            "UNION ALL SELECT dt FROM positions AS prior "
            "WHERE prior.portfolio_id = positions.portfolio_id)"
        )
        where = (
            f"dt = ({latest})"
            if portfolio_id
            else (
                "dt = (SELECT MAX(dt) FROM (SELECT dt FROM positions "
                "UNION ALL SELECT dt FROM position_snapshots))"
            )
        )
        params: list[Any] = []
        if portfolio_id:
            where += " AND portfolio_id = ?"
            params.append(portfolio_id)

        rows = self["positions"].rows_where(where, params)
        df = pl.DataFrame(rows)
        if len(df) == 0:
            return pl.DataFrame()

        return df.with_columns(pl.col("dt").cast(pl.Date))

    def positions_all(self, portfolio_id: str | None = None) -> pl.DataFrame:
        """获取所有持仓信息"""
        return self.query_positions(portfolio_id=portfolio_id)

    def query_positions(
        self,
        portfolio_id: str | None = None,
        start: datetime.date | None = None,
        end: datetime.date | None = None,
    ) -> pl.DataFrame:
        """根据 portfolio_id 和时间范围查询持仓信息"""
        where_clauses = []
        params: list[Any] = []

        if portfolio_id:
            where_clauses.append("portfolio_id = ?")
            params.append(portfolio_id)
        if start:
            where_clauses.append("dt >= ?")
            params.append(start)
        if end:
            where_clauses.append("dt <= ?")
            params.append(end)

        where = " AND ".join(where_clauses) if where_clauses else None

        rows = self["positions"].rows_where(where, params)
        df = pl.DataFrame(rows)
        if len(df) == 0:
            return pl.DataFrame()

        return df.with_columns(pl.col("dt").cast(pl.Date))

    def insert_order(self, order: Order) -> str:
        """增加委托单（未提交）

        Args:
            order: 订单

        Returns:
            订单ID, 用于后续查询和更新。该订单 ID 为内部 id，而柜台或者第三方的 id。
        """
        self["orders"].insert(order.to_dict(), pk=Order.__pk__)
        return order.qtoid

    def get_order_by_foid(self, foid: str | int) -> Order | None:
        """根据 foid 获取订单

        foid 是外部接口（比如 qmt 给出的订单 ID），而 qtoid 是本系统收到委托时创建的 id。
        Args:
            foid: 订单 id

        Returns:
            订单 id
        """
        rows = self["orders"].rows_where("foid = ?", (str(foid),), limit=1)
        orders = list(rows)
        if len(orders) == 0:
            return None
        else:
            return Order(**orders[0])

    def get_order(self, qtoid: str) -> Order | None:
        """根据 qtoid 获取订单

        Args:
            qtoid: 订单 id

        Returns:
            订单
        """
        rows = self["orders"].rows_where("qtoid = ?", (qtoid,), limit=1)
        orders = list(rows)
        if len(orders) == 0:
            return None
        else:
            return Order(**orders[0])

    def get_orders(
        self, dt: datetime.date | None = None, portfolio_id: str | None = None
    ) -> pl.DataFrame:
        """获取订单信息

        Args:
            dt: 指定日期，如果为 None 则获取所有日期的订单
            portfolio_id: 指定组合 ID
        """
        if dt is not None:
            result = self.query_order_by_date(dt, portfolio_id)
            return result if result is not None else pl.DataFrame()

        return self.orders_all(portfolio_id)

    def query_order_by_date(
        self, dt: datetime.date, portfolio_id: str | None = None
    ) -> pl.DataFrame | None:
        """根据日期查询订单

        Args:
            dt: 日期
            portfolio_id: 组合 ID

        Returns:
            订单数据框
        """
        if isinstance(dt, datetime.datetime):
            dt = dt.date()

        where = "tm >= ? and tm < ?"
        params: list[Any] = [dt, dt + datetime.timedelta(days=1)]

        if portfolio_id:
            where += " and portfolio_id = ?"
            params.append(portfolio_id)

        rows = self["orders"].rows_where(where, params)
        df = pl.DataFrame(rows)
        if len(df) == 0:
            return None

        return df.with_columns(pl.col("tm").cast(pl.Datetime))

    def query_orders_range(
        self,
        start: datetime.date | datetime.datetime,
        end: datetime.date | datetime.datetime,
        portfolio_id: str | None = None,
    ) -> pl.DataFrame:
        """查询时间范围内的委托（包含 start 当天，截止 end 当天）。"""
        if isinstance(start, datetime.datetime):
            start = start.date()
        if isinstance(end, datetime.datetime):
            end = end.date()
        where = "tm >= ? and tm < ?"
        params: list[Any] = [start, end + datetime.timedelta(days=1)]
        if portfolio_id:
            where += " and portfolio_id = ?"
            params.append(portfolio_id)
        rows = self["orders"].rows_where(where, params)
        df = pl.DataFrame(rows)
        if len(df) == 0:
            return pl.DataFrame()
        return df.with_columns(pl.col("tm").cast(pl.Datetime))

    def orders_all(self, portfolio_id: str | None = None) -> pl.DataFrame:
        """获取所有订单信息"""
        if portfolio_id:
            rows = self["orders"].rows_where("portfolio_id = ?", (portfolio_id,))
        else:
            rows = self["orders"].rows
        df = pl.DataFrame(rows)
        if "tm" in df.columns:
            return df.with_columns(pl.col("tm").cast(pl.Datetime))
        return df

    def update_order(self, qtoid: str, **updates: Any) -> None:
        """更新订单信息

        Args:
            oid: 订单ID
            kwupdatesargs: 更新的字段
        """
        self["orders"].update(qtoid, updates)

    def insert_trades(self, trades: list[Trade] | Trade) -> None:
        """保存成交信息

        Args:
            trade: 成交信息
        """
        if isinstance(trades, Trade):
            trades = [trades]
        else:
            trades = trades

        self["trades"].insert_all([trade.to_dict() for trade in trades], ignore=True)

    def insert_strategy_logs(self, logs: list[StrategyLog] | StrategyLog) -> None:
        """保存策略日志

        Args:
            logs: 策略日志
        """
        if isinstance(logs, StrategyLog):
            logs = [logs]

        self["strategy_logs"].insert_all([log.to_dict() for log in logs], ignore=True)

    def insert_backtest_logs(
        self,
        logs: list[BacktestLogEntry] | BacktestLogEntry,
    ) -> None:
        """保存回测文本日志。

        Args:
            logs: 回测日志或日志列表。
        """
        if isinstance(logs, BacktestLogEntry):
            logs = [logs]

        self["backtest_logs"].insert_all(
            [log.to_dict() for log in logs],
            ignore=True,
        )

    def get_strategy_logs(
        self,
        portfolio_id: str | None = None,
        start: datetime.date | None = None,
        end: datetime.date | None = None,
    ) -> pl.DataFrame:
        """获取策略日志

        Args:
            portfolio_id: 组合 ID
            start: 开始日期
            end: 结束日期

        Returns:
            策略日志 DataFrame
        """
        where_clauses = []
        params: list[Any] = []

        if portfolio_id:
            where_clauses.append("portfolio_id = ?")
            params.append(portfolio_id)
        if start:
            where_clauses.append("dt >= ?")
            params.append(start)
        if end:
            where_clauses.append("dt <= ?")
            params.append(end)

        where = " AND ".join(where_clauses) if where_clauses else None

        if where:
            rows = self["strategy_logs"].rows_where(where, params)
        else:
            rows = self["strategy_logs"].rows

        df = pl.DataFrame(rows)
        if len(df) == 0:
            return pl.DataFrame()

        return df.with_columns(pl.col("dt").cast(pl.Datetime))

    def get_backtest_logs(
        self,
        portfolio_id: str | None = None,
        start: datetime.date | None = None,
        end: datetime.date | None = None,
    ) -> pl.DataFrame:
        """获取回测文本日志。

        Args:
            portfolio_id: 组合 ID。
            start: 开始日期。
            end: 结束日期。

        Returns:
            回测日志 DataFrame。
        """
        where_clauses = []
        params: list[Any] = []

        if portfolio_id:
            where_clauses.append("portfolio_id = ?")
            params.append(portfolio_id)
        if start:
            where_clauses.append("dt >= ?")
            params.append(start)
        if end:
            where_clauses.append("dt <= ?")
            params.append(end)

        where = " AND ".join(where_clauses) if where_clauses else None

        if where:
            rows = self["backtest_logs"].rows_where(where, params)
        else:
            rows = self["backtest_logs"].rows

        df = pl.DataFrame(rows)
        if len(df) == 0:
            return pl.DataFrame()

        return df.with_columns(pl.col("dt").cast(pl.Datetime))

    def get_trade(self, tid: str) -> Trade | None:
        """根据 tid 获取成交

        Args:
            tid: 成交 id

        Returns:
            成交
        """
        rows = self["trades"].rows_where("tid = ?", (tid,), limit=1)
        trades = list(rows)
        if len(trades) == 0:
            return None
        else:
            return Trade(**trades[0])

    def query_trade(self, qtoid: str | None = None, foid: str | None = None) -> pl.DataFrame | None:
        """通过 qtoid, foid 或者 tid查询成交

            Args:
                qtoid: 查询指定 qtoid 的成交
                foid: 查询指定 foid 的成交

        Returns:
            成交数据框
        """
        filters = []
        params = {"qtoid": qtoid, "foid": foid}

        for param in params:
            if params[param]:
                filters.append(f"{param} = :{param}")

        if len(filters) == 0:
            return pl.DataFrame(self["trades"].rows).with_columns(pl.col("tm").cast(pl.Datetime))

        where_clause = " OR ".join(filters)
        rows = self["trades"].rows_where(where_clause, params)
        df = pl.DataFrame(rows)
        if len(df) == 0:
            return None

        return df.with_columns(pl.col("tm").cast(pl.Datetime))

    def get_trades(
        self, dt: datetime.date | None = None, portfolio_id: str | None = None
    ) -> pl.DataFrame:
        """获取成交信息

        Args:
            dt: 指定日期，如果为 None 则获取所有日期的成交
            portfolio_id: 指定组合 ID
        """
        if dt is not None:
            return self.query_trades_by_date(dt, portfolio_id)

        return self.trades_all(portfolio_id)

    def query_trades_by_date(
        self, dt: datetime.date, portfolio_id: str | None = None
    ) -> pl.DataFrame:
        """根据日期查询成交

        Args:
            dt: 日期
            portfolio_id: 组合 ID

        Returns:
            成交数据框
        """
        if isinstance(dt, datetime.datetime):
            dt = dt.date()

        where = "tm >= ? and tm < ?"
        params: list[Any] = [dt, dt + datetime.timedelta(days=1)]

        if portfolio_id:
            where += " and portfolio_id = ?"
            params.append(portfolio_id)

        rows = self["trades"].rows_where(where, params)
        df = pl.DataFrame(rows)
        if len(df) == 0:
            return pl.DataFrame()

        return df.with_columns(pl.col("tm").cast(pl.Datetime))

    def query_trades_range(
        self,
        start: datetime.date | datetime.datetime,
        end: datetime.date | datetime.datetime,
        portfolio_id: str | None = None,
    ) -> pl.DataFrame:
        """查询时间范围内的成交（包含 start 当天，截止 end 当天）。"""
        if isinstance(start, datetime.datetime):
            start = start.date()
        if isinstance(end, datetime.datetime):
            end = end.date()
        where = "tm >= ? and tm < ?"
        params: list[Any] = [start, end + datetime.timedelta(days=1)]
        if portfolio_id:
            where += " and portfolio_id = ?"
            params.append(portfolio_id)
        rows = self["trades"].rows_where(where, params)
        df = pl.DataFrame(rows)
        if len(df) == 0:
            return pl.DataFrame()
        return df.with_columns(pl.col("tm").cast(pl.Datetime))

    def trades_all(self, portfolio_id: str | None = None) -> pl.DataFrame:
        """获取所有成交信息"""
        if portfolio_id:
            rows = self["trades"].rows_where("portfolio_id = ?", (portfolio_id,))
        else:
            rows = self["trades"].rows

        df = pl.DataFrame(rows)
        if len(df) == 0:
            return pl.DataFrame()

        return df.with_columns(pl.col("tm").cast(pl.Datetime))

    def get_asset(
        self, dt: datetime.date | None = None, portfolio_id: str | None = None
    ) -> Asset | None:
        """获取指定日期和组合的资产信息

        Args:
            dt: 查询日期，如果为 None 则获取最新一条
            portfolio_id: 组合 ID，如果为 None 则不限制组合
        """
        if dt is None:
            return self._get_latest_asset(portfolio_id)

        if isinstance(dt, datetime.datetime):
            dt = dt.date()

        where = "dt = ?"
        params: list[Any] = [dt]
        if portfolio_id:
            where += " AND portfolio_id = ?"
            params.append(portfolio_id)

        rows = self["assets"].rows_where(where, params, limit=1)
        assets = list(rows)
        if len(assets) == 0:
            return None
        else:
            return Asset(**assets[0])

    def _get_latest_asset(self, portfolio_id: str | None = None) -> Asset | None:
        """获取最新资产信息

        Args:
            portfolio_id: 组合(策略）ID，如果为 None 则不限制组合
        """
        where = None
        params: list[Any] = []
        if portfolio_id:
            where = "portfolio_id = ?"
            params = [portfolio_id]

        rows = self["assets"].rows_where(where, params, limit=1, order_by="dt DESC")
        assets = list(rows)
        if len(assets) == 0:
            return None
        else:
            return Asset(**assets[0])

    def assets_all(self, portfolio_id: str | None = None) -> pl.DataFrame:
        """获取所有资产信息

        Returns:
            pl.DataFrame: 资产信息 DataFrame
        """
        return self.query_assets(portfolio_id)

    def query_assets(
        self,
        portfolio_id: str | None = None,
        start: datetime.date | None = None,
        end: datetime.date | None = None,
    ) -> pl.DataFrame:
        """根据 portfolio_id 和时间范围查询资产信息"""
        where_clauses = []
        params: list[Any] = []

        if portfolio_id:
            where_clauses.append("portfolio_id = ?")
            params.append(portfolio_id)
        if start:
            where_clauses.append("dt >= ?")
            params.append(start)
        if end:
            where_clauses.append("dt <= ?")
            params.append(end)

        where = " AND ".join(where_clauses) if where_clauses else None

        rows = self["assets"].rows_where(where, params)
        df = pl.DataFrame(rows, infer_schema_length=None)
        if len(df) == 0:
            return pl.DataFrame()

        return df.with_columns(pl.col("dt").cast(pl.Date))

    def upsert_asset(self, asset: Asset | list[Asset]) -> None:
        """保存(更新)资产信息

        Args:
            asset: 资产信息或资产信息列表
        """
        if isinstance(asset, Asset):
            assert asset.principal is not None, "资产信息中本金不能为空"
            self["assets"].upsert(asset.to_dict(), pk=Asset.__pk__)
        else:
            dicts = []
            for a in asset:
                assert a.principal is not None, "资产信息中本金不能为空"
                dicts.append(a.to_dict())
            self["assets"].upsert_all(dicts, pk=Asset.__pk__)

    def update_asset(self, dt: datetime.date, portfolio_id: str, **updates: Any) -> None:
        """更新资产信息

        与 save_asset 不同，本方法允许单字段更新
        """
        if isinstance(dt, datetime.datetime):
            dt = dt.date()
        row = {"portfolio_id": portfolio_id, "dt": dt, **updates}
        self["assets"].upsert(row, pk=Asset.__pk__)

    def insert_portfolio(self, portfolio: Portfolio) -> None:
        """插入组合信息"""
        self["portfolios"].insert(portfolio.to_dict(), pk=Portfolio.__pk__)

    def get_portfolio(self, portfolio_id: str) -> Portfolio | None:
        """获取组合信息"""
        rows = list(self["portfolios"].rows_where("portfolio_id = ?", (portfolio_id,)))
        if len(rows) == 0:
            return None
        else:
            # Filter unknown fields (e.g. strategy_name which was removed)
            row = rows[0]
            valid_fields = {f.name for f in fields(Portfolio)}
            row = {k: v for k, v in row.items() if k in valid_fields}
            return Portfolio(**row)

    def get_all_portfolios(self) -> list[Portfolio]:
        """获取所有组合信息"""
        rows = list(self["portfolios"].rows)
        valid_fields = {f.name for f in fields(Portfolio)}
        portfolios = []
        for row in rows:
            # Filter unknown fields
            row = {k: v for k, v in row.items() if k in valid_fields}
            portfolios.append(Portfolio(**row))
        return portfolios

    def delete_portfolio(self, portfolio_id: str) -> None:
        """删除组合信息"""
        self["portfolios"].delete(portfolio_id)

    def delete_portfolio_cascade(self, portfolio_id: str) -> None:
        """级联删除组合及其所有关联数据。

        按外键依赖顺序删除：backtest_logs -> strategy_logs -> trades -> orders
        -> positions -> assets -> portfolio。

        Args:
            portfolio_id: 组合 ID。
        """
        self["backtest_logs"].delete_where("portfolio_id = ?", (portfolio_id,))
        self["strategy_logs"].delete_where("portfolio_id = ?", (portfolio_id,))
        self["trades"].delete_where("portfolio_id = ?", (portfolio_id,))
        self["orders"].delete_where("portfolio_id = ?", (portfolio_id,))
        self["positions"].delete_where("portfolio_id = ?", (portfolio_id,))
        self["assets"].delete_where("portfolio_id = ?", (portfolio_id,))
        try:
            self["portfolios"].delete(portfolio_id)
        except Exception:
            pass

    def portfolios_all(self) -> pl.DataFrame:
        """获取所有组合信息"""
        return pl.DataFrame(self["portfolios"].rows)

    def get_portfolios_by_strategy(self, strategy_name: str) -> pl.DataFrame:
        """根据策略名称获取组合信息"""
        rows = self["portfolios"].rows_where("name = ?", (strategy_name,))
        df = pl.DataFrame(rows)
        if len(df) == 0:
            return pl.DataFrame()
        # Normalize dates returned as strings by sqlite-utils.
        # Polars handles string to date conversion if we cast
        return df.with_columns([pl.col("start").cast(pl.Date), pl.col("end").cast(pl.Date)])

    def update_portfolio(self, portfolio_id: str, **updates: Any) -> None:
        """更新组合信息

        Args:
            portfolio_id: 组合ID
            **updates: 要更新的字段及其值
        """
        self["portfolios"].update(portfolio_id, updates)


db: SQLiteDB = SQLiteDB()

__all__ = [
    "Asset",
    "BacktestLogEntry",
    "Entity",
    "Order",
    "Portfolio",
    "Position",
    "StrategyLog",
    "Trade",
    "db",
    "new_uuid_id",
]
