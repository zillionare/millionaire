"""[AC-NFR1101-01] init_wizard page route handler exception/inner branches.

Targets uncovered lines in `quantide/web/pages/init_wizard.py`:
- `_format_date_zh` exception fallback (lines 113-114)
- `FormHint` text path (line 380)
- `_get_step_meta` dev-stub step 4 dict (line 430)
- `Step1_Welcome` dev-stub text (lines 567-568)
- `Step5_DataSetup` int-parse except (lines 938-939)
- `handle_step` step=2 save_runtime_config exception (lines 1363-1372)
- `handle_step` step=4 dev-stub runtime-None + save exception (lines 1401-1428)
- `handle_step` step=4 non-dev-stub port/server/api_key/test_connection branches (lines 1448-1507)
- `handle_step` step=5 dev-stub save exception (lines 1538-1546)
- `handle_step` step=5 non-dev-stub save exception (lines 1570-1578)
- `handle_download` dev-stub exception + non-dev-stub save exception (lines 1847-1882)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from quantide.web.pages import init_wizard as iw_mod
from quantide.web.pages.init_wizard import (
    FormHint,
    Step1_Welcome,
    Step5_DataSetup,
    _format_date_zh,
    _get_step_meta,
    get as init_get,
    handle_download,
    handle_step,
)


# ---------------------------------------------------------------------------
# _format_date_zh exception fallback (lines 113-114)
# ---------------------------------------------------------------------------


def test_format_date_zh_unparseable_string_returns_text():
    """[AC-NFR1101-01] Non-empty, non-Chinese, unparseable string -> returns text as-is."""
    out = _format_date_zh("not-a-date")
    assert out == "not-a-date"


def test_format_date_zh_partial_garbage_returns_text():
    """[AC-NFR1101-01] Another unparseable string falls into except branch."""
    out = _format_date_zh("2024/13/99")
    assert out == "2024/13/99"


# ---------------------------------------------------------------------------
# FormHint (line 380)
# ---------------------------------------------------------------------------


def test_form_hint_renders_paragraph():
    """[AC-NFR1101-01] FormHint returns a rendered node containing the hint text."""
    out = FormHint("a small hint")
    assert out is not None
    s = str(out)
    assert "a small hint" in s


# ---------------------------------------------------------------------------
# _get_step_meta dev-stub step 4 dict (line 430)
# ---------------------------------------------------------------------------


def test_get_step_meta_dev_stub_step4_returns_stub_dict():
    """[AC-NFR1101-01] When dev_stubs_enabled and step==4, returns stub-specific dict."""
    with patch.object(iw_mod, "dev_stubs_enabled", return_value=True):
        meta = _get_step_meta(4)
    assert meta["title"] == "开发 Stub 交易网关"
    assert "stub" in meta["description"] or "Stub" in meta["description"]


def test_get_step_meta_dev_stub_step5_returns_stub_dict():
    """[AC-NFR1101-01] When dev_stubs_enabled and step==5, returns stub-specific dict."""
    with patch.object(iw_mod, "dev_stubs_enabled", return_value=True):
        meta = _get_step_meta(5)
    assert "样本数据" in meta["title"]


# ---------------------------------------------------------------------------
# Step1_Welcome dev-stub text (lines 567-568)
# ---------------------------------------------------------------------------


def test_step1_welcome_dev_stub_text_branch():
    """[AC-NFR1101-01] When dev_stubs_enabled, Step1_Welcome uses stub-specific text."""
    with patch.object(iw_mod, "dev_stubs_enabled", return_value=True):
        out = Step1_Welcome()
    s = str(out)
    assert "开发 Stub" in s
    assert "样本数据" in s


# ---------------------------------------------------------------------------
# Step5_DataSetup int-parse except (lines 938-939)
# ---------------------------------------------------------------------------


def test_step5_data_setup_invalid_years_falls_back_to_one():
    """[AC-NFR1101-01] Non-numeric history_years triggers ValueError -> years=1 fallback."""
    with patch.object(iw_mod, "dev_stubs_enabled", return_value=False):
        # Provide history_years as non-numeric to hit the except branch at 938-939.
        state = {"history_years": "garbage"}
        out = Step5_DataSetup(state)
    assert out is not None


# ---------------------------------------------------------------------------
# handle_step step=2 save_runtime_config exception (lines 1363-1372)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_step_step2_save_runtime_config_exception():
    """[AC-NFR1101-01] save_runtime_config raises -> except branch renders error content."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step2_Runtime", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={
            "app_home": "/tmp/x",
            "app_host": "127.0.0.1",
            "app_port": 8130,
            "app_prefix": "/quantide",
        })
        mock_iw.get_state = MagicMock(return_value=fake_state)
        mock_iw.save_runtime_config = MagicMock(side_effect=Exception("save boom"))
        req = MagicMock()
        req.form = AsyncMock(return_value={"nav": "next", "_current_step": "2"})
        resp = await handle_step(req, step=2)
    assert resp == "err"
    mock_render.assert_called_once()
    # Confirm the error path was taken (not the success path which would call update_step).
    mock_iw.update_step.assert_not_called()


# ---------------------------------------------------------------------------
# handle_step step=4 dev-stub runtime None + save exception (lines 1401-1428)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_step_step4_dev_stub_runtime_none():
    """[AC-NFR1101-01] dev-stubs + runtime None -> error content rendered."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "dev_stubs_enabled", return_value=True), \
         patch.object(iw_mod, "ensure_dev_stubs_started", return_value=None), \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step4_Gateway", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={"k": "v"})
        mock_iw.get_state = MagicMock(return_value=fake_state)
        req = MagicMock()
        req.form = AsyncMock(return_value={"nav": "next", "_current_step": "4"})
        resp = await handle_step(req, step=4)
    assert resp == "err"
    mock_render.assert_called_once()


@pytest.mark.asyncio
async def test_handle_step_step4_dev_stub_save_gateway_exception():
    """[AC-NFR1101-01] dev-stubs + save_gateway_config raises -> except branch at 1419-1428."""
    fake_runtime = MagicMock()
    fake_runtime.gateway_server = "localhost"
    fake_runtime.gateway_port = 8000
    fake_runtime.gateway_prefix = "/"
    fake_runtime.gateway_api_key = "k"
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "dev_stubs_enabled", return_value=True), \
         patch.object(iw_mod, "ensure_dev_stubs_started", return_value=fake_runtime), \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step4_Gateway", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={"k": "v"})
        mock_iw.get_state = MagicMock(return_value=fake_state)
        mock_iw.save_gateway_config = MagicMock(side_effect=Exception("save gw boom"))
        req = MagicMock()
        req.form = AsyncMock(return_value={"nav": "next", "_current_step": "4"})
        resp = await handle_step(req, step=4)
    assert resp == "err"
    mock_render.assert_called_once()


# ---------------------------------------------------------------------------
# handle_step step=4 non-dev-stub: port parse error, server missing, api_key
# missing, test_gateway_connection fails, save raises (lines 1448-1507)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_step_step4_non_stub_port_parse_error():
    """[AC-NFR1101-01] Non-dev-stub + bad port -> ValueError -> error content (line 1448)."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "dev_stubs_enabled", return_value=False), \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step4_Gateway", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={
            "gateway_enabled": "on",
            "gateway_server": "localhost",
            "gateway_port": "not-a-port",
            "gateway_prefix": "/",
            "gateway_api_key": "k",
        })
        mock_iw.get_state = MagicMock(return_value=fake_state)
        req = MagicMock()
        req.form = AsyncMock(return_value={
            "nav": "next",
            "_current_step": "4",
            "gateway_enabled": "on",
            "gateway_server": "localhost",
            "gateway_port": "not-a-port",
            "gateway_prefix": "/",
            "gateway_api_key": "k",
        })
        resp = await handle_step(req, step=4)
    assert resp == "err"
    mock_render.assert_called_once()


@pytest.mark.asyncio
async def test_handle_step_step4_non_stub_enabled_no_server():
    """[AC-NFR1101-01] Enabled gateway without server -> error content (line 1457-1464)."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "dev_stubs_enabled", return_value=False), \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step4_Gateway", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={
            "gateway_enabled": "on",
            "gateway_server": "",
            "gateway_port": 8000,
            "gateway_prefix": "/",
            "gateway_api_key": "k",
        })
        mock_iw.get_state = MagicMock(return_value=fake_state)
        req = MagicMock()
        req.form = AsyncMock(return_value={
            "nav": "next",
            "_current_step": "4",
            "gateway_enabled": "on",
            "gateway_server": "   ",
            "gateway_port": "8000",
            "gateway_prefix": "/",
            "gateway_api_key": "k",
        })
        resp = await handle_step(req, step=4)
    assert resp == "err"
    mock_render.assert_called_once()


@pytest.mark.asyncio
async def test_handle_step_step4_non_stub_enabled_no_api_key():
    """[AC-NFR1101-01] Enabled gateway without api_key -> error content (line 1465-1472)."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "dev_stubs_enabled", return_value=False), \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step4_Gateway", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={
            "gateway_enabled": "on",
            "gateway_server": "localhost",
            "gateway_port": 8000,
            "gateway_prefix": "/",
            "gateway_api_key": "",
        })
        mock_iw.get_state = MagicMock(return_value=fake_state)
        req = MagicMock()
        req.form = AsyncMock(return_value={
            "nav": "next",
            "_current_step": "4",
            "gateway_enabled": "on",
            "gateway_server": "localhost",
            "gateway_port": "8000",
            "gateway_prefix": "/",
            "gateway_api_key": "",
        })
        resp = await handle_step(req, step=4)
    assert resp == "err"
    mock_render.assert_called_once()


@pytest.mark.asyncio
async def test_handle_step_step4_non_stub_test_connection_fails():
    """[AC-NFR1101-01] Enabled gateway, test_gateway_connection returns ok=False (line 1478-1490)."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "dev_stubs_enabled", return_value=False), \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step4_Gateway", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={
            "gateway_enabled": "on",
            "gateway_server": "localhost",
            "gateway_port": 8000,
            "gateway_prefix": "/",
            "gateway_api_key": "k",
        })
        mock_iw.get_state = MagicMock(return_value=fake_state)
        mock_iw.test_gateway_connection = MagicMock(return_value=(False, "conn refused"))
        req = MagicMock()
        req.form = AsyncMock(return_value={
            "nav": "next",
            "_current_step": "4",
            "gateway_enabled": "on",
            "gateway_server": "localhost",
            "gateway_port": "8000",
            "gateway_prefix": "/",
            "gateway_api_key": "k",
        })
        resp = await handle_step(req, step=4)
    assert resp == "err"
    mock_render.assert_called_once()
    mock_iw.save_gateway_config.assert_not_called()


@pytest.mark.asyncio
async def test_handle_step_step4_non_stub_save_gateway_exception():
    """[AC-NFR1101-01] Non-dev-stub + save_gateway_config raises (line 1500-1507)."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "dev_stubs_enabled", return_value=False), \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step4_Gateway", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={
            "gateway_enabled": "on",
            "gateway_server": "localhost",
            "gateway_port": 8000,
            "gateway_prefix": "/",
            "gateway_api_key": "k",
        })
        mock_iw.get_state = MagicMock(return_value=fake_state)
        mock_iw.test_gateway_connection = MagicMock(return_value=(True, "ok"))
        mock_iw.save_gateway_config = MagicMock(side_effect=Exception("save boom"))
        req = MagicMock()
        req.form = AsyncMock(return_value={
            "nav": "next",
            "_current_step": "4",
            "gateway_enabled": "on",
            "gateway_server": "localhost",
            "gateway_port": "8000",
            "gateway_prefix": "/",
            "gateway_api_key": "k",
        })
        resp = await handle_step(req, step=4)
    assert resp == "err"
    mock_render.assert_called_once()


# ---------------------------------------------------------------------------
# handle_step step=5 epoch parse ValueError (lines 1519-1527)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_step_step5_bad_epoch_raises_value_error():
    """[AC-NFR1101-01] Non-dev-stub + unparseable epoch -> ValueError -> error content (1519-1527)."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "dev_stubs_enabled", return_value=False), \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step5_DataSetup", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={
            "epoch": "not-a-date",
            "data_source": "tushare",
            "tushare_token": "tok",
            "history_years": 1,
        })
        mock_iw.get_state = MagicMock(return_value=fake_state)
        req = MagicMock()
        req.form = AsyncMock(return_value={
            "nav": "next",
            "_current_step": "5",
            "epoch": "not-a-date",
            "data_source": "tushare",
            "tushare_token": "tok",
            "history_years": "1",
        })
        resp = await handle_step(req, step=5)
    assert resp == "err"
    mock_render.assert_called_once()
    # save_data_init_config should not have been called because epoch parse failed.
    mock_iw.save_data_init_config.assert_not_called()


@pytest.mark.asyncio
async def test_handle_step_step5_bad_history_years_raises_value_error():
    """[AC-NFR1101-01] Non-dev-stub + non-numeric history_years -> ValueError at 1519."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "dev_stubs_enabled", return_value=False), \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step5_DataSetup", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={
            "epoch": "2020-01-01",
            "data_source": "tushare",
            "tushare_token": "tok",
            "history_years": "not-a-number",
        })
        mock_iw.get_state = MagicMock(return_value=fake_state)
        req = MagicMock()
        req.form = AsyncMock(return_value={
            "nav": "next",
            "_current_step": "5",
            "epoch": "2020-01-01",
            "data_source": "tushare",
            "tushare_token": "tok",
            "history_years": "not-a-number",
        })
        resp = await handle_step(req, step=5)
    assert resp == "err"
    mock_render.assert_called_once()


# ---------------------------------------------------------------------------
# handle_step step=5 dev-stub save exception (lines 1538-1546)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_step_step5_dev_stub_save_exception():
    """[AC-NFR1101-01] dev-stubs + save_data_init_config raises -> except at 1538-1546."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "dev_stubs_enabled", return_value=True), \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step5_DataSetup", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={
            "epoch": "2020-01-01",
            "data_source": "tushare",
            "tushare_token": "tok",
            "history_years": 1,
        })
        mock_iw.get_state = MagicMock(return_value=fake_state)
        mock_iw.save_data_init_config = MagicMock(side_effect=Exception("save boom"))
        req = MagicMock()
        req.form = AsyncMock(return_value={
            "nav": "next",
            "_current_step": "5",
            "epoch": "2020-01-01",
        })
        resp = await handle_step(req, step=5)
    assert resp == "err"
    mock_render.assert_called_once()


# ---------------------------------------------------------------------------
# handle_step step=5 non-dev-stub save exception (lines 1570-1578)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_step_step5_non_stub_save_exception():
    """[AC-NFR1101-01] Non-dev-stub + save_data_init_config raises -> except at 1570-1578."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "dev_stubs_enabled", return_value=False), \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step5_DataSetup", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={
            "epoch": "2020-01-01",
            "data_source": "tushare",
            "tushare_token": "tok",
            "history_years": 1,
        })
        mock_iw.get_state = MagicMock(return_value=fake_state)
        mock_iw.save_data_init_config = MagicMock(side_effect=Exception("save boom"))
        req = MagicMock()
        req.form = AsyncMock(return_value={
            "nav": "next",
            "_current_step": "5",
            "epoch": "2020-01-01",
            "data_source": "tushare",
            "tushare_token": "tok",
            "history_years": "1",
        })
        resp = await handle_step(req, step=5)
    assert resp == "err"
    mock_render.assert_called_once()


# ---------------------------------------------------------------------------
# handle_download dev-stub exception (lines 1847-1855) +
# non-dev-stub save exception (lines 1874-1882)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_download_dev_stub_save_exception():
    """[AC-NFR1101-01] dev-stubs + save_data_init_config raises -> except at 1847-1855."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "dev_stubs_enabled", return_value=True), \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step5_DataSetup", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={
            "epoch": "2020-01-01",
            "data_source": "tushare",
            "tushare_token": "tok",
            "history_years": 1,
        })
        mock_iw.get_state = MagicMock(return_value=fake_state)
        mock_iw.save_data_init_config = MagicMock(side_effect=Exception("save boom"))
        req = MagicMock()
        req.form = AsyncMock(return_value={
            "epoch": "2020-01-01",
        })
        resp = await handle_download(req)
    assert resp == "err"
    mock_render.assert_called_once()


@pytest.mark.asyncio
async def test_handle_download_non_stub_save_exception():
    """[AC-NFR1101-01] Non-dev-stub + save_data_init_config raises -> except at 1874-1882."""
    with patch.object(iw_mod, "init_wizard") as mock_iw, \
         patch.object(iw_mod, "dev_stubs_enabled", return_value=False), \
         patch.object(iw_mod, "_set_reconfigure_mode"), \
         patch.object(iw_mod, "_request_in_force_mode", return_value=False), \
         patch.object(iw_mod, "_render_wizard_main_content", return_value="err") as mock_render, \
         patch.object(iw_mod, "Step5_DataSetup", return_value="form"):
        fake_state = MagicMock()
        fake_state.to_dict = MagicMock(return_value={
            "epoch": "2020-01-01",
            "data_source": "tushare",
            "tushare_token": "tok",
            "history_years": 1,
        })
        mock_iw.get_state = MagicMock(return_value=fake_state)
        mock_iw.save_data_init_config = MagicMock(side_effect=Exception("save boom"))
        req = MagicMock()
        req.form = AsyncMock(return_value={
            "epoch": "2020-01-01",
            "data_source": "tushare",
            "tushare_token": "tok",
            "history_years": "1",
        })
        resp = await handle_download(req)
    assert resp == "err"
    mock_render.assert_called_once()
