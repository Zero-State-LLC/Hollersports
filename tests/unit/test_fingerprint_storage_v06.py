from datetime import datetime, timezone

import pytest

from hollersports.bookmaker import FingerprintStore
from hollersports.bookmaker.fingerprint import bookmaker_fingerprint


AS_OF = datetime(2026, 1, 2, tzinfo=timezone.utc)
COMPUTED_AT = datetime(2026, 1, 2, 0, 1, tzinfo=timezone.utc)


def rows():
    return [
        {"bookmaker": "book-a", "probability": 0.6, "outcome": 1, "hold": 0.04, "source": "settlement", "source_hash": "a", "available_at": "2026-01-01T20:00:00Z"},
        {"bookmaker": "book-a", "probability": 0.4, "outcome": 0, "hold": 0.05, "source": "settlement", "source_hash": "b", "available_at": "2026-01-01T21:00:00Z"},
    ]


def promote(store, fingerprint_id="fp-1", evidence=None):
    evidence = rows() if evidence is None else evidence
    result = bookmaker_fingerprint("book-a", evidence, minimum_sample=2)
    return store.append(
        fingerprint_id=fingerprint_id,
        bookmaker="book-a",
        market_class="NBA/PLAYER_PROP/POINTS",
        as_of=AS_OF,
        computed_at=COMPUTED_AT,
        fingerprint=result,
        evidence_rows=evidence,
    )


def test_fingerprint_promotion_is_append_only_temporal_and_integrity_checked(tmp_path):
    store = FingerprintStore(tmp_path)
    record = promote(store)
    assert record.fingerprint.status == "COMPUTED"
    assert len(record.evidence_fingerprints) == 2
    assert store.query(bookmaker="book-a", at_or_before=datetime(2026, 1, 1, tzinfo=timezone.utc)) == []
    assert store.query(bookmaker="book-a", at_or_before=COMPUTED_AT) == [record]
    with pytest.raises(ValueError, match="duplicate fingerprint_id"):
        promote(store)
    raw = store.path.read_text(encoding="utf-8").replace(record.packet_fingerprint, "0" * 64)
    store.path.write_text(raw, encoding="utf-8")
    assert store.integrity_issues() == ["packet fingerprint mismatch: fp-1"]


def test_fingerprint_promotion_rejects_future_and_duplicate_evidence(tmp_path):
    store = FingerprintStore(tmp_path)
    future = rows()
    future[1] = {**future[1], "available_at": "2026-01-03T00:00:00Z"}
    with pytest.raises(ValueError, match="postdate"):
        promote(store, evidence=future)
    duplicate = [rows()[0], rows()[0]]
    result = bookmaker_fingerprint("book-a", duplicate, minimum_sample=2)
    with pytest.raises(ValueError, match="duplicate fingerprint evidence"):
        store.append(
            fingerprint_id="fp-2", bookmaker="book-a", market_class="NBA/PLAYER_PROP/POINTS",
            as_of=AS_OF, computed_at=COMPUTED_AT, fingerprint=result, evidence_rows=duplicate,
        )


def test_not_computable_fingerprint_cannot_be_promoted(tmp_path):
    evidence = rows()[:1]
    result = bookmaker_fingerprint("book-a", evidence, minimum_sample=2)
    with pytest.raises(ValueError, match="only COMPUTED"):
        FingerprintStore(tmp_path).append(
            fingerprint_id="fp-3", bookmaker="book-a", market_class="NBA/PLAYER_PROP/POINTS",
            as_of=AS_OF, computed_at=COMPUTED_AT, fingerprint=result, evidence_rows=evidence,
        )
