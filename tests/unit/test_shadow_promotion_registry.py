from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from hollersports.ml.promotion_registry import (
    ModelFamily,
    PromotionRecord,
    RegistryHealthStatus,
    ShadowPromotionRegistry,
    stable_hash,
)


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _record(**overrides: object) -> PromotionRecord:
    artifact = stable_hash({"model": overrides.get("model_id", "m1"), "weights": [1, 2, 3]})
    evidence = stable_hash({"folds": 5, "rows": 100})
    values = {
        "model_family": ModelFamily.PLAYER_OUTCOME,
        "sport": "NBA",
        "market_class": "PLAYER_PROP",
        "market_subclass": "POINTS",
        "trained_at": BASE,
        "evaluated_at": BASE + timedelta(hours=1),
        "promoted_at": BASE + timedelta(hours=2),
        "artifact_hash": artifact,
        "evidence_hash": evidence,
        "sample_size": 100,
        "sample_minimum": 20,
        "metrics": {"brier": 0.18, "auc": 0.62},
        "model_id": "m1",
    }
    values.update(overrides)
    return PromotionRecord(**values)  # type: ignore[arg-type]


def test_append_query_and_health_are_shadow_only(tmp_path):
    registry = ShadowPromotionRegistry(tmp_path / "promotions.jsonl")
    record = registry.append(_record())

    assert registry.health().ok
    assert registry.health().status is RegistryHealthStatus.OK
    assert registry.query(sport="NBA", model_family=ModelFamily.PLAYER_OUTCOME) == [record]
    assert registry.query(promoted_from=BASE + timedelta(hours=3)) == []

    payload = registry.path.read_text(encoding="utf-8")
    assert '"capital_authority":false' in payload
    assert '"execution_authority":false' in payload


def test_record_validation_blocks_unsafe_and_unstable_inputs():
    with pytest.raises(ValueError, match="timezone-aware"):
        _record(trained_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="sample_size"):
        _record(sample_size=10, sample_minimum=20)
    with pytest.raises(ValueError, match="capital_authority"):
        _record(capital_authority=True)
    with pytest.raises(ValueError, match="artifact_hash"):
        _record(artifact_hash="not-stable")
    with pytest.raises(ValueError, match="trained_at <= evaluated_at"):
        _record(trained_at=BASE + timedelta(hours=3))


@pytest.mark.parametrize("family", list(ModelFamily))
def test_all_model_families_are_supported(tmp_path, family):
    registry = ShadowPromotionRegistry(tmp_path / f"{family.value}.jsonl")
    record = _record(
        model_family=family,
        artifact_hash=stable_hash({"family": family.value, "artifact": 1}),
        evidence_hash=stable_hash({"family": family.value, "evidence": 1}),
    )
    registry.append(record)
    assert registry.query(model_family=family) == [record]


def test_duplicate_guard_blocks_same_artifact_evidence_market(tmp_path):
    registry = ShadowPromotionRegistry(tmp_path / "promotions.jsonl")
    first = _record(record_id="r1")
    registry.append(first)

    with pytest.raises(ValueError, match="duplicate artifact/evidence"):
        registry.append(_record(record_id="r2"))


def test_integrity_health_detects_tampering(tmp_path):
    registry = ShadowPromotionRegistry(tmp_path / "promotions.jsonl")
    registry.append(_record())

    entry = json.loads(registry.path.read_text(encoding="utf-8"))
    entry["payload"]["metrics"]["brier"] = 0.99
    registry.path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    health = registry.health()
    assert not health.ok
    assert health.status is RegistryHealthStatus.CORRUPT
    assert any("entry_hash mismatch" in error for error in health.errors)


def test_temporal_query_requires_aware_bounds(tmp_path):
    registry = ShadowPromotionRegistry(tmp_path / "promotions.jsonl")
    with pytest.raises(ValueError, match="timezone-aware"):
        registry.query(promoted_from=datetime(2026, 1, 1))
