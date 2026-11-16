import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from quantide.app_factory import _initialize_app_database
from quantide.config.paths import set_app_config_dir_override
from quantide.core.message import msg_hub
from quantide.data.sqlite import db

with tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    set_app_config_dir_override(directory)
    path = directory / "quantide.db"
    with sqlite3.connect(path) as con:
        con.execute("create table sentinel(value text)")
        con.execute("insert into sentinel values ('healthy original')")
    original = db.init
    calls = 0

    def init_once_locked(path):
        global calls
        calls += 1
        if calls == 1:
            raise sqlite3.OperationalError("database is locked")
        return original(path)

    with patch.object(db, "init", side_effect=init_once_locked):
        _initialize_app_database()
    print(
        json.dumps(
            {
                "new_active_has_original_table": "sentinel" in db.table_names(),
                "healthy_database_renamed_as_corrupt": len(
                    list(directory.glob("quantide.corrupt.*.db"))
                )
                == 1,
            }
        )
    )
    db.close()
msg_hub.stop()
