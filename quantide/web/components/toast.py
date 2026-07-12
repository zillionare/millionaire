"""FR-0170 UI 内通知 (toast/banner) 规则.

定义 toast 类型 (success/error/warning/info) 的自动消失时长、
ARIA role 属性要求与语义图标.

通知类型按触发场景:
- success: 操作成功, 3s 自动消失, hover 暂停
- error: 操作失败, 不自动消失, 必须手动关闭, 强制 ARIA role="alert"
- warning: 需要提醒但不阻塞, 持续到用户处理, 可关闭
- info: 一般提示, 5s 自动消失, hover 暂停
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ToastLevel(str, Enum):
    """toast 级别."""

    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


_AUTO_DISMISS_SECONDS: dict[ToastLevel, int | None] = {
    ToastLevel.SUCCESS: 3,
    ToastLevel.ERROR: None,
    ToastLevel.WARNING: None,
    ToastLevel.INFO: 5,
}

_ICONS: dict[ToastLevel, str] = {
    ToastLevel.SUCCESS: "check",
    ToastLevel.ERROR: "x",
    ToastLevel.WARNING: "alert-triangle",
    ToastLevel.INFO: "info",
}


@dataclass
class ToastConfig:
    """toast 配置.

    Attributes:
        level: toast 级别.
        message: 显示消息.
        auto_dismiss: 是否自动消失.
        dismiss_seconds: 自动消失秒数 (None 表示不自动消失).
    """

    level: ToastLevel
    message: str
    auto_dismiss: bool
    dismiss_seconds: int | None

    @classmethod
    def create(cls, level: ToastLevel, message: str) -> ToastConfig:
        """创建 toast 配置.

        Args:
            level: toast 级别.
            message: 显示消息.

        Returns:
            ToastConfig 实例, auto_dismiss / dismiss_seconds 按级别规则填充.
        """
        seconds = auto_dismiss_seconds(level)
        return cls(
            level=level,
            message=message,
            auto_dismiss=seconds is not None,
            dismiss_seconds=seconds,
        )


def auto_dismiss_seconds(level: ToastLevel) -> int | None:
    """获取自动消失秒数.

    Args:
        level: toast 级别.

    Returns:
        秒数; None 表示不自动消失.
    """
    return _AUTO_DISMISS_SECONDS[level]


def is_auto_dismiss(level: ToastLevel) -> bool:
    """判断是否自动消失.

    Args:
        level: toast 级别.

    Returns:
        True 当该级别自动消失.
    """
    return _AUTO_DISMISS_SECONDS[level] is not None


def requires_aria_alert_role(level: ToastLevel) -> bool:
    """AC-5: 错误 toast 强制 ARIA role='alert'.

    Args:
        level: toast 级别.

    Returns:
        True 当且仅当级别为 error.
    """
    return level == ToastLevel.ERROR


def icon_for_level(level: ToastLevel) -> str:
    """获取语义图标名.

    Args:
        level: toast 级别.

    Returns:
        图标名 (✓ / ✕ / ⚠ / ⓘ 对应 check / x / alert-triangle / info).
    """
    return _ICONS[level]


__all__ = [
    "ToastConfig",
    "ToastLevel",
    "auto_dismiss_seconds",
    "icon_for_level",
    "is_auto_dismiss",
    "requires_aria_alert_role",
]
