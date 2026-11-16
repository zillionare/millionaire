"""Backtest portfolio history and snapshot maintenance."""

import datetime
from typing import TYPE_CHECKING

import polars as pl

from quantide.core.enums import FrameType
from quantide.data.models import Asset, Position
from quantide.data.models.calendar import calendar
from quantide.data.sqlite import db


def _position_snapshot_frame(
    self: "BacktestSnapshots", latest_pos: pl.DataFrame, fill_dates: list[datetime.date]
) -> pl.DataFrame:
    """Position snapshot frame."""
    assets = latest_pos["asset"].unique().to_list()
    start, end = fill_dates[0], fill_dates[-1]

    # 1. 获取行情与复权因子（包含前一交易日，用于基准）
    old_date = calendar.day_shift(start, -1)
    prices_df = self._get_close_adjust_factors(assets, old_date, end)
    prices_df = prices_df.sort(["asset", "date"])

    base_factors = prices_df.filter(pl.col("date") == old_date).select(
        [
            pl.col("asset"),
            pl.col("adjust").alias("base_adjust"),
        ]
    )
    first_factors = prices_df.group_by("asset").agg(pl.col("adjust").first().alias("first_adjust"))

    # 3. 构造填充模板
    pos_template = (
        latest_pos.select(
            [
                pl.col("asset"),
                pl.col("shares"),
                pl.col("price"),
                (pl.col("mv") / pl.col("shares")).alias("last_mkt_price"),
            ]
        )
        .join(base_factors, on="asset", how="left")
        .join(first_factors, on="asset", how="left")
        .with_columns(
            pl.coalesce(
                pl.col("base_adjust"),
                pl.col("first_adjust"),
                pl.lit(1.0),
            ).alias("seed_adjust")
        )
    )

    fill_df = pl.DataFrame({"date": fill_dates}).join(pos_template, how="cross")

    # 4. 合并行情并处理缺失值
    fill_df = fill_df.join(prices_df, on=["date", "asset"], how="left").sort(["asset", "date"])
    return fill_df


class BacktestSnapshots:
    """Backtest portfolio history and snapshot maintenance."""

    if TYPE_CHECKING:
        _portfolio_id: str
        _positions: dict[str, Position]

        def _get_close_adjust_factors(
            self, assets: list[str], start: datetime.date, end: datetime.date
        ) -> pl.DataFrame: ...

    def _fill_history_gaps(self, end_fill: datetime.date) -> None:
        """填补历史数据缺失，确保资产记录和持仓记录完整

        本方法要求在每一次交易时，都要更新数据库中的 asset 和 position 记录。

        Args:
            end_fill (datetime.date): 填充到的结束日期，一般为 clock 前一日
        """
        # 1. 获取需要填补的日期范围
        # 在回测场景下， latest_asset一定存在，这是 init_backtest 保证的
        latest_asset: Asset = db.get_asset(portfolio_id=self._portfolio_id)  # type: ignore

        start_fill = calendar.day_shift(latest_asset.dt, 1)

        fill_dates = calendar.get_frames(start_fill, end_fill, FrameType.DAY)
        if not fill_dates:
            return

        # 2. 获取与最新资产记录同日的持仓快照。
        #
        # 清仓后的最新资产日可能已经没有任何持仓记录；如果这里退回到 positions
        # 表中的“最新日期”，会把更早一天的历史仓位重新带回来，导致后续填仓时在
        # 空仓日期重新出现 market_value。
        latest_pos = db.get_positions(dt=latest_asset.dt, portfolio_id=self._portfolio_id)

        if latest_pos.is_empty():
            self._fill_assets_only(fill_dates, latest_asset)
        else:
            self._fill_positions_and_assets(fill_dates, latest_pos, latest_asset)

    def _fill_assets_only(self, fill_dates: list[datetime.date], last_asset: Asset) -> None:
        """无持仓时，仅同步资产日期"""
        assets_to_insert = [
            Asset(
                portfolio_id=self._portfolio_id,
                dt=d,
                principal=last_asset.principal,
                cash=last_asset.cash,
                frozen_cash=float(last_asset.frozen_cash or 0.0),
                market_value=0.0,
                total=last_asset.cash,
            )
            for d in fill_dates
        ]
        db.upsert_asset(assets_to_insert)

    def _fill_positions_and_assets(
        self, fill_dates: list[datetime.date], latest_pos: pl.DataFrame, last_asset: Asset
    ) -> None:
        """有持仓时，计算行情变动及复权折算

        在复权发生时，按现金折算持仓价值，更新资产记录。

        Args:
            fill_dates (list[datetime.date]): 填充的日期列表
            latest_pos (pl.DataFrame): 最新持仓 DataFrame
            last_asset (Asset): 上一个交易日的资产记录
        """
        fill_df = _position_snapshot_frame(self, latest_pos, fill_dates)

        fill_df = fill_df.with_columns(
            [
                pl.col("close").fill_null(strategy="forward").over("asset"),
                pl.col("adjust").fill_null(strategy="forward").over("asset"),
            ]
        ).with_columns(
            [
                pl.col("close").fill_null(pl.col("last_mkt_price")).over("asset"),
                pl.col("adjust").fill_null(pl.col("seed_adjust")).over("asset"),
            ]
        )

        # 5. 按复权因子调整持仓，而不是现金补偿。
        #
        # 数据源只提供累计复权因子，无法可靠区分现金分红与拆股。按更合理的
        # 拆股假设处理：adjust_ratio = r 时，股数乘以 r、成本除以 r，raw price
        # 变为原来的 1/r，持仓总市值在除权前后保持不变。这样后续涨跌始终作用
        # 在完整的经济仓位上；对现金分红而言，等价于把分红再投资。
        fill_df = (
            fill_df.with_columns(
                pl.col("adjust")
                .shift(1)
                .over("asset")
                .fill_null(pl.col("seed_adjust"))
                .alias("prev_adjust")
            )
            .with_columns(
                [
                    pl.when((pl.col("adjust") > 0) & (pl.col("prev_adjust") > 0))
                    .then(pl.col("adjust") / pl.col("prev_adjust"))
                    .otherwise(pl.lit(1.0))
                    .alias("adjust_ratio"),
                ]
            )
            .with_columns(
                [
                    pl.col("adjust_ratio").cum_prod().over("asset").alias("cum_adjust_ratio"),
                ]
            )
            .with_columns(
                [
                    # A 股股数必须为整数：现金分红按拆股近似会产生小数，取整后再
                    # 用「总成本不变」反推每股成本，避免宿主卖出时因零股被拒。
                    # 与 _apply_day_adjustment 的 round() 保持一致（half-to-even）
                    (pl.col("shares") * pl.col("cum_adjust_ratio"))
                    .round(0)
                    .cast(pl.Int64)
                    .alias("new_shares"),
                ]
            )
            .with_columns(
                [
                    pl.when(pl.col("new_shares") > 0)
                    .then((pl.col("shares") * pl.col("price")) / pl.col("new_shares"))
                    .otherwise(pl.col("price"))
                    .alias("new_price"),
                ]
            )
            .with_columns(
                [
                    (pl.col("new_shares") * pl.col("close")).alias("mv"),
                    ((pl.col("close") - pl.col("new_price")) * pl.col("new_shares")).alias(
                        "profit"
                    ),
                ]
            )
        )

        # 6. 汇总每日统计量。公司行为不产生现金，现金余额保持不变。
        daily_stats = (
            fill_df.group_by("date")
            .agg(
                [
                    pl.col("mv").sum().alias("market_value"),
                ]
            )
            .sort("date")
        )
        daily_stats = daily_stats.with_columns(pl.lit(last_asset.cash).alias("new_cash"))

        # 同步更新内存中的现金余额，供展仓后的下一笔交易使用
        self._cash = daily_stats["new_cash"][-1]

        # 同步内存持仓的股数/成本/市值，后续策略和风控 overlay 读取的是调整后的值
        for row in fill_df.sort("date").group_by("asset").last().iter_rows(named=True):
            pos = self._positions.get(row["asset"])
            if pos is None:
                continue
            pos.shares = row["new_shares"]
            pos.price = row["new_price"]
            pos.mv = row["mv"]
            pos.profit = row["profit"]
            pos.avail = row["new_shares"]
            pos.dt = row["date"]

        # 7. 批量更新数据库 (资产表和持仓表)
        self._batch_update_history(fill_df, daily_stats, last_asset)

    def _batch_update_history(
        self, fill_df: pl.DataFrame, daily_stats: pl.DataFrame, last_asset: Asset
    ) -> None:
        """执行数据库批量更新"""
        # 批量写入持仓记录。每个日期必须写成完整快照，否则已清仓的标的
        # 会残留在当天记录中，并在下一次 fill_history_gap 时被当成持仓。
        for (fill_date,), group in fill_df.group_by("date", maintain_order=True):
            positions = [
                Position(
                    portfolio_id=self._portfolio_id,
                    dt=row["date"],
                    asset=row["asset"],
                    shares=row["new_shares"],
                    price=row["new_price"],
                    avail=row["new_shares"],
                    mv=row["mv"],
                    profit=row["profit"],
                )
                for row in group.to_dicts()
            ]
            db.replace_positions(self._portfolio_id, fill_date, positions)

        # 批量写入资产记录 (核心：更新每一天的 cash 字段)
        assets_to_insert = [
            Asset(
                portfolio_id=self._portfolio_id,
                dt=row["date"],
                principal=last_asset.principal,
                cash=row["new_cash"],  # 正确反映每日现金变动
                frozen_cash=float(last_asset.frozen_cash or 0.0),
                market_value=row["market_value"],
                total=row["new_cash"] + row["market_value"],
            )
            for row in daily_stats.to_dicts()
        ]
        db.upsert_asset(assets_to_insert)
