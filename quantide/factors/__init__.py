"""因子库：原始 K 线 → 因子表，与策略解耦。"""

from quantide.factors.alpha import (
    FACTOR_VERSION,
    FEATURE_COLS,
    FEATURE_DOCS,
    FEATURE_GROUPS,
    compute_alpha_features,
    standardize_features,
)
from quantide.factors.alphatest import (
    SingleFactorResult,
    load_factor_panel,
    study_single_factor,
)
from quantide.factors.catalog import (
    FeatureSpec,
    list_feature_specs,
    resolve_feature_selection,
)
from quantide.factors.metadata import (
    FACTOR_METADATA,
    FactorDefinition,
    factor_definition,
    list_factor_definitions,
)
from quantide.factors.research import HorizonRequest, HorizonResult, study_horizon

__all__ = [
    "FACTOR_VERSION",
    "FEATURE_COLS",
    "FEATURE_DOCS",
    "FEATURE_GROUPS",
    "FACTOR_METADATA",
    "FactorDefinition",
    "FeatureSpec",
    "HorizonRequest",
    "HorizonResult",
    "SingleFactorResult",
    "load_factor_panel",
    "study_single_factor",
    "compute_alpha_features",
    "factor_definition",
    "list_factor_definitions",
    "list_feature_specs",
    "resolve_feature_selection",
    "standardize_features",
    "study_horizon",
]
