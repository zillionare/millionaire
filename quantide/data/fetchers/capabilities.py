"""Published source capabilities; never silently substitute an unsupported market."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceCapability:
    """Data kinds and exchange coverage supplied by a built-in adapter."""

    exchanges: tuple[str, ...]
    datasets: tuple[str, ...]
    requires_opt_in: bool = False

    def supports(self, asset: str) -> bool:
        return asset.strip().upper().rsplit(".", 1)[-1] in self.exchanges


SOURCE_CAPABILITIES = {
    "tushare": SourceCapability(
        ("SH", "SZ", "BJ"),
        (
            "daily_bars",
            "calendar",
            "stock_list",
            "adjust_factor",
            "st_info",
            "limit_price",
            "daily_basic",
            "index_bars",
            "index_weights",
        ),
    ),
    "baostock": SourceCapability(
        ("SH", "SZ"),
        (
            "daily_bars",
            "calendar",
            "stock_list",
            "adjust_factor",
            "st_info",
            "minute_5_15_30_60",
        ),
    ),
    "tencent_demo": SourceCapability(("SH", "SZ", "BJ"), ("snapshot",), True),
}


def require_source_asset(source: str, asset: str) -> None:
    """Reject explicit unsupported requests before any network connection."""
    if not SOURCE_CAPABILITIES[source].supports(asset):
        raise ValueError(f"{source} does not support {asset}; use a data extension for this market")


def supports_dataset(source: str, dataset: str) -> bool:
    """Return whether an advertised source capability covers a sync dataset."""
    capability = SOURCE_CAPABILITIES.get(source)
    return bool(capability and dataset in capability.datasets)
