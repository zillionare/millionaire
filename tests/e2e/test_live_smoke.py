"""L3 live-smoke scaffold for the Windows + QMT gate."""

from __future__ import annotations

import os

import pytest


@pytest.mark.e2e
@pytest.mark.e2e_live_smoke
@pytest.mark.xfail(
    reason="Requires Windows + QMT real broker host. Keeper will run this in the live environment.",
    strict=False,
)
def test_live_smoke_contract_for_real_broker_path() -> None:
    """AC-FR0460-04 AC-FR0340-06 AC-FR0420-01: 真机环境需具备 wizard→gateway→投策略→仿真→实盘 的最小运行前提."""
    assert os.name == "nt"
    assert os.getenv("SHIELD_QMT_GATEWAY_HOST")
    assert os.getenv("SHIELD_QMT_GATEWAY_PORT")
