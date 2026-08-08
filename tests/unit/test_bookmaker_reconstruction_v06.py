from hollersports.bookmaker import BookmakerQuote, OutcomePrice
from hollersports.bookmaker.consensus import weighted_consensus
from hollersports.bookmaker.devig import additive_devig, devig, multiplicative_devig, power_devig, shin_devig
from hollersports.bookmaker.fingerprint import bookmaker_fingerprint


def _outcomes(home=0.55, away=0.50):
    return (
        OutcomePrice(selection="HOME", observed_probability=home),
        OutcomePrice(selection="AWAY", observed_probability=away),
    )


def _quote(book="book-a", home=0.55, away=0.50):
    return BookmakerQuote(
        bookmaker=book,
        event_id="event-1",
        market_id="m1",
        market_type="MONEYLINE",
        fetched_at="2026-01-01T10:00:00Z",
        source="fixture",
        source_hash=f"hash-{book}",
        outcomes=_outcomes(home, away),
    )


def test_all_devig_methods_return_governed_packets_that_sum_to_one():
    results = [
        multiplicative_devig(_outcomes()),
        additive_devig(_outcomes()),
        power_devig(_outcomes()),
        shin_devig(_outcomes(), z=0.02),
    ]
    for result in results:
        assert result.status == "COMPUTED"
        assert result.capital_authority is False
        assert result.execution_authority is False
        assert result.raw_probabilities == {"HOME": 0.55, "AWAY": 0.50}
        assert result.overround == 0.050000000000000044
        assert abs(sum(result.fair_probabilities.values()) - 1.0) < 1e-9
        assert result.uncertainty is not None
        assert result.method in {"MULTIPLICATIVE", "ADDITIVE", "POWER", "SHIN"}


def test_devig_fail_closed_for_bad_method_and_bad_parameters():
    unsupported = devig(_outcomes(), method="BOOK_CALIBRATED")
    assert unsupported.status == "NOT_COMPUTABLE"
    assert "unsupported" in unsupported.reason
    assert unsupported.fair_probabilities == {}
    bad_shin = shin_devig(_outcomes(), z=1.0)
    assert bad_shin.status == "NOT_COMPUTABLE"
    assert bad_shin.parameters == {"z": 1.0}


def test_weighted_consensus_uses_supplied_factors_and_no_implicit_calibration():
    result = weighted_consensus(
        (_quote("sharp", 0.60, 0.45), _quote("slow", 0.50, 0.55)),
        factors={
            "sharp": {"calibration": 2.0, "freshness": 1.0, "leadership": 1.0, "specialization": 1.0},
            "slow": {"freshness": 0.5},
        },
    )
    assert result.status == "COMPUTED"
    assert result.weights == {"sharp": 0.8, "slow": 0.2}
    assert 1.0 < result.effective_book_count < 2.0
    assert result.weight_entropy > result.entropy >= 0.0
    assert abs(sum(result.probabilities.values()) - 1.0) < 1e-12
    sharp_provenance = next(item for item in result.source_provenance if item["bookmaker"] == "sharp")
    slow_provenance = next(item for item in result.source_provenance if item["bookmaker"] == "slow")
    assert sharp_provenance["calibration_status"] == "SUPPLIED"
    assert slow_provenance["calibration_status"] == "NOT_COMPUTABLE"
    assert "BOOK_CALIBRATED" not in str(result.model_dump())


def test_bookmaker_fingerprint_minimum_sample_and_field_evidence():
    small = bookmaker_fingerprint("book-a", [{"bookmaker": "book-a", "probability": 0.6, "outcome": 1}], minimum_sample=2)
    assert small.status == "NOT_COMPUTABLE"
    assert small.reason == "minimum provenance-complete sample not met"

    rows = []
    for i in range(20):
        rows.append({
            "bookmaker": "book-a",
            "probability": 0.6,
            "outcome": 1 if i % 2 == 0 else 0,
            "overround": 0.04,
            "stale_seconds": 600 if i % 4 == 0 else 10,
            "source": "fixture",
            "source_hash": f"row-{i}",
        })
    fp = bookmaker_fingerprint("book-a", rows, minimum_sample=20)
    assert fp.status == "COMPUTED"
    assert fp.sample_size == 20
    assert fp.brier is not None and fp.log_loss is not None and fp.ece is not None
    assert fp.hold == 0.04
    assert abs(fp.stale_rate - 0.25) < 1e-12
    assert fp.fields["bias"] == "COMPUTED"
    assert fp.field_sample_sizes["brier"] == 20
    assert fp.source_provenance[0]["source_hash"] == "row-0"

    no_metrics = bookmaker_fingerprint(
        "book-a",
        [
            {
                "bookmaker": "book-a",
                "source": "fixture",
                "source_hash": f"empty-{i}",
            }
            for i in range(20)
        ],
        minimum_sample=20,
    )
    assert no_metrics.status == "NOT_COMPUTABLE"
    assert no_metrics.fields["brier"] == "NOT_COMPUTABLE"


def test_consensus_rejects_incomparable_selection_sets():
    one_sided = BookmakerQuote(
        bookmaker="broken",
        event_id="event-1",
        market_id="m1",
        market_type="MONEYLINE",
        fetched_at="2026-01-01T10:00:00Z",
        source="fixture",
        source_hash="broken-hash",
        outcomes=(OutcomePrice(selection="HOME", observed_probability=0.80),),
    )
    result = weighted_consensus((_quote("complete"), one_sided))
    assert result.status == "NOT_COMPUTABLE"
    assert result.bookmakers_observed == ["broken", "complete"]
    assert result.effective_book_count is None


def test_fingerprint_fields_each_require_the_minimum_sample():
    rows = [
        {
            "bookmaker": "book-a",
            "source": "fixture",
            "source_hash": f"partial-{i}",
            **({"probability": 0.6, "outcome": 1} if i == 0 else {}),
        }
        for i in range(20)
    ]
    result = bookmaker_fingerprint("book-a", rows, minimum_sample=20)
    assert result.status == "NOT_COMPUTABLE"
    assert result.fields["brier"] == "NOT_COMPUTABLE"
    assert result.field_sample_sizes["brier"] == 1


def test_fingerprint_rejects_invalid_calibration_bins():
    result = bookmaker_fingerprint("book-a", [], minimum_sample=20, ece_bins=0)
    assert result.status == "NOT_COMPUTABLE"
    assert "must be positive" in result.reason
