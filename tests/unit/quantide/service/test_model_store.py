"""ModelStore 持久化测试。"""

from __future__ import annotations

from pathlib import Path

from quantide.service.model_store import (
    ModelArtifact,
    ModelStore,
    model_key,
)


def test_model_key_changes_with_model_config():
    key1 = model_key("Demo", {"train_window": 45, "retrain_days": 5, "commission": 1e-4})
    key2 = model_key("Demo", {"train_window": 30, "retrain_days": 5, "commission": 1e-4})
    key3 = model_key("Demo", {"train_window": 45, "retrain_days": 5, "commission": 2e-4})
    assert key1 != key2
    assert key1 == key3  # 交易费用不影响模型版本


def test_model_store_saves_and_overwrites_latest(tmp_path):
    store = ModelStore(tmp_path)
    key = "Demo-abc123"
    meta1 = ModelArtifact(
        model_key=key,
        strategy_name="Demo",
        config_hash="abc123",
        train_end="2026-10-24",
        effective_from="2026-10-27",
        engine="LightGBM",
    )
    store.save(key=key, model={"version": 1}, metadata=meta1)
    model, loaded = store.load(key)
    assert model == {"version": 1}
    assert loaded is not None
    assert loaded.train_end == "2026-10-24"

    meta2 = ModelArtifact(
        model_key=key,
        strategy_name="Demo",
        config_hash="abc123",
        train_end="2026-10-27",
        effective_from="2026-10-28",
        engine="LightGBM",
    )
    store.save(key=key, model={"version": 2}, metadata=meta2)
    model, loaded = store.load(key)
    assert model == {"version": 2}
    assert loaded is not None
    assert loaded.effective_from == "2026-10-28"


def test_model_store_missing_and_clear(tmp_path):
    store = ModelStore(tmp_path)
    assert store.load("missing") == (None, None)
    meta = ModelArtifact(
        model_key="k",
        strategy_name="Demo",
        config_hash="c",
        train_end="2026-10-24",
        effective_from="2026-10-27",
    )
    store.save(key="k", model=1, metadata=meta)
    store.clear("k")
    assert store.load("k") == (None, None)


def test_model_store_handles_corrupt_metadata(tmp_path):
    store = ModelStore(tmp_path)
    directory = store.root / "bad"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "latest.json").write_text("{not-json", encoding="utf-8")
    (directory / "latest.pkl").write_bytes(b"x")
    model, meta = store.load("bad")
    assert model is None
    assert meta is None


def test_model_store_keeps_immutable_old_version_for_gap_replay(tmp_path):
    store = ModelStore(tmp_path)
    key = "Demo-ref"
    meta1 = ModelArtifact(
        model_key=key,
        strategy_name="Demo",
        config_hash="c",
        train_end="2026-10-20",
        effective_from="2026-10-21",
    )
    saved1 = store.save(key=key, model={"version": 1}, metadata=meta1)
    meta2 = ModelArtifact(
        model_key=key,
        strategy_name="Demo",
        config_hash="c",
        train_end="2026-10-27",
        effective_from="2026-10-28",
    )
    saved2 = store.save(key=key, model={"version": 2}, metadata=meta2)

    old_model, old_meta = store.load_ref(str(saved1.extra["model_ref"]))
    latest_model, latest_meta = store.load(key)

    assert old_model == {"version": 1}
    assert old_meta is not None and old_meta.effective_from == "2026-10-21"
    assert latest_model == {"version": 2}
    assert latest_meta is not None and latest_meta.model_hash == saved2.model_hash


def test_model_store_artifact_identity_includes_training_context(tmp_path):
    store = ModelStore(tmp_path)
    key = "Demo-context"
    first = store.save(
        key=key,
        model={"weights": [1.0, 2.0]},
        metadata=ModelArtifact(
            model_key=key,
            strategy_name="Demo",
            config_hash="c",
            train_end="2024-01-01",
            effective_from="2024-01-02",
        ),
    )
    second = store.save(
        key=key,
        model={"weights": [1.0, 2.0]},
        metadata=ModelArtifact(
            model_key=key,
            strategy_name="Demo",
            config_hash="c",
            train_end="2024-02-01",
            effective_from="2024-02-02",
        ),
    )

    old_model, old_meta = store.load_ref(str(first.extra["model_ref"]))

    assert first.extra["model_ref"] != second.extra["model_ref"]
    assert old_model == {"weights": [1.0, 2.0]}
    assert old_meta is not None and old_meta.effective_from == "2024-01-02"


def test_model_store_crash_before_latest_pointer_preserves_old_consistent_model(
    tmp_path, monkeypatch
):
    store = ModelStore(tmp_path)
    key = "Demo-crash"
    store.save(
        key=key,
        model={"version": 1},
        metadata=ModelArtifact(
            model_key=key,
            strategy_name="Demo",
            config_hash="c",
            train_end="2024-01-01",
            effective_from="2024-01-02",
        ),
    )
    import quantide.service.model_store as module

    real_write_json = module.write_json

    def fail_latest(path, payload):
        if Path(path).name == "latest.json":
            raise OSError("simulated crash before latest pointer")
        return real_write_json(path, payload)

    monkeypatch.setattr(module, "write_json", fail_latest)
    try:
        store.save(
            key=key,
            model={"version": 2},
            metadata=ModelArtifact(
                model_key=key,
                strategy_name="Demo",
                config_hash="c",
                train_end="2024-02-01",
                effective_from="2024-02-02",
            ),
        )
    except OSError:
        pass

    model, meta = store.load(key)

    assert model == {"version": 1}
    assert meta is not None and meta.effective_from == "2024-01-02"


def test_legacy_upgrade_crash_keeps_matching_model_and_metadata_pair(tmp_path, monkeypatch):
    import json
    import pickle

    store = ModelStore(tmp_path)
    key = "Demo-legacy"
    directory, model_path, meta_path = store._paths(key)
    directory.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(pickle.dumps({"weights": [1.0]}))
    meta_path.write_text(
        json.dumps(
            {
                "model_key": key,
                "strategy_name": "Demo",
                "config_hash": "old",
                "train_end": "2024-01-01",
                "effective_from": "2024-01-02",
            }
        ),
        encoding="utf-8",
    )
    import quantide.service.model_store as module

    real_write_json = module.write_json

    def fail_new_latest(path, payload):
        if Path(path).name == "latest.json" and payload.get("config_hash") == "new":
            raise OSError("simulated crash during legacy upgrade")
        return real_write_json(path, payload)

    monkeypatch.setattr(module, "write_json", fail_new_latest)
    try:
        store.save(
            key=key,
            model={"weights": [2.0]},
            metadata=ModelArtifact(
                model_key=key,
                strategy_name="Demo",
                config_hash="new",
                train_end="2024-02-01",
                effective_from="2024-02-02",
            ),
        )
    except OSError:
        pass

    model, meta = store.load(key)

    assert model == {"weights": [1.0]}
    assert meta is not None and meta.config_hash == "old"


def test_legacy_bare_ref_is_rejected_when_weights_match_multiple_contexts(tmp_path):
    store = ModelStore(tmp_path)
    key = "Demo-ambiguous"
    for config_hash, effective_from in (("a", "2024-01-02"), ("b", "2024-02-02")):
        store.save(
            key=key,
            model={"weights": [1.0]},
            metadata=ModelArtifact(
                model_key=key,
                strategy_name="Demo",
                config_hash=config_hash,
                train_end=effective_from,
                effective_from=effective_from,
            ),
        )
    from quantide.service.model_store import model_key

    bare_hash = next(
        meta["model_hash"]
        for meta in (
            __import__("json").loads(path.read_text(encoding="utf-8"))
            for path in (tmp_path / key / "versions").glob("*.json")
        )
    )

    assert store.load_ref(bare_hash) == (None, None)
    assert store.load_ref(model_key("Demo", {"train_window": 1}))[0] is None
