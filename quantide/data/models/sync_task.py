"""数据同步任务的持久化模型与状态机.

同步任务写入 SQLite（``data_sync_tasks`` 表），进程重启后可恢复：
每个阶段记录已完成区间，重跑只补缺口。
"""

import datetime
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from quantide.data.models.base import Entity

#: 同步阶段（按顺序执行）
SYNC_STAGES: tuple[str, ...] = (
    "calendar",  # 交易日历
    "stock_list",  # 证券主数据
    "daily_bars",  # 个股日线（复权/ST/涨跌停合并）
    "daily_basic",  # 市值/换手
    "index_bars",  # 指数日线
    "index_weight",  # 指数成分（PIT）
    "minute_bars",  # 30 分钟线（baostock 历史 + 腾讯增量）
)

#: 任务状态
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


@dataclass
class DataSyncTask(Entity):
    """一次数据同步任务。

    表：``data_sync_tasks``
    """

    __table_name__ = "data_sync_tasks"
    __pk__ = "task_id"
    __indexes__ = (["status"], False)

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    """任务 ID"""

    status: str = STATUS_PENDING
    """pending / running / done / failed / cancelled"""

    stages: str = "[]"
    """已完成阶段列表（JSON）"""

    params: str = "{}"
    """任务参数（JSON）：start_date/end_date/index_codes 等"""

    progress: int = 0
    """进度百分比（0-100）"""
    # 注：Entity.to_db_schema 按注解推断列类型，int 会落为 INTEGER 列。

    message: str = ""
    """当前阶段说明"""

    error: str = ""
    """错误信息"""

    created_at: datetime.datetime | None = field(default_factory=datetime.datetime.now)
    started_at: datetime.datetime | None = None
    finished_at: datetime.datetime | None = None

    @staticmethod
    def new_task_id() -> str:
        """生成任务 ID。"""
        return uuid.uuid4().hex

    def to_params(self) -> dict[str, Any]:
        """解析参数字段。"""
        try:
            data = json.loads(self.params or "{}")
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def stage_list(self) -> list[str]:
        """已完成阶段列表。"""
        try:
            data = json.loads(self.stages or "[]")
        except (TypeError, ValueError):
            return []
        return [str(x) for x in data] if isinstance(data, list) else []
