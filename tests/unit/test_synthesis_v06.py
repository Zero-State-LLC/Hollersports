from datetime import datetime, timezone

from hollersports.synthesis import (
    GateStatus, ReleaseGateEvidence, ReleaseGateThresholds, StructuralEvidenceObservation,
    SynthesisStore, evaluate_release_readiness,
)
from hollersports.runes.structural_verdict import StructuralThresholds


THRESHOLDS = StructuralThresholds(0.7, 0.4, 0.6, 0.03, 0.08, 0.015)
GATE_THRESHOLDS = ReleaseGateThresholds(
    minimum_backtest_sample=20, minimum_qualified_fingerprints=2,
    maximum_prop_monotonic_violation_rate=0.0, maximum_prop_calibration_error=0.05,
    minimum_verdict_discrimination=0.1, minimum_pass_retained_sample=10,
)


def structural_observation():
    return StructuralEvidenceObservation(
        observation_id="struct-1", subject_id="market-1", subject_type="SINGLE",
        observed_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        recorded_at=datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc),
        source="fixture", source_hash="source-hash", threshold_source_id="calibration-1",
        threshold_source_hash="threshold-hash", book_probability=0.59,
        consensus_probability=0.52, reality_probability=0.51, data_quality=0.9,
        market_entropy=0.1, thresholds=THRESHOLDS,
        evidence_references={"bookmaker": "book-analysis-1", "market": "consensus-1", "context": "context-1", "player": "surface-1"},
    )


def passing_evidence():
    return ReleaseGateEvidence(
        temporal_replay_passed=True, devig_sample_size=100, raw_implied_brier=0.24,
        fair_probability_brier=0.22, qualified_fingerprint_count=3, prop_sample_size=100,
        prop_monotonic_violation_rate=0.0, prop_calibration_error=0.03, joint_sample_size=100,
        independent_joint_log_loss=0.8, modeled_joint_log_loss=0.7, verdict_sample_size=100,
        verdict_discrimination=0.2, pass_retained_sample=50, forced_pick_calibration_error=0.08,
        pass_filtered_calibration_error=0.05, v05_regression_passed=True,
        provenance={f"gate_{letter.lower()}": f"evidence-{letter}" for letter in "ABCDEFGH"},
    )


def test_release_readiness_requires_every_gate_to_pass():
    packet = evaluate_release_readiness(passing_evidence(), GATE_THRESHOLDS)
    assert packet.status == "READY"
    assert [gate.gate for gate in packet.gates] == list("ABCDEFGH")
    assert all(gate.status == GateStatus.PASS for gate in packet.gates)
    assert packet.capital_authority is False


def test_pass_gate_fails_when_pass_does_not_improve_calibration():
    evidence = passing_evidence().model_copy(update={"pass_filtered_calibration_error": 0.09})
    packet = evaluate_release_readiness(evidence, GATE_THRESHOLDS)
    gate_g = next(gate for gate in packet.gates if gate.gate == "G")
    assert packet.status == "NOT_READY"
    assert gate_g.status == GateStatus.FAIL


def test_missing_gate_evidence_is_not_computable_not_passed():
    packet = evaluate_release_readiness(ReleaseGateEvidence(), GATE_THRESHOLDS)
    assert packet.status == "NOT_READY"
    assert all(gate.status == GateStatus.NOT_COMPUTABLE for gate in packet.gates)


def test_structural_synthesis_persists_separate_deterministic_derivation(tmp_path):
    store = SynthesisStore(tmp_path)
    observation = structural_observation()
    analysis = store.derive(observation, "analysis-1", datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc))
    store.append_bundle(observation, analysis)
    assert analysis.verdict_packet["verdict"] == "RETAIL_PRICED"
    assert store.latest_at_or_before("market-1", datetime(2026, 1, 1, 10, 1, 30, tzinfo=timezone.utc)) == (observation, None)
    assert store.latest_at_or_before("market-1", datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc)) == (observation, analysis)
    assert store.integrity_issues() == []
