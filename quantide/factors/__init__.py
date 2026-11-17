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
from quantide.factors.registry import (
    all_factor_ids,
    compute_feature_panel,
    factor_metadata,
    feature_docs,
    feature_groups,
)
from quantide.factors.research import HorizonRequest, HorizonResult, study_horizon
from quantide.factors.universe import (
    UniverseFilterConfig,
    UniverseFilterResult,
    filter_universe_for_date,
    filter_universe_panel,
    load_st_status_frame,
)

__all__ = [
    "FACTOR_VERSION",
    "FEATURE_COLS",
    "FEATURE_DOCS",
    "FEATURE_GROUPS",
    "FACTOR_METADATA",
    "FactorDefinition",
    "FeatureSpec",
    "all_factor_ids",
    "compute_feature_panel",
    "factor_metadata",
    "feature_docs",
    "feature_groups",
    "HorizonRequest",
    "HorizonResult",
    "SingleFactorResult",
    "UniverseFilterConfig",
    "UniverseFilterResult",
    "filter_universe_for_date",
    "filter_universe_panel",
    "load_st_status_frame",
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
