"""AC-4302: the legacy alpha-ledger page stays removed."""

from pathlib import Path


def test_alpha_ledger_page_removed() -> None:
    root = Path(__file__).parents[5]
    assert not (root / "quantide/web/pages/system/alpha_ledger.py").exists()
