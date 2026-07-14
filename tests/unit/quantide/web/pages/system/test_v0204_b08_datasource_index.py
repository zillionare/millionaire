"""B08-datasource-2: Tests for quantide/web/pages/system/datasource.py index."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quantide.web.pages.system.datasource import _get_data_status, _get_sync_history, index


@pytest.mark.asyncio
async def test_index_calls_render():
    """index(req) renders successfully."""
    req = MagicMock()
    resp = await index(req)
    assert resp is not None


@pytest.mark.asyncio
async def test_index_with_mocked_data_status():
    """index renders even when db state is unknown."""
    with patch("quantide.web.pages.system.datasource.db") as mock_db:
        # Default case: tables exist but are empty.
        mock_db.table_names.return_value = ["app_state", "sync_history"]
        resp = await index(MagicMock())
    assert resp is not None


def test_get_data_status_with_empty_db_state():
    """_get_data_status returns dict structure even if db raises."""
    with patch("quantide.web.pages.system.datasource.db") as mock_db:
        mock_db.table_names.side_effect = Exception("boom")
        status = _get_data_status()
    assert isinstance(status, dict)


def test_get_sync_history_returns_list():
    """_get_sync_history returns a list (possibly empty)."""
    history = _get_sync_history()
    assert isinstance(history, list)
