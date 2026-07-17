"""Importable strategy fixture for spawned GridSearch worker tests."""

import datetime

from quantide.core.strategy import BaseStrategy


class GridSearchRecordingStrategy(BaseStrategy):
    """Record the grid-search ``param1`` value from a spawned worker process."""

    async def init(self) -> None:
        """Record the configured parameter in the worker backtest log.

        Inputs:
            None; reads ``param1`` from this strategy's configuration.

        Returns:
            None.

        Raises:
            Propagates errors from the broker log-recording boundary.

        Side Effects:
            Writes a ``param1`` strategy-log entry to the worker database.
        """
        self.record(
            "param1",
            float(self.config.get("param1", 0)),
            self._current_time or datetime.datetime.now(),
        )

    async def on_bar(
        self,
        tm: datetime.datetime,
    ) -> None:
        """Accept runner bar callbacks without placing orders.

        Inputs:
            tm is the bar time. The strategy pulls data through
            ``get_bars``/``get_history`` rather than receiving a quote.

        Returns:
            None.

        Raises:
            None.

        Side Effects:
            None.
        """
