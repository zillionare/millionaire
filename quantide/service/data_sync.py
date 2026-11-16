"""数据同步服务：阶段编排、断点续传、并发互斥。

与旧版 ``data_market`` 页面的差异：

* 任务**持久化**在 SQLite（``data_sync_tasks``）→ 进程重启后可恢复；
* **阶段化**：日历 → 证券列表 → 日线 → 市值 → 指数日线 → 指数成分；
* **按月批量**抓取（Tushare ``daily`` 支持区间查询）→ 比逐日快一个数量级；
* **单实例互斥**：同一数据集不并发同步；
* 指数成分**逐期**抓取（``index_weight`` 区间查询有 7000 行上限）。
"""

from __future__ import annotations

import datetime
import json
import threading
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from quantide.core.message import msg_hub
from quantide.data.coverage import trading_sessions
from quantide.data.models.sync_task import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    SYNC_STAGES,
    DataSyncTask,
)
from quantide.data.sqlite import db
from quantide.service.minute_backfill import (
    MINUTE_HISTORY_READY_TIME as MINUTE_HISTORY_READY_TIME,
)
from quantide.service.minute_backfill import (
    MINUTE_HISTORY_START as MINUTE_HISTORY_START,
)
from quantide.service.minute_backfill import (
    MinuteBackfill,
)
from quantide.service.minute_backfill import (
    _minute_history_end as _minute_history_end,
)

#: 同步进度主题
SYNC_PROGRESS_TOPIC = "data_sync_progress"


@dataclass
class SyncParams:
    """同步参数。"""

    start_date: datetime.date
    end_date: datetime.date
    index_codes: list[str] = field(default_factory=list)
    include_minute: bool = True
    minute_frequency: str = "30"
    minute_assets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转成可 JSON 序列化的字典。"""
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "index_codes": list(self.index_codes),
            "include_minute": self.include_minute,
            "minute_frequency": self.minute_frequency,
            "minute_assets": list(self.minute_assets),
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> SyncParams:
        """从字典还原。"""
        start = payload.get("start_date")
        end = payload.get("end_date")
        return SyncParams(
            start_date=datetime.date.fromisoformat(str(start)),
            end_date=datetime.date.fromisoformat(str(end)),
            index_codes=list(payload.get("index_codes") or []),
            include_minute=bool(payload.get("include_minute")),
            minute_frequency=str(payload.get("minute_frequency") or "30"),
            minute_assets=list(payload.get("minute_assets") or []),
        )


def _publish(payload: dict[str, Any]) -> None:
    """广播进度。"""
    try:
        msg_hub.publish(topic=SYNC_PROGRESS_TOPIC, msg_content=payload)
    except Exception:  # pragma: no cover - 消息总线异常不影响同步
        pass


class DataSyncService:
    """数据同步编排器（单例）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running_task_id: str | None = None
        self._cancel = threading.Event()

    # ------------------------------------------------------------------
    # 任务持久化
    # ------------------------------------------------------------------
    def _ensure_table(self) -> None:
        if DataSyncTask.__table_name__ in db.tables:
            return
        schema = DataSyncTask.to_db_schema()
        table = db[DataSyncTask.__table_name__]
        table.create(schema, pk=DataSyncTask.__pk__, if_not_exists=True)
        for col, typ in schema.items():
            if typ is str and col not in ("task_id", "status", "stages", "params"):
                table.create_index([col], if_not_exists=True)

    def create_task(self, params: SyncParams) -> DataSyncTask:
        """创建任务（持久化）。"""
        self._ensure_table()
        task = DataSyncTask(
            status=STATUS_PENDING,
            params=json.dumps(params.to_dict(), ensure_ascii=False),
            message="等待执行",
        )
        db[DataSyncTask.__table_name__].insert(task.to_dict(), pk=DataSyncTask.__pk__, replace=True)
        return task

    def get_task(self, task_id: str) -> DataSyncTask | None:
        """读取任务。"""
        self._ensure_table()
        rows = list(db[DataSyncTask.__table_name__].rows_where("task_id = ?", (task_id,)))
        if not rows:
            return None
        row = dict(rows[0])
        return DataSyncTask(
            **{k: v for k, v in row.items() if k in DataSyncTask.__dataclass_fields__}
        )

    def list_tasks(self, limit: int = 20) -> list[DataSyncTask]:
        """列出最近的任务。"""
        self._ensure_table()
        rows = list(
            db[DataSyncTask.__table_name__].rows_where(order_by="created_at desc", limit=limit)
        )
        return [
            DataSyncTask(
                **{k: v for k, v in dict(row).items() if k in DataSyncTask.__dataclass_fields__}
            )
            for row in rows
        ]

    def _update_task(self, task_id: str, **fields: Any) -> None:
        """更新任务状态。"""
        self._ensure_table()
        data = {k: v for k, v in fields.items() if k in DataSyncTask.__dataclass_fields__}
        if "stages" in data and not isinstance(data["stages"], str):
            data["stages"] = json.dumps(data["stages"], ensure_ascii=False)
        if "params" in data and not isinstance(data["params"], str):
            data["params"] = json.dumps(data["params"], ensure_ascii=False)
        db[DataSyncTask.__table_name__].update(task_id, data)

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        """是否有任务在执行。"""
        with self._lock:
            return self._running_task_id is not None

    def cancel(self) -> bool:
        """请求取消当前任务。"""
        with self._lock:
            if self._running_task_id is None:
                return False
        self._cancel.set()
        return True

    def run(self, task_id: str) -> bool:
        """执行一个同步任务（同步调用）。

        Args:
            task_id: 任务 ID。

        Returns:
            bool: 是否成功完成。
        """
        task = self.get_task(task_id)
        if task is None:
            return False
        params = SyncParams.from_dict(task.to_params())
        done_stages = task.stage_list()

        with self._lock:
            if self._running_task_id is not None:
                logger.warning("已有同步任务在执行，跳过本次启动")
                return False
            self._running_task_id = task_id
            self._cancel.clear()

        self._update_task(
            task_id,
            status=STATUS_RUNNING,
            started_at=datetime.datetime.now(),
            error="",
            message="开始同步",
        )
        try:
            for index, stage in enumerate(SYNC_STAGES):
                if self._cancel.is_set():
                    self._update_task(task_id, status=STATUS_CANCELLED, message="已取消")
                    return False
                if stage in done_stages:
                    continue
                percent = int(index * 100 / len(SYNC_STAGES))
                self._update_task(task_id, progress=percent, message=f"正在同步 {stage}...")
                _publish(
                    {
                        "task_id": task_id,
                        "stage": stage,
                        "progress": percent,
                        "message": f"正在同步 {stage}...",
                    }
                )
                try:
                    self._run_stage(stage, params)
                except Exception as exc:
                    logger.exception("同步阶段失败: {}", stage)
                    self._update_task(
                        task_id,
                        status=STATUS_FAILED,
                        error=str(exc),
                        message=f"{stage} 失败",
                    )
                    _publish(
                        {
                            "task_id": task_id,
                            "stage": stage,
                            "progress": percent,
                            "error": str(exc),
                            "message": f"{stage} 失败",
                        }
                    )
                    return False
                if self._cancel.is_set():
                    self._update_task(task_id, status=STATUS_CANCELLED, message="已取消")
                    return False
                done_stages.append(stage)
                self._update_task(
                    task_id, stages=done_stages, progress=int((index + 1) * 100 / len(SYNC_STAGES))
                )

            self._update_task(
                task_id,
                status=STATUS_DONE,
                progress=100,
                message="同步完成",
                finished_at=datetime.datetime.now(),
            )
            _publish(
                {
                    "task_id": task_id,
                    "stage": "done",
                    "progress": 100,
                    "completed": True,
                    "message": "同步完成",
                }
            )
            return True
        finally:
            with self._lock:
                self._running_task_id = None

    # ------------------------------------------------------------------
    # 各阶段实现
    # ------------------------------------------------------------------
    def _run_stage(self, stage: str, params: SyncParams) -> None:
        """执行单个同步阶段。"""
        if stage == "calendar":
            self._sync_calendar(params)
        elif stage == "stock_list":
            self._sync_stock_list(params)
        elif stage == "daily_bars":
            self._sync_daily_bars(params)
        elif stage == "daily_basic":
            self._sync_daily_basic(params)
        elif stage == "index_bars":
            self._sync_index_bars(params)
        elif stage == "index_weight":
            self._sync_index_weight(params)
        elif stage == "minute_bars":
            self._sync_minute_bars(params)
        else:  # pragma: no cover - 未知阶段
            raise ValueError(f"未知同步阶段: {stage}")

    @staticmethod
    def _month_ranges(
        start: datetime.date, end: datetime.date
    ) -> list[tuple[datetime.date, datetime.date]]:
        """把区间按自然月切分（批量抓取用）。"""
        ranges: list[tuple[datetime.date, datetime.date]] = []
        cursor = start.replace(day=1)
        while cursor <= end:
            if cursor.month == 12:
                nxt = cursor.replace(year=cursor.year + 1, month=1)
            else:
                nxt = cursor.replace(month=cursor.month + 1)
            chunk_end = min(nxt - datetime.timedelta(days=1), end)
            ranges.append((max(cursor, start), chunk_end))
            cursor = nxt
        return ranges

    def _sync_calendar(self, params: SyncParams) -> None:
        """同步交易日历。

        必须从配置的 epoch（默认 2005）拉取完整日历再一次性保存；
        如果按本次同步的 ``start_date`` 拉取并覆盖，会把历史日历截断，
        导致 ``day_shift`` 在回测起始日附近算出错误的上一交易日。
        """
        _ = params
        from quantide.data.models.calendar import calendar

        calendar.update()

    def _sync_stock_list(self, params: SyncParams) -> None:
        """同步证券主数据。"""
        from quantide.data.fetchers.registry import get_data_fetcher
        from quantide.data.models.stocks import stock_list

        fetcher = get_data_fetcher()
        frame = fetcher.fetch_stock_list()
        if frame is None or len(frame) == 0:
            raise RuntimeError("证券列表同步无数据，保留已有数据")
        stock_list.save(frame)

    def _sync_daily_bars(self, params: SyncParams) -> None:
        """同步个股日线（按月批量）。"""
        from quantide.data.models.daily_bars import daily_bars

        for chunk_start, chunk_end in self._month_ranges(params.start_date, params.end_date):
            if self._cancel.is_set():
                return
            daily_bars.fetch(chunk_start, chunk_end)

    def _sync_daily_basic(self, params: SyncParams) -> None:
        """同步市值/换手（按月批量）。"""
        from quantide.data.models.calendar import calendar
        from quantide.data.models.daily_basic import daily_basic

        daily_basic.load()
        available = (
            set(daily_basic.data["date"].to_list()) if not daily_basic.data.is_empty() else set()
        )
        for chunk_start, chunk_end in self._month_ranges(params.start_date, params.end_date):
            if self._cancel.is_set():
                return
            dates = sorted(set(trading_sessions(calendar, chunk_start, chunk_end)) - available)
            if not dates:
                continue
            daily_basic.update(dates=dates)

    def _sync_index_bars(self, params: SyncParams) -> None:
        """同步指数日线。"""
        if not params.index_codes:
            return
        from quantide.data import get_index_bars_store
        from quantide.data.fetchers.registry import get_data_fetcher

        fetcher = get_data_fetcher()
        frame, errors = fetcher.fetch_index_bars(
            params.index_codes, params.start_date, params.end_date
        )
        if errors:
            raise RuntimeError(f"指数行情同步失败: {errors}")
        if frame is None or len(frame) == 0:
            raise RuntimeError("指数行情同步无数据，保留已有数据")
        store = get_index_bars_store()
        store.append_data(_to_index_bars_frame(frame))

    def _sync_minute_bars(self, params: SyncParams) -> None:
        """Backfill supported minutes and evict only committed, verified intervals."""
        if params.include_minute or params.minute_assets:
            MinuteBackfill(params, self._cancel, _publish).run()

    def _sync_index_weight(self, params: SyncParams) -> None:
        """同步指数成分（逐期抓取，绕过 7000 行上限）。"""
        if not params.index_codes:
            return
        from quantide.data import get_index_weight_store
        from quantide.data.fetchers.registry import get_data_fetcher

        fetcher = get_data_fetcher()
        store = get_index_weight_store()
        snapshots = _month_end_snapshots(params.start_date, params.end_date)
        if not snapshots:
            return
        frame, errors = fetcher.fetch_index_weights(params.index_codes, snapshots)
        if errors:
            raise RuntimeError(f"指数成分同步失败: {errors}")
        if frame is None or len(frame) == 0:
            return
        store.append_data(frame)


def _to_minute_bars_frame(frame: Any) -> Any:
    """把分钟线转成存储字段（date 保留时分，单位：手/千元）。"""
    import polars as pl

    out = frame if isinstance(frame, pl.DataFrame) else pl.from_pandas(frame)
    if "date" in out.columns:
        out = out.with_columns(pl.col("date").cast(pl.Datetime("ms")))
    cols = ["date", "asset", "open", "high", "low", "close", "volume", "amount"]
    for col in cols:
        if col not in out.columns:
            out = out.with_columns(pl.lit(None).alias(col))
    return out.select(cols)


def _to_index_bars_frame(frame: Any) -> Any:
    """把指数日线转成存储层字段（sector_id 作为指数代码）。"""
    import polars as pl

    if isinstance(frame, pl.DataFrame):
        out = frame
    else:
        out = pl.from_pandas(frame)
    if "index_code" in out.columns and "sector_id" not in out.columns:
        out = out.rename({"index_code": "sector_id"})
    if "date" in out.columns:
        out = out.with_columns(pl.col("date").cast(pl.Date))
    return out


def _month_end_snapshots(start: datetime.date, end: datetime.date) -> list[datetime.date]:
    """列出区间内每个自然月的月末（成分快照日候选）。"""
    from quantide.data.models.calendar import calendar

    try:
        frames = calendar.get_frames(
            start, end, __import__("quantide.core.enums", fromlist=["FrameType"]).FrameType.MONTH
        )
    except Exception:  # pragma: no cover - 日历不可用
        frames = []
    return [f for f in frames if isinstance(f, datetime.date) and start <= f <= end]


#: 全局单例
data_sync_service = DataSyncService()
