from hollersports.dependency import (
    Computability,
    DependencyEdge,
    DependencyMethod,
    LegProbability,
    analyze_parlay,
    joint_probability,
)


def _legs():
    return [
        LegProbability(leg_id="a", marginal_probability=0.6),
        LegProbability(leg_id="b", marginal_probability=0.5),
    ]


def test_unknown_dependency_is_not_naively_multiplied():
    result = joint_probability(_legs())
    assert result.status == Computability.NOT_COMPUTABLE
    assert result.joint_probability is None


def test_independence_requires_explicit_opt_in_and_joint_is_capped():
    result = joint_probability(
        _legs(),
        method=DependencyMethod.INDEPENDENT,
        explicitly_allow_independence=True,
    )
    assert result.status == Computability.COMPUTABLE
    assert result.joint_probability == 0.3
    assert result.joint_probability <= min(leg.marginal_probability for leg in _legs())


def test_missing_required_dependency_fails_closed():
    result = analyze_parlay(
        _legs(),
        [
            DependencyEdge(
                source_leg_id="a",
                target_leg_id="missing",
                dependency_type="required",
                required=True,
            )
        ],
        method=DependencyMethod.INDEPENDENT,
        explicitly_allow_independence=True,
    )
    assert result.status == Computability.NOT_COMPUTABLE
