import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import requests
import tushare as ts

token = os.environ.get("TUSHARE_TOKEN", "").strip()
if not token:
    raise SystemExit("TUSHARE_TOKEN is not set")
pro = ts.pro_api(token=token, timeout=6)
results = []
original_post = requests.post
for name, params in [
    (
        "trade_cal",
        {
            "exchange": "SSE",
            "start_date": "20240102",
            "end_date": "20240103",
            "fields": "exchange,cal_date,is_open,pretrade_date",
        },
    ),
    (
        "daily",
        {
            "ts_code": "000001.SZ",
            "start_date": "20240102",
            "end_date": "20240103",
            "fields": "ts_code,trade_date,open,high,low,close,vol,amount",
        },
    ),
]:
    observed = []

    def post(*args, observed=observed, **kwargs):
        response = original_post(*args, **kwargs)
        observed.append({"http_status": response.status_code})
        return response

    start = time.monotonic()
    row = {"endpoint": name, "token_source": "TUSHARE_TOKEN", "request_params": params}
    try:
        with patch("requests.post", side_effect=post):
            frame = getattr(pro, name)(**params)
        row.update(
            {
                "status": "data" if len(frame) else "empty",
                "rows": len(frame),
                "columns": list(frame.columns),
            }
        )
    except Exception as exc:
        row.update({"status": "error", "exception_type": type(exc).__name__})
    row.update({"elapsed_seconds": round(time.monotonic() - start, 2), "responses": observed})
    results.append(row)
    print(json.dumps(row, ensure_ascii=False), flush=True)
Path("/tmp/millionaire-ce-review-tushare-smoke.json").write_text(
    json.dumps(
        {"token_present": True, "sdk_version": ts.__version__, "results": results},
        ensure_ascii=False,
        indent=2,
    )
)
