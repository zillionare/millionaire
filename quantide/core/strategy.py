import datetime
from typing import Any

import polars as pl
from loguru import logger

from quantide.core.enums import FrameType
from quantide.service.base_broker import Broker


class BaseStrategy:
    """策略基类"""

    def __init__(self, broker: Broker, config: dict[str, Any]):
        self.broker = broker
        self.config = config
        logger_kwargs = {"strategy": self.__class__.__name__}
        portfolio_id = getattr(broker, "portfolio_id", "")
        if portfolio_id:
            logger_kwargs["portfolio_id"] = portfolio_id
        self.logger = logger.bind(**logger_kwargs)
        self.interval: str = "1d"  # Default, set by Runner
        self._current_time: datetime.datetime | None = None

    def _render_log_message(self, msg: str, *args: Any, **kwargs: Any) -> str:
        """渲染日志文本，便于同步写入回测日志。"""
        if not args and not kwargs:
            return msg
        try:
            return msg.format(*args, **kwargs)
        except Exception:
            return msg


    async def init(self):
        """策略初始化，在实例化后立即调用"""
        pass

    async def on_start(self):
        """回测/实盘开始前调用"""
        pass

    async def on_stop(self):
        """回测/实盘结束后调用"""
        pass

    async def on_day_open(self, tm: datetime.datetime):
        """每日开盘前调用"""
        pass

    async def on_day_close(self, tm: datetime.datetime):
        """每日收盘后调用"""
        pass

    @staticmethod
    def default_config() -> dict[str, Any]:
        """策略 config 默认值。子类覆盖以声明自己的配置项。

        部署到 paper/live 时, UI 模态框按 (key, default, custom) 三列展示,
        custom 列默认等于回测时实际值, 用户可编辑覆盖。
        """
        return {}

    def get_history(
        self,
        asset: str,
        count: int,
        end_dt: datetime.datetime | None = None,
        frame_type: str = "1d",
        include_forming_bar: bool = True,
    ) -> pl.DataFrame:
        """获取历史数据。

        Args:
            asset: 资产代码
            count: 数量
            end_dt: 截止时间 (包含)，默认为当前回测/实盘时间
            frame_type: 周期
            include_forming_bar: 是否合并今日 forming bar（默认 True，
                Issue #20）。live/paper 模式下默认会拿到今日 forming bar；
                backtest 模式下回放历史 tick 也会得到对应时刻的 forming bar。

        Returns:
            pl.DataFrame: 历史数据（含或不含今日 forming bar）。
        """
        return self.broker.get_history(
            asset, count, end_dt, frame_type, include_forming_bar=include_forming_bar
        )

    def log(
        self,
        msg: str,
        *args,
        tm: datetime.datetime | datetime.date | None = None,
        level: str = "INFO",
        **kwargs,
    ):
        """日志辅助方法

        用户可以通过 tm 参数显式指定日志时间。
        如果 tm 为 None，则尝试使用当前的仿真时间。

        Args:
            msg: 日志内容
            tm: 指定时间
            level: 日志级别
        """
        # 1. 优先使用显式传入的时间
        log_time = tm

        # 2. 其次使用 runner 维护的当前时间
        if log_time is None:
            log_time = self._current_time

        # 3. 构造 patcher
        # 注意：这里我们为每条日志临时创建一个 patcher，这在极高频日志下可能有性能损耗，
        # 但考虑到日志量通常可控，且为了正确显示时间，这是必要的。
        rendered_message = self._render_log_message(msg, *args, **kwargs)
        if log_time:
            def _temp_patcher(record):
                record["time"] = log_time

            self.logger.patch(_temp_patcher).log(level, msg, *args, **kwargs)
        else:
            # 如果都没有时间，则使用系统时间（直接打印）
            self.logger.log(level, msg, *args, **kwargs)

        write_backtest_log = getattr(self.broker, "write_backtest_log", None)
        if callable(write_backtest_log):
            write_backtest_log(
                level=level,
                source="strategy",
                message=rendered_message,
                dt=log_time,
            )

    def record(
        self,
        key: str,
        value: float,
        dt: datetime.datetime | None = None,
        extra: dict | None = None,
    ):
        """记录策略指标/信号

        用于记录策略运行过程中的关键变量，便于后续分析。

        Args:
            key: 指标名称
            value: 指标值
            dt: 时间（可选），若不填则使用当前仿真时间
            extra: 额外信息（字典）
        """
        if dt is None:
            dt = self._current_time

        self.broker.record(key, value, dt, extra)
