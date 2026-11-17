"""Public monthly wind-tunnel inputs must retain their raw daily provenance."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from quantide.factors.plugins import clear_plugin_cache
from quantide.service.factor_wind_tunnel import load_wind_tunnel_frame, run_factor_wind_tunnel

_PERMUTATION = (4, 1, 9, 2, 12, 6, 7, 3, 10, 5, 11, 8)
_MONTH_ENDS = (
    dt.date(2024, 1, 31),
    dt.date(2024, 2, 29),
    dt.date(2024, 3, 29),
    dt.date(2024, 4, 30),
    dt.date(2024, 5, 31),
    dt.date(2024, 6, 28),
)
_EXPECTED_CORRELATION = 0.4195804195804196


def _daily_prices() -> pl.DataFrame:
    rows = []
    for month, last in enumerate(_MONTH_ENDS, start=1):
        first = dt.date(2024, month, 2)
        for index, adjusted_open in enumerate(_PERMUTATION, start=1):
            for is_last, day in ((False, first), (True, last)):
                rows.append(
                    {
                        "date": day,
                        "asset": f"{index:06d}.SZ",
                        "open": float(index),
                        "high": float(index),
                        "low": float(index),
                        "close": float(index),
                        "volume": 1000.0,
                        "amount": 10000.0,
                        "adjust": adjusted_open / index * ((20 - index) if is_last else 1),
                    }
                )
    return pl.DataFrame(rows).sort(["asset", "date"])


@pytest.fixture
def monthly_market(tmp_path, monkeypatch):
    from quantide.data.models.calendar import calendar
    from quantide.data.models.daily_bars import daily_bars

    for suffix, adjustment in (("hfq", "hfq"), ("raw", "raw")):
        factor_id = f"month_open_{suffix}"
        (tmp_path / f"{factor_id}.py").write_text(
            "from quantide.factors.plugins import FactorPlugin\n"
            f"FACTOR_PLUGIN = FactorPlugin(factor_id='{factor_id}', "
            f"display_name='{factor_id}', bar_interval='1M', "
            f"price_adjustment='{adjustment}', warmup_bars=0, required_columns=('open',), "
            "compute=lambda panel: panel['open'])\n",
            encoding="utf-8",
        )
    monkeypatch.setattr("quantide.config.settings.get_factor_dir", lambda: str(tmp_path))
    clear_plugin_cache()
    daily = _daily_prices()
    reads = []

    def read(start, end, *, assets=None, **_kwargs):
        start = start.date() if isinstance(start, dt.datetime) else start
        end = end.date() if isinstance(end, dt.datetime) else end
        reads.append((start, end))
        result = daily.filter(pl.col("date").is_between(start, end))
        return result.filter(pl.col("asset").is_in(assets)) if assets else result

    def next_session(day, _count):
        if day in _MONTH_ENDS:
            return dt.date(day.year, day.month + 1, 1)
        return day + dt.timedelta(days=1)

    monkeypatch.setattr(daily_bars, "get_bars_in_range", read)
    monkeypatch.setattr(calendar, "day_shift", next_session)
    yield daily, reads
    clear_plugin_cache()


@pytest.mark.parametrize(
    ("basis", "start"), [("hfq", dt.date(2024, 1, 15)), ("raw", dt.date(2024, 1, 2))]
)
def test_public_monthly_check_compares_bases_from_same_full_months(monthly_market, basis, start):
    """The fixed rank permutation is independent of month-end adjustment changes."""
    _, reads = monthly_market
    result = run_factor_wind_tunnel(
        f"month_open_{basis}", start=start, end=_MONTH_ENDS[-1], save=False
    )

    assert result.status == "PASS", [
        (c.check_id, c.status.value, c.message)
        for c in result.report.checks
        if c.status.value in {"FAIL", "INCONCLUSIVE"}
    ]
    peer = next(
        item
        for item in result.orthogonality.top_peers
        if item.peer_factor_id == ("month_open_raw" if basis == "hfq" else "month_open_hfq")
    )
    # Spearman = 1 - 6 * sum((permutation[i] - (i + 1))**2) / (12 * (12**2 - 1)).
    assert peer.mean_rank_corr == pytest.approx(_EXPECTED_CORRELATION, rel=0, abs=1e-12)
    assert peer.n_common_days == 6
    assert reads == [(dt.date(2024, 1, 1), _MONTH_ENDS[-1])]


def test_explicit_monthly_frame_does_not_borrow_unrelated_local_daily_data(monthly_market):
    """A supplied aggregate carries no proof that local daily data produced it."""
    _, reads = monthly_market
    frame = load_wind_tunnel_frame(
        dt.date(2024, 1, 2), _MONTH_ENDS[-1], interval="1M", price_adjustment="hfq"
    ).with_columns(pl.col("dt").cast(pl.Datetime("ms")))
    reads.clear()

    result = run_factor_wind_tunnel("month_open_hfq", frame=frame, save=False)

    assert result.status == "PASS", [
        (c.check_id, c.status.value, c.message)
        for c in result.report.checks
        if c.status.value in {"FAIL", "INCONCLUSIVE"}
    ]
    assert result.orthogonality.status == "INCONCLUSIVE"
    assert result.metadata["orthogonality_provenance"] == "raw_daily_unavailable"
    assert reads == []


@pytest.mark.parametrize(("basis", "use_path"), [("hfq", False), ("raw", True)])
def test_cli_monthly_check_retains_declared_interval_and_price_basis(
    monthly_market, monkeypatch, basis, use_path
):
    from quantide.factors.plugins import discover_factor_plugins
    from quantide.service import research_cli

    _, reads = monthly_market
    factor_id = f"month_open_{basis}"
    plugin = discover_factor_plugins().by_id(factor_id)
    assert plugin is not None
    monkeypatch.setattr(research_cli, "_bar_dates", lambda: list(_MONTH_ENDS))

    payload, code = research_cli.check_factor(
        plugin.source_path if use_path else factor_id,
        start=dt.date(2024, 1, 15),
        end=_MONTH_ENDS[-1],
    )

    assert code == 0, payload["diagnostics"]
    assert payload["data"]["metadata"]["price_adjustment"] == basis
    assert payload["data"]["metadata"]["orthogonality_provenance"] == "original_raw_daily"
    assert payload["data"]["orthogonality"]["max_abs_rank_corr"] == pytest.approx(
        _EXPECTED_CORRELATION, rel=0, abs=1e-12
    )
    assert reads == [(dt.date(2024, 1, 1), _MONTH_ENDS[-1])]


def test_ai_worker_monthly_check_preserves_raw_price_basis(monthly_market, tmp_path):
    from quantide.service.ai_factor_tools import _wind_tunnel_worker

    _, reads = monthly_market
    payload = _wind_tunnel_worker(
        {
            "factor_id": "month_open_raw",
            "factor_dir": str(tmp_path),
            "start": "2024-01-15",
            "end": "2024-06-28",
        }
    )

    assert payload["status"] == "PASS"
    assert payload["metadata"]["price_adjustment"] == "raw"
    assert payload["metadata"]["orthogonality_provenance"] == "original_raw_daily"
    assert payload["orthogonality"]["max_abs_rank_corr"] == pytest.approx(
        _EXPECTED_CORRELATION, rel=0, abs=1e-12
    )
    assert reads == [(dt.date(2024, 1, 1), _MONTH_ENDS[-1])]


def test_supplied_daily_source_must_reproduce_the_monthly_frame(monthly_market):
    from quantide.service.factor_wind_tunnel import load_wind_tunnel_inputs

    daily, reads = monthly_market
    loaded = load_wind_tunnel_inputs(dt.date(2024, 1, 2), _MONTH_ENDS[-1], interval="1M")
    reads.clear()
    unrelated = daily.with_columns(
        (pl.col(column) * 2).alias(column) for column in ("open", "high", "low", "close")
    )

    result = run_factor_wind_tunnel(
        "month_open_hfq", frame=loaded.frame, source_daily=unrelated, save=False
    )

    assert result.status == "PASS"
    assert result.orthogonality.status == "INCONCLUSIVE"
    assert result.metadata["orthogonality_provenance"] == "raw_daily_unavailable"
    assert reads == []
