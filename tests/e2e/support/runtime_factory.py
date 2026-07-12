"""测试用 RuntimeContext 工厂.

封装 L1 paper E2E 装配: 把 VirtualClock 注入, 跳过 DB 加载 (用 in-memory BrokerRegistry).
"""

from quantide.core.runtime.modes import RuntimeBootstrap
from quantide.core.runtime.modes import RuntimeContext
from .virtual_clock import DEFAULT_VIRTUAL_T0
from .virtual_clock import VirtualClock


def make_paper_runtime(
    virtual_clock: VirtualClock | None = None,
    mode: str = "paper",
) -> RuntimeContext:
    """构造一个 paper (L1) 测试运行时.

    Args:
        virtual_clock: 可选, 默认新建 VirtualClock(t0=DEFAULT_VIRTUAL_T0).
        mode: 模式, paper / live / backtest.

    Returns:
        RuntimeContext with virtual clock injected.
    """
    clock = virtual_clock or VirtualClock(t0=DEFAULT_VIRTUAL_T0)
    return RuntimeBootstrap(mode=mode, clock=clock).bootstrap()
