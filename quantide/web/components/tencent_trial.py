"""Wizard controls for the optional Tencent demonstration source."""

from fasthtml.common import FT, Div, Input, Label, P

from quantide.config.tencent_trial import trial_status


def TencentTrialControl() -> FT:
    """Show explicit consent and a fixed, non-renewable deadline."""
    status = trial_status()
    return Div(
        Label(
            Input(
                type="checkbox",
                name="tencent_trial_enabled",
                value="on",
                checked=status.enabled,
                disabled=status.expired,
            ),
            " 启用腾讯财经爬虫获取实时行情（仅演示，首次启用后 30 天自动关闭）",
        ),
        P("请确认你有权使用该数据源；勾选不代表取得腾讯或交易所的数据授权。"),
        P("演示结束后，请自行通过扩展接入其它行情实现。关闭或重新配置不会延长演示期。"),
        P(f"截止时间（UTC）：{status.expires_at}" if status.expires_at else "默认关闭"),
        P("演示期已结束，内置腾讯源已停用。" if status.expired else ""),
        cls="rounded-lg border border-gray-200 p-4 mt-4",
    )
