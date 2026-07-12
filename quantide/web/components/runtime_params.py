"""FR-0020 运行时参数编辑.

定义运行时参数 (本金/滑点/印花税比率/佣金比率/单笔最低佣金) 的数据结构、
默认值与校验规则.

运行时参数 != 策略参数: 每次启动回测/仿真/实盘都允许独立设置, 不被回测结果锁定.
最近一次值缓存在 localStorage (NFR-0070), 不写入回测结果.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RuntimeParams:
    """运行时参数 (interfaces.md §4.1).

    Attributes:
        principal: 本金 (>0, 取上一次值).
        slippage_rate: 滑点比率 (0<=x<=0.1, 默认 0).
        stamp_tax_rate: 印花税比率 (0<=x<=0.01, 默认 0.001).
        commission_rate: 佣金比率 (0<=x<=0.01, 默认 0.0001).
        min_commission: 单笔最低佣金 (>=0, 默认 5).
    """

    principal: float | None
    slippage_rate: float = 0.0
    stamp_tax_rate: float = 0.001
    commission_rate: float = 0.0001
    min_commission: float = 5


DEFAULT_RUNTIME_PARAMS = RuntimeParams(principal=None)


class RuntimeParamsError(ValueError):
    """运行时参数校验错误."""


def validate_runtime_params(params: RuntimeParams) -> bool:
    """校验运行时参数边界 (AC-FR0020-2).

    Args:
        params: 待校验参数.

    Returns:
        True 当所有字段满足边界约束.

    Raises:
        RuntimeParamsError: 当任一字段越界, message 指明具体字段与约束.
    """
    if params.principal is None or params.principal <= 0:
        raise RuntimeParamsError("本金必须 > 0")
    if not (0 <= params.slippage_rate <= 0.1):
        raise RuntimeParamsError("滑点必须在 0~0.1")
    if not (0 <= params.stamp_tax_rate <= 0.01):
        raise RuntimeParamsError("印花税比率必须在 0~0.01")
    if not (0 <= params.commission_rate <= 0.01):
        raise RuntimeParamsError("佣金比率必须在 0~0.01")
    if params.min_commission < 0:
        raise RuntimeParamsError("单笔最低佣金必须 >= 0")
    return True


__all__ = [
    "DEFAULT_RUNTIME_PARAMS",
    "RuntimeParams",
    "RuntimeParamsError",
    "validate_runtime_params",
]
