"""B08-kline-api-final: Test endpoints too."""

from __future__ import annotations

import pytest

from quantide.web.apis.analysis.kline import get_sector_kline


@pytest.mark.asyncio
async def test_get_sector_kline_returns_410():
    from unittest.mock import MagicMock

    resp = await get_sector_kline(
        request=MagicMock(),
        sector_id="x",
        start=None,
        end=None,
        freq="day",
        ma=None,
    )
    assert resp.status_code == 410
