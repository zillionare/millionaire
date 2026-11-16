"""Deterministic audit contracts, runners and future-data perturbation checks."""

from quantide.audit.account import AccountLedger, Position
from quantide.audit.checks import (
    callback_check,
    future_invariance_check,
    ledger_invariant_check,
)
from quantide.audit.factor import audit_factor, build_factor_spec
from quantide.audit.future import (
    PerturbationResult,
    assert_future_invariance,
    frame_digest,
    perturb_frame,
)
from quantide.audit.models import (
    AuditCheck,
    AuditReport,
    AuditSpec,
    AuditStatus,
    canonical_hash,
)
from quantide.audit.performance import (
    AttributionPeriod,
    AuditTrade,
    PeriodAttribution,
    attribute_period,
    link_carino,
)
from quantide.audit.runner import AuditRunner
from quantide.audit.statistics import (
    StatisticalProfile,
    empirical_p_value,
    null_rank_ic_distribution,
    permute_within_date,
    random_factor,
    rank_ic_summary,
    summarize_null_distribution,
)
from quantide.audit.store import ReportStore
from quantide.audit.synthetic import (
    RandomControl,
    SignalExperiment,
    matched_benchmark_excess,
    signal_recovery,
    study_synthetic_signal,
    synthetic_panel,
    zero_drift_control,
)

__all__ = [
    "AccountLedger",
    "AuditCheck",
    "AuditReport",
    "AuditRunner",
    "AuditSpec",
    "AuditTrade",
    "AttributionPeriod",
    "AuditStatus",
    "PeriodAttribution",
    "PerturbationResult",
    "ReportStore",
    "RandomControl",
    "SignalExperiment",
    "StatisticalProfile",
    "Position",
    "assert_future_invariance",
    "audit_factor",
    "callback_check",
    "attribute_period",
    "build_factor_spec",
    "canonical_hash",
    "empirical_p_value",
    "frame_digest",
    "future_invariance_check",
    "ledger_invariant_check",
    "link_carino",
    "matched_benchmark_excess",
    "null_rank_ic_distribution",
    "permute_within_date",
    "perturb_frame",
    "random_factor",
    "signal_recovery",
    "rank_ic_summary",
    "study_synthetic_signal",
    "summarize_null_distribution",
    "synthetic_panel",
    "zero_drift_control",
]
