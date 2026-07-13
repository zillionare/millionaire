"""v0.2-004-coverage-recovery C1.3f: quantide/core/utils.py (0% -> 80%+).

Per AD-05 RESOLVED RETAIN, the five date/time helpers in
``quantide/core/utils.py`` form a small bidirectional parse/format pair:

    str2date(s)   8-char  YYYYMMDD      -> datetime.date
    date2str(d)   datetime.date        -> 8-char  YYYYMMDD (zero-padded)
    str2time(s)   14-char YYYYMMDDHHMMSS -> datetime.datetime
    time2str(dt)  datetime.datetime    -> 14-char YYYYMMDDHHMMSS (zero-padded)
    time2minute(dt) datetime.datetime   -> 14-char YYYYMMDDHHMMSS with SS='00'

These tests cover happy paths, length validation, non-numeric rejection, and
the zero-padding edges for every low-order component.
"""

from __future__ import annotations

import datetime

import pytest

from quantide.core.utils import date2str, str2date, str2time, time2minute, time2str


def test_str2date_parses_eight_digit_yyyymmdd() -> None:
    """AC-FR0700-24: str2date parses a canonical 8-char YYYYMMDD string."""
    assert str2date("20240115") == datetime.date(2024, 1, 15)


def test_str2date_rejects_non_eight_length_inputs() -> None:
    """AC-FR0700-25: str2date raises ValueError for inputs whose length is not 8."""
    with pytest.raises(ValueError, match="8 length"):
        str2date("2024011")
    with pytest.raises(ValueError, match="8 length"):
        str2date("202401011")


def test_str2date_rejects_non_numeric_eight_char_input() -> None:
    """AC-FR0700-26: str2date raises ValueError for 8-char inputs with non-numeric chars."""
    with pytest.raises(ValueError):
        str2date("2024ab15")


def test_date2str_zero_pads_single_digit_month_and_day() -> None:
    """AC-FR0700-27: date2str zero-pads month and day to 2 digits."""
    assert date2str(datetime.date(2024, 1, 1)) == "20240101"


def test_date2str_preserves_double_digit_components() -> None:
    """AC-FR0700-28: date2str renders double-digit month/day without trimming."""
    assert date2str(datetime.date(2024, 12, 31)) == "20241231"


def test_str2time_parses_fourteen_digit_timestamp() -> None:
    """AC-FR0700-29: str2time parses a canonical 14-char YYYYMMDDHHMMSS string."""
    assert str2time("20240115120330") == datetime.datetime(2024, 1, 15, 12, 3, 30)


def test_str2time_rejects_non_fourteen_length_inputs() -> None:
    """AC-FR0700-30: str2time raises ValueError for inputs whose length is not 14."""
    with pytest.raises(ValueError, match="14 length"):
        str2time("2024011512033")
    with pytest.raises(ValueError, match="14 length"):
        str2time("202401151203301")


def test_time2str_zero_pads_all_low_order_components() -> None:
    """AC-FR0700-31: time2str zero-pads month/day/hour/minute/second to 2 digits."""
    assert time2str(datetime.datetime(2024, 1, 1, 0, 0, 0)) == "20240101000000"


def test_time2str_renders_full_digits_without_padding_loss() -> None:
    """AC-FR0700-32: time2str renders double-digit components verbatim."""
    assert (
        time2str(datetime.datetime(2024, 12, 31, 23, 59, 59))
        == "20241231235959"
    )


def test_time2minute_always_emits_seconds_as_zero_zero() -> None:
    """AC-FR0700-33: time2minute zeroes the seconds component regardless of input."""
    assert (
        time2minute(datetime.datetime(2024, 6, 15, 9, 5, 30))
        == "20240615090500"
    )


def test_time2minute_zero_pads_low_order_components() -> None:
    """AC-FR0700-34: time2minute zero-pads month/day/hour/minute to 2 digits."""
    assert time2minute(datetime.datetime(2024, 1, 1, 0, 0)) == "20240101000000"


def test_roundtrip_str2time_time2str_is_identity() -> None:
    """AC-FR0700-35: parse then format a datetime round-trips exactly."""
    original = "20241231235959"
    parsed = str2time(original)
    assert time2str(parsed) == original


def test_roundtrip_str2date_date2str_is_identity() -> None:
    """AC-FR0700-36: parse then format a date round-trips exactly."""
    original = "20240229"
    parsed = str2date(original)
    assert date2str(parsed) == original
