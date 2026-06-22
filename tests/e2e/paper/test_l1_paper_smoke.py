"""L1 paper E2E smoke (P3 Step 2-D 2/3).

按 P3 推进计划 + test-plan §6.4.6 边界铁律:
- 用 VirtualClock + make_paper_runtime (公共 support)
- 不 mock.patch 内部符号, 不调私有方法
- 本 smoke 验证公共 support 装配 + VirtualClock 推进; 完整 paper E2E 跑策略待 PR2 暴露 PaperBroker 公开 on_quote/on_limit API 后推进.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from quantide.data.models.calendar import calendar as calendar_model
from quantide.data.models.daily_bars import daily_bars
from quantide.data.models.limit_price import limit_price
from quantide.data.sqlite import db

from tests.e2e.support.runtime_factory import make_paper_runtime
from tests.e2e.support.virtual_clock import VirtualClock

ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets"
TEST_DATE = datetime.date(2024, 6, 3)


@pytest.mark.e2e
@pytest.mark.e2e_paper
def test_l1_paper_smoke_virtual_clock_advances():
    db.init(":memory:")
    calendar_model.load(ASSETS_ROOT / "baseline_calendar.parquet")
    daily_bars.load(ASSETS_ROOT / "2024_bars_ext_cols.parquet")
    limit_price.load(ASSETS_ROOT / "2024_limit_price.parquet")

    t0 = datetime.datetime.combine(TEST_DATE, datetime.time(9, 30))
    clock = VirtualClock(t0=t0)
    runtime = make_paper_runtime(virtual_clock=clock, mode="paper")

    assert runtime.clock is clock
    assert runtime.mode == "paper"
    assert runtime.clock.now() == t0

    t1 = datetime.datetime.combine(TEST_DATE, datetime.time(15, 0))
    clock.advance_to(t1)
    assert runtime.clock.now() == t1

    with pytest.raises(ValueError, match="is before current"):
        clock.advance_to(t0)

    clock.advance(seconds=-1800)
    assert runtime.clock.now() == t1 - datetime.timedelta(seconds=1800)


@pytest.mark.e2e
@pytest.mark.e2e_paper
def test_l1_paper_smoke_calendar_frames_loadable():
    """验证 calendar fixture 加载后, 可推进到下一帧 (test-plan §6.4.2 '回放行情源' 依赖)."""
    db.init(":memory:")
    calendar_model.load(ASSETS_ROOT / "baseline_calendar.parquet")

    clock = VirtualClock(t0=datetime.datetime(2024, 6, 3, 9, 30))
    from quantide.core.enums import FrameType

    next_frame = clock.advance_to_next_frame(FrameType.DAY)
    assert next_frame > datetime.datetime(2024, 6, 3, 9, 30)
    assert clock.now() == next_frame
