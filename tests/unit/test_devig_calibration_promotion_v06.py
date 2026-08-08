from datetime import datetime, timezone
import json

import pytest

from hollersports.bookmaker import DevigCalibrationPromotionRecord, DevigCalibrationPromotionStore
from hollersports.bookmaker.fingerprint import stable_fingerprint
from tests.unit.test_devig_calibration_v06 import compare, row


PROMOTED_AT = datetime(2026, 1, 2, 2, tzinfo=timezone.utc)


def computed_result():
    result = compare([row("one", "HOME"), row("two", "AWAY")])
    assert result.status == "COMPUTED"
    assert result.preferred_method is not None
    assert result.improvement_over_raw_brier is not None and result.improvement_over_raw_brier > 0
    return result


def test_devig_calibration_promotion_appends_evidence_bound_shadow_only_record(tmp_path):
    store = DevigCalibrationPromotionStore(tmp_path)
    result = computed_result()

    record = store.append(promotion_id="promo-1", result=result, promoted_at=PROMOTED_AT)

    assert record.schema_version == "DevigCalibrationPromotion.v1"
    assert record.preferred_method == result.preferred_method
    assert record.improvement_over_raw_brier == result.improvement_over_raw_brier
    assert record.source_result_fingerprint == stable_fingerprint(result.model_dump(mode="json"))
    assert record.packet_fingerprint == stable_fingerprint(record.fingerprint_payload())
    assert record.authority == "SHADOW_ONLY"
    assert record.capital_authority is False
    assert record.execution_authority is False
    assert store.records() == [record]
    assert store.integrity_issues() == []


def test_devig_calibration_promotion_rejects_non_improving_or_unpreferred_result(tmp_path):
    store = DevigCalibrationPromotionStore(tmp_path)
    result = computed_result().model_copy(update={"preferred_method": None, "improvement_over_raw_brier": 0.0})

    with pytest.raises(ValueError, match="requires a preferred method|positive Brier improvement"):
        store.append(promotion_id="promo-1", result=result, promoted_at=PROMOTED_AT)


def test_devig_calibration_promotion_rejects_temporal_regression(tmp_path):
    store = DevigCalibrationPromotionStore(tmp_path)
    with pytest.raises(ValueError, match="promoted_at cannot precede as_of"):
        store.append(
            promotion_id="promo-1",
            result=computed_result(),
            promoted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_devig_calibration_promotion_is_append_only_and_result_fingerprint_unique(tmp_path):
    store = DevigCalibrationPromotionStore(tmp_path)
    result = computed_result()
    store.append(promotion_id="promo-1", result=result, promoted_at=PROMOTED_AT)

    with pytest.raises(ValueError, match="duplicate promotion_id"):
        store.append(promotion_id="promo-1", result=result, promoted_at=PROMOTED_AT)
    with pytest.raises(ValueError, match="duplicate source_result_fingerprint"):
        store.append(promotion_id="promo-2", result=result, promoted_at=PROMOTED_AT)


def test_devig_calibration_promotion_detects_tampered_packet(tmp_path):
    store = DevigCalibrationPromotionStore(tmp_path)
    record = store.append(promotion_id="promo-1", result=computed_result(), promoted_at=PROMOTED_AT)
    payload = record.model_dump(mode="json")
    payload["preferred_method"] = "TAMPERED"
    store.path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    assert "source result preferred_method must match promotion preferred_method" in store.integrity_issues()[0]


def test_devig_calibration_promotion_record_rejects_mutated_source_fingerprint():
    result = computed_result()
    with pytest.raises(ValueError, match="source result fingerprint mismatch"):
        DevigCalibrationPromotionRecord(
            promotion_id="promo-1",
            bookmaker=result.bookmaker,
            sport=result.sport,
            market_class=result.market_class,
            odds_bucket=result.odds_bucket,
            preferred_method=result.preferred_method,
            as_of=result.as_of,
            promoted_at=PROMOTED_AT,
            minimum_sample=result.minimum_sample,
            improvement_over_raw_brier=result.improvement_over_raw_brier,
            source_result_fingerprint="not-the-result-fingerprint",
            result=result,
            packet_fingerprint="pending",
        )
