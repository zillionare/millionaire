"""因子清单与勾选解析。

回测向导的第二步会列出全部因子（按分组），允许逐个勾选；
策略侧用 :func:`resolve_feature_selection` 归一化勾选结果。
外部插件与内置因子通过统一注册表合并。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quantide.factors.registry import (
    feature_docs,
    feature_groups,
)
from quantide.factors.registry import (
    resolve_feature_selection as _resolve_feature_selection,
)


@dataclass(frozen=True)
class FeatureSpec:
    """一个因子的元信息。"""

    name: str
    group: str
    doc: str


def list_feature_specs() -> list[FeatureSpec]:
    """按分组顺序返回全部因子元信息。"""
    docs = feature_docs()
    specs: list[FeatureSpec] = []
    for group, names in feature_groups().items():
        for name in names:
            specs.append(FeatureSpec(name=name, group=group, doc=docs.get(name, "")))
    return specs


def resolve_feature_selection(requested: Sequence[str] | None) -> list[str]:
    """归一化勾选的因子列表；``None`` 或空表示使用全部已注册因子。"""
    return _resolve_feature_selection(requested)
