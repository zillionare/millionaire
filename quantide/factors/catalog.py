"""因子清单与勾选解析。

回测向导的第二步会列出全部因子（按分组），允许逐个勾选；
策略侧用 :func:`resolve_feature_selection` 归一化勾选结果。
"""

from __future__ import annotations

from dataclasses import dataclass

from quantide.factors.alpha import FEATURE_DOCS, FEATURE_GROUPS


@dataclass(frozen=True)
class FeatureSpec:
    """一个因子的元信息。"""

    name: str
    group: str
    doc: str


def list_feature_specs() -> list[FeatureSpec]:
    """按分组顺序返回全部因子元信息。"""
    specs: list[FeatureSpec] = []
    for group, names in FEATURE_GROUPS.items():
        for name in names:
            specs.append(FeatureSpec(name=name, group=group, doc=FEATURE_DOCS.get(name, "")))
    return specs


def resolve_feature_selection(requested: list[str] | None) -> list[str]:
    """归一化勾选的因子列表。

    Args:
        requested: 用户勾选的因子名；``None`` 或空表示使用全部因子。

    Returns:
        list[str]: 有效且去重后的因子名（保持 :data:`FEATURE_GROUPS` 的顺序）。

    Raises:
        ValueError: 勾选了不存在的因子。
    """
    if not requested:
        return list(
            FEATURE_GROUPS and [name for names in FEATURE_GROUPS.values() for name in names]
        )
    known = {name for names in FEATURE_GROUPS.values() for name in names}
    unknown = [name for name in requested if name not in known]
    if unknown:
        raise ValueError(f"未知因子: {', '.join(sorted(set(unknown)))}")
    selected = set(requested)
    return [name for names in FEATURE_GROUPS.values() for name in names if name in selected]
