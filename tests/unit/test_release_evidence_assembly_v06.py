from datetime import datetime, timezone

from hollersports.bookmaker import DevigCalibrationResult, MethodCalibrationMetric
from hollersports.dependency import JointBacktestMetric, JointBacktestResult
from hollersports.props import PropBacktestMetric, PropSurfaceBacktestResult
from hollersports.synthesis import ReleaseGateEvidence, assemble_release_gate_evidence

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_assembly_discards_unbound_metric_scalars():
    base = ReleaseGateEvidence(
        devig_sample_size=999,
        raw_implied_brier=0.9,
        fair_probability_brier=0.1,
        provenance={"gate_b": "caller-assertion", "gate_a": "replay:abc"},
    )
    assembled = assemble_release_gate_evidence(base)
    assert assembled.evidence.devig_sample_size == 0
    assert assembled.evidence.raw_implied_brier is None
    assert "gate_b" not in assembled.evidence.provenance
    assert assembled.evidence.provenance["gate_a"] == "replay:abc"


def test_assembly_binds_computed_backtest_packets():
    devig = DevigCalibrationResult(
        status="COMPUTED", bookmaker="book", sport="NBA", market_class="NBA/PROP/POINTS",
        odds_bucket="EVEN", as_of=NOW, minimum_sample=2,
        raw_implied=MethodCalibrationMetric(method="RAW_IMPLIED", status="COMPUTED", sample_size=2, brier=0.3, log_loss=0.6),
        methods=(MethodCalibrationMetric(method="POWER", status="COMPUTED", sample_size=2, brier=0.2, log_loss=0.5),),
        preferred_method="POWER", improvement_over_raw_brier=0.1, evidence_row_ids=("d1", "d2"),
    )
    metric = lambda name, value, sample=2: PropBacktestMetric(name=name, status="COMPUTED", sample_size=sample, value=value)
    props = PropSurfaceBacktestResult(
        status="COMPUTED", market_class="NBA/PROP/POINTS", model_id="p1", as_of=NOW,
        minimum_sample=2, row_count=2, threshold_forecast_count=6,
        monotonic_violation_rate=metric("monotonic_violation_rate", 0.0),
        calibration_error=metric("calibration_error", 0.05, 6), brier=metric("brier", 0.2, 6),
        discrete_crps=metric("discrete_crps", 0.15), evidence_row_ids=("p1", "p2"),
    )
    joint_metric = lambda name, value: JointBacktestMetric(name=name, status="COMPUTED", sample_size=2, value=value)
    joint = JointBacktestResult(
        status="COMPUTED", market_class="NBA/PARLAY", modeled_method="EMPIRICAL", model_id="j1",
        as_of=NOW, minimum_sample=2, leg_count=2,
        independent_brier=joint_metric("independent_brier", 0.3), modeled_brier=joint_metric("modeled_brier", 0.2),
        independent_log_loss=joint_metric("independent_log_loss", 0.7), modeled_log_loss=joint_metric("modeled_log_loss", 0.5),
        log_loss_improvement=0.2, modeled_beats_independence=True, evidence_row_ids=("j1", "j2"),
    )
    assembled = assemble_release_gate_evidence(ReleaseGateEvidence(), devig=devig, props=props, joint=joint)
    evidence = assembled.evidence
    assert (evidence.devig_sample_size, evidence.raw_implied_brier, evidence.fair_probability_brier) == (2, 0.3, 0.2)
    assert (evidence.prop_sample_size, evidence.prop_monotonic_violation_rate, evidence.prop_calibration_error) == (2, 0.0, 0.05)
    assert (evidence.joint_sample_size, evidence.independent_joint_log_loss, evidence.modeled_joint_log_loss) == (2, 0.7, 0.5)
    assert all(evidence.provenance[f"gate_{gate}"].startswith(prefix) for gate, prefix in (("b", "Devig"), ("d", "Prop"), ("e", "Joint")))
    assert set(assembled.packet_fingerprints) == {"devig", "props", "joint"}


def test_not_computable_packet_does_not_supply_gate_provenance():
    unavailable = MethodCalibrationMetric(method="RAW_IMPLIED", status="NOT_COMPUTABLE", sample_size=1, reason="small sample")
    result = DevigCalibrationResult(
        status="NOT_COMPUTABLE", bookmaker="book", sport="NBA", market_class="NBA/PROP", odds_bucket="EVEN",
        as_of=NOW, minimum_sample=20, raw_implied=unavailable, methods=(), reasons=("small sample",), evidence_row_ids=("d1",),
    )
    assembled = assemble_release_gate_evidence(ReleaseGateEvidence(), devig=result)
    assert "devig" in assembled.packet_fingerprints
    assert "gate_b" not in assembled.evidence.provenance
    assert assembled.evidence.devig_sample_size == 0
