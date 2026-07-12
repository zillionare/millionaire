"""FR-015 SecurityListSDK 完整 4 接口契约 + FR-020 EnumerationResult 完整 test.

按 spec §FR-015 / §FR-020:
- FR-015 4 接口: stocks_listed(date, exclude_st) / is_st(asset, date) / days_since_ipo(asset, date) / get_name(asset)
- FR-020 EnumerationResult: 含 strategies + diagnostics (SkippedEntry + SkippedReason)
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from quantide.core.sdk_metadata import Security, SecurityListSDK
from quantide.core.strategy_discovery import (
    EnumerationResult,
    SkippedEntry,
    SkippedReason,
    StrategyDiscovery,
    StrategyMetadata,
)


AC_DATE = datetime.date(2024, 6, 1)


# ===== FR-015 4 接口契约 =====

def test_fr_015_stocks_listed_excludes_not_yet_listed():
    """AC-FR-015-01: stocks_listed 返回指定日期已上市证券 (排除未上市)."""
    sdk = SecurityListSDK()
    sdk.register(Security(symbol="A", name="Listed 2020", list_date=datetime.date(2020, 1, 1)))
    sdk.register(Security(symbol="B", name="Listed 2025", list_date=datetime.date(2025, 1, 1)))
    listed = sdk.stocks_listed(AC_DATE)
    assert listed == ["A"], f"expected only A (listed before 2024-06-01), got {listed}"


def test_fr_015_stocks_listed_excludes_delisted():
    """AC-FR-015-01: 已退市证券不应在 stocks_listed 中."""
    sdk = SecurityListSDK()
    sdk.register(Security(
        symbol="X", name="Delisted",
        list_date=datetime.date(2010, 1, 1),
        delist_date=datetime.date(2020, 1, 1),
    ))
    sdk.register(Security(symbol="Y", name="Active", list_date=datetime.date(2010, 1, 1)))
    listed = sdk.stocks_listed(AC_DATE)
    assert "X" not in listed
    assert "Y" in listed


def test_fr_015_stocks_listed_exclude_st_default_true():
    """AC-FR-015-01: exclude_st=True 默认排除 ST."""
    sdk = SecurityListSDK()
    sdk.register(Security(symbol="A", name="Normal", is_st=False))
    sdk.register(Security(symbol="B", name="ST Test", is_st=True))
    listed = sdk.stocks_listed(AC_DATE)
    assert "A" in listed
    assert "B" not in listed


def test_fr_015_stocks_listed_exclude_st_false_includes_st():
    """AC-FR-015-01: exclude_st=False 包含 ST."""
    sdk = SecurityListSDK()
    sdk.register(Security(symbol="A", name="Normal", is_st=False))
    sdk.register(Security(symbol="B", name="ST Test", is_st=True))
    listed = sdk.stocks_listed(AC_DATE, exclude_st=False)
    assert "A" in listed
    assert "B" in listed


def test_fr_015_stocks_listed_sorted():
    """AC-FR-015-01: 返回按代码排序 (确定性)."""
    sdk = SecurityListSDK()
    sdk.register(Security(symbol="Z", name="Z"))
    sdk.register(Security(symbol="A", name="A"))
    sdk.register(Security(symbol="M", name="M"))
    listed = sdk.stocks_listed(AC_DATE)
    assert listed == ["A", "M", "Z"]


def test_fr_015_is_st_with_date():
    """AC-FR-015-02: is_st(asset, date) 返回该日期是否 ST."""
    sdk = SecurityListSDK()
    sdk.register(Security(symbol="A", name="X", is_st=True))
    assert sdk.is_st("A", AC_DATE) is True
    assert sdk.is_st("NotExist", AC_DATE) is False


def test_fr_015_days_since_ipo_positive():
    """AC-FR-015-02: days_since_ipo 返回上市天数 (正数)."""
    sdk = SecurityListSDK()
    sdk.register(Security(symbol="A", name="X", list_date=datetime.date(2020, 1, 1)))
    days = sdk.days_since_ipo("A", AC_DATE)
    assert days == (AC_DATE - datetime.date(2020, 1, 1)).days
    assert days == 1613  # 2020-01-01 → 2024-06-01


def test_fr_015_days_since_ipo_before_listing_returns_zero():
    """AC-FR-015-02: 上市前返回 0."""
    sdk = SecurityListSDK()
    sdk.register(Security(symbol="A", name="X", list_date=datetime.date(2030, 1, 1)))
    assert sdk.days_since_ipo("A", AC_DATE) == 0


def test_fr_015_days_since_ipo_no_list_date_returns_zero():
    """AC-FR-015-02: 无 list_date 返回 0."""
    sdk = SecurityListSDK()
    sdk.register(Security(symbol="A", name="X"))
    assert sdk.days_since_ipo("A", AC_DATE) == 0


def test_fr_015_get_name_returns_security_name():
    """AC-FR-015-03: get_name 返回证券名称."""
    sdk = SecurityListSDK()
    sdk.register(Security(symbol="A", name="平安银行"))
    assert sdk.get_name("A") == "平安银行"


def test_fr_015_get_name_unknown_raises_value_error():
    """AC-FR-015-03: 未知证券 raise ValueError."""
    sdk = SecurityListSDK()
    with pytest.raises(ValueError):
        sdk.get_name("NotExist")


# ===== FR-020 EnumerationResult 模式 =====

def test_fr_020_enumeration_result_dataclass():
    """AC-FR-020-15: EnumerationResult 是 dataclass 含 strategies + diagnostics."""
    assert hasattr(EnumerationResult, "__dataclass_fields__")
    assert "strategies" in EnumerationResult.__dataclass_fields__
    assert "diagnostics" in EnumerationResult.__dataclass_fields__


def test_fr_020_skipped_reason_enum_values():
    """AC-FR-020-15: SkippedReason 枚举 6 个值."""
    expected = {"NotAStrategy", "InvalidConfig", "SyntaxError", "ImportError", "PermissionDenied", "BuiltinOverridden"}
    actual = {r.name for r in SkippedReason}
    assert actual == expected


def test_fr_020_skipped_entry_dataclass():
    """AC-FR-020-15: SkippedEntry 含 path + class_name + reason + detail."""
    e = SkippedEntry(path="/x.py", class_name="A", reason=SkippedReason.SyntaxError, detail="bad")
    assert e.path == "/x.py"
    assert e.class_name == "A"
    assert e.reason == SkippedReason.SyntaxError
    assert e.detail == "bad"


def test_fr_020_diagnose_non_strategy_class(tmp_path):
    """AC-FR-020-15: 不继承 BaseStrategy/RiskStrategy 的类记录到 diagnostics (NotAStrategy)."""
    (tmp_path / "junk.py").write_text(
        "class NotAStrategy:\n    pass\n"
    )
    result = StrategyDiscovery.discover(tmp_path)
    assert result.strategies == []
    assert any(d.reason == SkippedReason.NotAStrategy and d.class_name == "NotAStrategy" for d in result.diagnostics)


def test_fr_020_diagnose_syntax_error(tmp_path):
    """AC-FR-020-15: SyntaxError 记录到 diagnostics (不抛异常, 整体不阻塞)."""
    (tmp_path / "broken.py").write_text("def bad(:\n  pass\n")
    (tmp_path / "ok.py").write_text(
        "from quantide.core.strategy import BaseStrategy\n"
        "class OKStrategy(BaseStrategy):\n    pass\n"
    )
    result = StrategyDiscovery.discover(tmp_path)
    assert any(d.reason == SkippedReason.SyntaxError for d in result.diagnostics)
    assert any(s.strategy_id.endswith("OKStrategy") for s in result.strategies)


def test_fr_020_diagnose_import_error(tmp_path):
    """AC-FR-020-15: ImportError 记录到 diagnostics (SyntaxError 不 catch, ImportError catch)."""
    (tmp_path / "noimport.py").write_text(
        "import some_module_that_does_not_exist_xyz\n"
    )
    result = StrategyDiscovery.discover(tmp_path)
    assert any(d.reason == SkippedReason.ImportError for d in result.diagnostics)


def test_fr_020_diagnose_invalid_config_default(tmp_path):
    """AC-FR-020-15: default_config() 返回非 dict 记录到 diagnostics (InvalidConfig)."""
    (tmp_path / "badconfig.py").write_text(
        "from quantide.core.strategy import BaseStrategy\n"
        "class BadConfig(BaseStrategy):\n"
        "    @staticmethod\n"
        "    def default_config():\n"
        "        return 'not a dict'\n"
    )
    result = StrategyDiscovery.discover(tmp_path)
    assert any(d.reason == SkippedReason.InvalidConfig and d.class_name == "BadConfig" for d in result.diagnostics)


def test_fr_020_nonexistent_dir_returns_permission_denied_diagnostic(tmp_path):
    """AC-FR-020-15: 目录不存在返回 diagnostics PermissionDenied."""
    nonexistent = tmp_path / "nonexistent"
    result = StrategyDiscovery.discover(nonexistent)
    assert result.strategies == []
    assert any(d.reason == SkippedReason.PermissionDenied for d in result.diagnostics)


def test_fr_020_enumeration_result_iterable():
    """AC-FR-020-15: EnumerationResult 可迭代, iter() 返回 strategies."""
    from quantide.core.strategy import BaseStrategy

    class S1(BaseStrategy):
        pass

    sdk_results = [StrategyMetadata(
        strategy_id="S1", name="S1", description="",
        strategy_type="independent", module="x", is_builtin=False, default_config={},
    )]
    r = EnumerationResult(strategies=sdk_results, diagnostics=[])
    assert list(r) == sdk_results
    assert len(r) == 1
