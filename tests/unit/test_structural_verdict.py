from hollersports.runes.structural_verdict import (
    StructuralThresholds,
    structural_verdict,
)


THRESHOLDS = StructuralThresholds(
    minimum_data_quality=0.7,
    maximum_market_entropy=0.4,
    minimum_dependency_confidence=0.6,
    edge_probability_points=0.03,
    conflict_probability_points=0.08,
    fair_pricing_tolerance=0.015,
)


def test_structural_verdict_fails_closed_without_calibration():
    packet = structural_verdict(
        book_probability=0.55,
        consensus_probability=0.52,
        reality_probability=0.51,
        data_quality=0.9,
        market_entropy=0.1,
        thresholds=None,
    )
    assert packet["verdict"] == "NOT_COMPUTABLE"
    assert packet["capital_authority"] is False
    assert packet["execution_authority"] is False


def test_structural_verdict_pass_is_normal_outcome():
    packet = structural_verdict(
        book_probability=0.55,
        consensus_probability=0.52,
        reality_probability=0.51,
        data_quality=0.9,
        market_entropy=0.7,
        thresholds=THRESHOLDS,
    )
    assert packet["verdict"] == "PASS"


def test_structural_verdict_requires_dependency_for_parlay():
    packet = structural_verdict(
        book_probability=0.55,
        consensus_probability=0.52,
        reality_probability=0.51,
        data_quality=0.9,
        market_entropy=0.1,
        thresholds=THRESHOLDS,
        dependency_required=True,
        dependency_confidence=0.2,
    )
    assert packet["verdict"] == "NOT_COMPUTABLE"


def test_structural_verdict_separates_evidence_families():
    packet = structural_verdict(
        book_probability=0.59,
        consensus_probability=0.52,
        reality_probability=0.51,
        data_quality=0.9,
        market_entropy=0.1,
        thresholds=THRESHOLDS,
    )
    assert packet["verdict"] == "RETAIL_PRICED"
    assert set(packet["evidence"]) == {
        "bookmaker",
        "market",
        "player",
        "dependency",
        "data_quality",
    }
