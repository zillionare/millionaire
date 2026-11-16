import datetime
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from quantide.core.message import msg_hub
from quantide.data.fetchers.baostock_minute import BaostockMinuteFetcher, BaostockThrottledError
from quantide.data.models.sync_task import SYNC_STAGES
from quantide.data.sqlite import db
from quantide.service.data_sync import DataSyncService, SyncParams
from quantide.service.minute_bar_aggregator import minute_bar_aggregator

with tempfile.TemporaryDirectory() as tmp:
    db.init(Path(tmp) / "review.db")
    service = DataSyncService()
    params = SyncParams(
        datetime.date(2024, 1, 2), datetime.date(2024, 1, 3), minute_assets=["000001.SZ"]
    )
    task = service.create_task(params)
    service._update_task(task.task_id, stages=[s for s in SYNC_STAGES if s != "minute_bars"])
    store = MagicMock()
    store.last_dates.return_value = {}
    with (
        patch("quantide.data.get_minute_bars_store", return_value=store),
        patch("quantide.service.data_sync._minute_history_end", return_value=params.end_date),
        patch.object(
            BaostockMinuteFetcher,
            "fetch_minute_bars",
            side_effect=BaostockThrottledError("simulated blackout"),
        ),
        patch.object(minute_bar_aggregator, "clear_between") as clear,
    ):
        returned = service.run(task.task_id)
        final = service.get_task(task.task_id)
        print(
            json.dumps(
                {
                    "run_return": returned,
                    "task_status": final.status,
                    "task_error": final.error,
                    "writes": store.append_data.call_count,
                    "aggregator_clear_calls": clear.call_count,
                }
            )
        )
    db.close()
msg_hub.stop()
