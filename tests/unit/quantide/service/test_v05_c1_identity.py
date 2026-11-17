"""C1 contracts: model identity and fail-closed historical dependencies."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest

from quantide.service.model_store import ModelArtifact, ModelStore
from quantide.strategies.example import ml_momentum_reversal as ml
from quantide.strategies.example.ml_momentum_reversal import MLMomentumReversalStrategy


def _strategy(**overrides: Any) -> MLMomentumReversalStrategy:
    return MLMomentumReversalStrategy(
        None,  # type: ignore[arg-type]
        {**MLMomentumReversalStrategy.default_config(), **overrides},
    )


def _artifact(key: str, *, pipeline_version: str) -> ModelArtifact:
    return ModelArtifact(
        model_key=key,
        strategy_name="MLMomentumReversalStrategy",
        config_hash="cfg",
        train_end="2024-12-31",
        effective_from="2024-12-31",
        pipeline_version=pipeline_version,
        metrics={"rank_ic": 0.02},
    )


def test_model_key_encodes_pipeline_and_custom_symbols() -> None:
    baseline = _strategy()
    custom = _strategy(assets=["AAA", "BBB"], symbols=["AAA", "BBB"], seed=7)

    assert baseline._model_key != custom._model_key
    assert isinstance(ml.PIPELINE_VERSION, str)
    assert ml.PIPELINE_VERSION


def test_reload_rejects_artifact_from_another_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ModelStore(root=tmp_path)
    monkeypatch.setattr(ml, "model_store", store)
    strategy = _strategy()
    key = strategy._model_key
    store.save(
        key=key,
        model={"stale": True},
        metadata=_artifact(key, pipeline_version="ancient-pipeline"),
    )

    assert strategy._load_model_from_store(dt.date(2024, 12, 31)) is False


def test_model_key_encodes_effective_seed() -> None:
    """Official models with different training randomness remain distinct."""
    assert _strategy()._model_key == _strategy(seed=42)._model_key
    assert _strategy(seed=7)._model_key != _strategy(seed=99)._model_key
