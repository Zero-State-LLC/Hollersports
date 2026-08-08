from hollersports.props import (
    ComputationStatus,
    PropLadder,
    PropThreshold,
    reconstruct_survival,
    validate_ladder,
)


def test_prop_surface_is_monotonic_and_bounded_after_repair():
    ladder = PropLadder(
        event_id="event-1",
        market="POINTS",
        player="player-1",
        thresholds=(
            PropThreshold(threshold=20, fair_probability=0.60),
            PropThreshold(threshold=25, fair_probability=0.64),
            PropThreshold(threshold=30, fair_probability=0.30),
        ),
    )
    surface = reconstruct_survival(ladder)
    values = [point.survival_probability for point in surface.points]
    assert surface.status == ComputationStatus.COMPUTABLE
    assert surface.weak_fit is True
    assert all(0.0 <= value <= 1.0 for value in values)
    assert values == sorted(values, reverse=True)


def test_prop_ladder_with_one_threshold_is_not_computable():
    ladder = PropLadder(
        event_id="event-1",
        market="POINTS",
        thresholds=(PropThreshold(threshold=20, fair_probability=0.60),),
    )
    assert validate_ladder(ladder).status == ComputationStatus.NOT_COMPUTABLE


def test_prop_domain_cannot_gain_execution_authority():
    try:
        PropLadder(
            event_id="event-1",
            market="POINTS",
            thresholds=(PropThreshold(threshold=20, fair_probability=0.60),),
            execution_authority=True,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("props domain accepted execution authority")
