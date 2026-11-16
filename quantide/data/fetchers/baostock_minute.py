"""BaoStock 分钟线数据源适配器.

**BaoStock 使用约束（发行版必须遵守）**：

* 每日 API 请求不能超过 5 万次，超限进入黑名单；
* **不能并发连接**（单 socket，串行访问）；
* 本自然年度初次被黑名单会冻结 6 小时；本年多次被限，冻结时长 = 累计次数 × 6 小时；
* 解除后需等待约 5 分钟才可继续使用。

因此本适配器：

* **严格单线程串行**访问（内部锁 + 单会话）；
* 维护**每日请求预算**（默认 45000，留 10% 余量），超预算即停止并报错；
* 识别黑名单/限频错误（错误信息含"黑名单"/"限制"/"频率"），**立即停止**并把
  ``blacklisted_until`` 标记为 6 小时后，避免继续撞限。

分钟线历史实测边界：30 分钟线自 2020-01-02 起可用（日线可回溯到 2005）。
"""

from __future__ import annotations

import datetime
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager

import pandas as pd
from filelock import FileLock

from quantide.config.paths import get_app_config_dir
from quantide.data.fetchers.baostock_budget import BaostockBudget
from quantide.data.fetchers.baostock_budget import BaostockThrottledError as BaostockThrottledError
from quantide.data.fetchers.capabilities import require_source_asset

#: 单次请求的默认重试次数（网络抖动）
DEFAULT_RETRIES = 2
#: 每日请求预算（硬上限 5 万，留 10% 余量）
DEFAULT_DAILY_BUDGET = 45000
#: 识别为黑名单/限频的错误关键词
BLOCKED_KEYWORDS = ("黑名单", "限制", "频率超限", "冻结")


_SESSION_LOCK = threading.RLock()


class BaostockMinuteFetcher:
    """BaoStock 分钟线抓取器（串行 + 预算受限）。

    仅在需要分钟级历史时使用；日线请用 Tushare。
    """

    def __init__(
        self,
        daily_budget: int = DEFAULT_DAILY_BUDGET,
        min_history_date: datetime.date = datetime.date(2020, 1, 1),
    ) -> None:
        """初始化抓取器。

        Args:
            daily_budget: 每日 API 请求预算。
            min_history_date: 分钟线可用的最早日期（早于此日期无数据）。
        """
        self._daily_budget = int(daily_budget)
        self._min_history_date = min_history_date
        self._lock = _SESSION_LOCK
        self._logged_in = False
        self._budget = BaostockBudget(get_app_config_dir() / "baostock-budget.json", daily_budget)

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------
    def _ensure_login(self) -> None:
        """确保已登录（BaoStock 单连接，登录失败会抛错）。"""
        if self._logged_in:
            return
        import baostock as bs

        lg = bs.login()
        if lg.error_code != "0":
            raise BaostockThrottledError(f"BaoStock 登录失败: {lg.error_msg}")
        self._logged_in = True

    def close(self) -> None:
        """登出会话。"""
        with self._lock:
            if not self._logged_in:
                return
            try:
                import baostock as bs

                bs.logout()
            except Exception:  # pragma: no cover - 登出失败忽略
                pass
            self._logged_in = False

    def __enter__(self) -> BaostockMinuteFetcher:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 预算与黑名单
    # ------------------------------------------------------------------
    @property
    def requests_today(self) -> int:
        """Read the shared count, including requests reserved by previous processes."""
        return int(self._budget.status().get("used", 0))

    @property
    def budget_remaining(self) -> int:
        return max(0, self._budget.limit - self.requests_today)

    def _check_budget(self) -> None:
        self._budget.check()

    def _consume(self) -> None:
        self._budget.consume()

    def _handle_error(self, message: str) -> None:
        if self._is_blocking(message):
            until = self._budget.freeze()
            raise BaostockThrottledError(f"BaoStock 黑名单冻结/冷却期至 {until}: {message}")
        raise BaostockThrottledError(f"BaoStock 请求失败: {message}")

    def _retry_error(self, message: str, attempt: int) -> None:
        if self._is_blocking(message) or attempt >= DEFAULT_RETRIES:
            self._handle_error(message)
        time.sleep(attempt + 1)

    @contextmanager
    def _session(self) -> Iterator[None]:
        # BaoStock uses a module-global socket. Lock login, query iteration and logout
        # together across all fetchers, and serialize other local processes as well.
        with self._lock, FileLock(str(self._budget.path) + ".session.lock", timeout=60):
            self._check_budget()
            try:
                self._ensure_login()
                yield
            finally:
                self.close()

    # ------------------------------------------------------------------
    # 抓取
    # ------------------------------------------------------------------
    @staticmethod
    def _to_baostock_code(asset: str) -> str:
        """把统一代码转成 BaoStock 格式（sh.600000 / sz.000001）。"""
        code = asset.strip().upper()
        if "." in code:
            require_source_asset("baostock", code)
            number, market = code.split(".", 1)
            return f"{market.lower()}.{number}"
        if code.startswith(("5", "6", "9", "688", "11")):
            return f"sh.{code}"
        return f"sz.{code}"

    @staticmethod
    def _is_blocking(message: str) -> bool:
        """判断错误信息是否属于限频/黑名单。"""
        return any(keyword in message for keyword in BLOCKED_KEYWORDS)

    def fetch_minute_bars(
        self,
        asset: str,
        start_date: datetime.date,
        end_date: datetime.date,
        frequency: str = "30",
        adjust: str = "3",
    ) -> pd.DataFrame:
        """抓取单只股票的分钟线。

        Args:
            asset: 统一代码，如 ``600000.SH``。
            start_date: 起始日。
            end_date: 结束日。
            frequency: 分钟周期（``5`` / ``15`` / ``30`` / ``60``）。
            adjust: 复权标志（``1`` 后复权 / ``2`` 前复权 / ``3`` 不复权）。

        Returns:
            pd.DataFrame: 字段 date, time, asset, open, high, low, close, volume, amount。
        """
        self._to_baostock_code(asset)
        if start_date < self._min_history_date:
            start_date = self._min_history_date
        self._budget.path.parent.mkdir(parents=True, exist_ok=True)
        with self._session():
            import baostock as bs

            last_error = ""
            for attempt in range(DEFAULT_RETRIES + 1):
                self._consume()
                try:
                    rs = bs.query_history_k_data_plus(
                        self._to_baostock_code(asset),
                        "date,time,code,open,high,low,close,volume,amount",
                        start_date=start_date.isoformat(),
                        end_date=end_date.isoformat(),
                        frequency=str(frequency),
                        adjustflag=str(adjust),
                    )
                except Exception as exc:
                    last_error = str(exc)
                    self._retry_error(last_error, attempt)
                    continue

                if rs.error_code != "0":
                    last_error = rs.error_msg
                    self._retry_error(last_error, attempt)
                    continue

                rows: list[list[str]] = []
                while rs.next():
                    rows.append(rs.get_row_data())
                if not rows:
                    return pd.DataFrame()
                frame = pd.DataFrame(rows, columns=rs.fields)
                return self._normalize(frame, asset)

            raise BaostockThrottledError(f"BaoStock 抓取失败: {last_error}")

    def fetch_trading_status(
        self, asset: str, start: datetime.date, end: datetime.date
    ) -> pd.DataFrame:
        """Read explicit suspended-session flags to distinguish absence from source gaps."""
        code = self._to_baostock_code(asset)
        self._budget.path.parent.mkdir(parents=True, exist_ok=True)
        with self._session():
            import baostock as bs

            self._consume()
            result = bs.query_history_k_data_plus(
                code,
                "date,code,tradestatus",
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                frequency="d",
                adjustflag="3",
            )
            if result.error_code != "0":
                self._handle_error(result.error_msg)
            rows = []
            while result.next():
                rows.append(result.get_row_data())
            frame = pd.DataFrame(rows, columns=result.fields)
            frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.date
            return frame

    def fetch_many(
        self,
        assets: Iterable[str],
        start_date: datetime.date,
        end_date: datetime.date,
        frequency: str = "30",
        adjust: str = "3",
        progress: Callable[[int, int], None] | None = None,
    ) -> pd.DataFrame:
        """串行抓取多只股票的分钟线（受每日预算限制）。

        Args:
            assets: 统一代码列表。
            start_date: 起始日。
            end_date: 结束日。
            frequency: 分钟周期。
            adjust: 复权标志。
            progress: 进度回调 ``(done, total)``。

        Returns:
            pd.DataFrame: 合并后的分钟线。
        """
        assets = list(assets)
        frames: list[pd.DataFrame] = []
        for index, asset in enumerate(assets, start=1):
            frame = self.fetch_minute_bars(
                asset, start_date, end_date, frequency=frequency, adjust=adjust
            )
            if not frame.empty:
                frames.append(frame)
            if progress is not None:
                progress(index, len(assets))
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def _normalize(frame: pd.DataFrame, asset: str) -> pd.DataFrame:
        """把 BaoStock 原始表转成统一字段。"""
        out = frame.rename(
            columns={
                "code": "asset",
                "vol": "volume",
            }
        )
        if "asset" in out.columns:
            out["asset"] = asset
        for col in ("open", "high", "low", "close", "volume", "amount"):
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        if "time" in out.columns:
            out["dt"] = pd.to_datetime(
                out["time"].astype(str), format="%Y%m%d%H%M%S%f", errors="coerce"
            )
        if "date" in out.columns:
            out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
        return out
