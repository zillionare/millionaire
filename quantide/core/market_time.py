"""Exchange-local wall time, independent of the host operating system timezone."""

import datetime


def market_now() -> datetime.datetime:
    """Return naive exchange-local time, matching stored bars and vendor quote timestamps."""
    from quantide.config.settings import get_timezone

    return datetime.datetime.now(get_timezone()).replace(tzinfo=None)


def market_today() -> datetime.date:
    """Return the trading venue's current calendar date."""
    return market_now().date()
