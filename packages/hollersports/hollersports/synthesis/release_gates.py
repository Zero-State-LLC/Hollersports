from __future__ import annotations

from typing import Any

from .models import GateStatus, ReleaseGateEvidence, ReleaseGateResult, ReleaseGateThresholds, ReleaseReadinessPacket


def _gate(gate: str, status: GateStatus, reason: str, **evidence: Any) -> ReleaseGateResult:
    return ReleaseGateResult(gate=gate, status=status, reason=reason, evidence=evidence)


def evaluate_release_readiness(evidence: ReleaseGateEvidence, thresholds: ReleaseGateThresholds) -> ReleaseReadinessPacket:
    gates: list[ReleaseGateResult] = []

    def has_provenance(gate: str) -> bool:
        return bool(evidence.provenance.get(f"gate_{gate.lower()}", "").strip())

    if evidence.temporal_replay_passed is None or not has_provenance("A"):
        gates.append(_gate("A", GateStatus.NOT_COMPUTABLE, "temporal replay evidence is missing"))
    else:
        gates.append(_gate("A", GateStatus.PASS if evidence.temporal_replay_passed else GateStatus.FAIL, "temporal replay passed" if evidence.temporal_replay_passed else "temporal replay failed"))

    if not has_provenance("B") or evidence.devig_sample_size < thresholds.minimum_backtest_sample or evidence.raw_implied_brier is None or evidence.fair_probability_brier is None:
        gates.append(_gate("B", GateStatus.NOT_COMPUTABLE, "de-vig comparison lacks held-out sample evidence", sample_size=evidence.devig_sample_size))
    else:
        passed = evidence.fair_probability_brier < evidence.raw_implied_brier
        gates.append(_gate("B", GateStatus.PASS if passed else GateStatus.FAIL, "fair probabilities beat raw implied Brier" if passed else "fair probabilities did not beat raw implied Brier", raw_brier=evidence.raw_implied_brier, fair_brier=evidence.fair_probability_brier, sample_size=evidence.devig_sample_size))

    if evidence.qualified_fingerprint_count is None or not has_provenance("C"):
        gates.append(_gate("C", GateStatus.NOT_COMPUTABLE, "qualified fingerprint count is missing"))
    else:
        passed = evidence.qualified_fingerprint_count >= thresholds.minimum_qualified_fingerprints
        gates.append(_gate("C", GateStatus.PASS if passed else GateStatus.FAIL, "minimum qualified fingerprints met" if passed else "minimum qualified fingerprints not met", qualified=evidence.qualified_fingerprint_count))

    if not has_provenance("D") or evidence.prop_sample_size < thresholds.minimum_backtest_sample or evidence.prop_monotonic_violation_rate is None or evidence.prop_calibration_error is None:
        gates.append(_gate("D", GateStatus.NOT_COMPUTABLE, "prop surface gate lacks held-out evidence", sample_size=evidence.prop_sample_size))
    else:
        passed = evidence.prop_monotonic_violation_rate <= thresholds.maximum_prop_monotonic_violation_rate and evidence.prop_calibration_error <= thresholds.maximum_prop_calibration_error
        gates.append(_gate("D", GateStatus.PASS if passed else GateStatus.FAIL, "prop surface invariants and calibration passed" if passed else "prop surface invariants or calibration failed", violation_rate=evidence.prop_monotonic_violation_rate, calibration_error=evidence.prop_calibration_error, sample_size=evidence.prop_sample_size))

    if not has_provenance("E") or evidence.joint_sample_size < thresholds.minimum_backtest_sample or evidence.independent_joint_log_loss is None or evidence.modeled_joint_log_loss is None:
        gates.append(_gate("E", GateStatus.NOT_COMPUTABLE, "joint model comparison lacks held-out evidence", sample_size=evidence.joint_sample_size))
    else:
        passed = evidence.modeled_joint_log_loss < evidence.independent_joint_log_loss
        gates.append(_gate("E", GateStatus.PASS if passed else GateStatus.FAIL, "joint model beat naive independence" if passed else "joint model did not beat naive independence", independent_log_loss=evidence.independent_joint_log_loss, modeled_log_loss=evidence.modeled_joint_log_loss, sample_size=evidence.joint_sample_size))

    if not has_provenance("F") or evidence.verdict_sample_size < thresholds.minimum_backtest_sample or evidence.verdict_discrimination is None:
        gates.append(_gate("F", GateStatus.NOT_COMPUTABLE, "verdict discrimination lacks held-out evidence", sample_size=evidence.verdict_sample_size))
    else:
        passed = evidence.verdict_discrimination >= thresholds.minimum_verdict_discrimination
        gates.append(_gate("F", GateStatus.PASS if passed else GateStatus.FAIL, "verdict buckets demonstrate separation" if passed else "verdict buckets do not demonstrate separation", discrimination=evidence.verdict_discrimination, sample_size=evidence.verdict_sample_size))

    if not has_provenance("G") or evidence.pass_retained_sample < thresholds.minimum_pass_retained_sample or evidence.forced_pick_calibration_error is None or evidence.pass_filtered_calibration_error is None:
        gates.append(_gate("G", GateStatus.NOT_COMPUTABLE, "PASS comparison lacks retained held-out evidence", retained_sample=evidence.pass_retained_sample))
    else:
        passed = evidence.pass_filtered_calibration_error < evidence.forced_pick_calibration_error
        gates.append(_gate("G", GateStatus.PASS if passed else GateStatus.FAIL, "PASS improved calibration" if passed else "PASS did not improve calibration", forced_error=evidence.forced_pick_calibration_error, pass_filtered_error=evidence.pass_filtered_calibration_error, retained_sample=evidence.pass_retained_sample))

    if evidence.v05_regression_passed is None or not has_provenance("H"):
        gates.append(_gate("H", GateStatus.NOT_COMPUTABLE, "V0.5 regression evidence is missing"))
    else:
        gates.append(_gate("H", GateStatus.PASS if evidence.v05_regression_passed else GateStatus.FAIL, "V0.5 regression remains green" if evidence.v05_regression_passed else "V0.5 regression failed"))

    ready = all(gate.status == GateStatus.PASS for gate in gates)
    return ReleaseReadinessPacket(status="READY" if ready else "NOT_READY", gates=tuple(gates))
