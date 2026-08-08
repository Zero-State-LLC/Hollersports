from fastapi.testclient import TestClient

from hollersports.api.app import create_app


def _devig_result(client):
    rows = []
    for row_id, winner in (("one", "HOME"), ("two", "AWAY")):
        rows.append({
            "row_id": row_id, "bookmaker": "book-a", "sport": "NBA",
            "market_class": "NBA/MONEYLINE", "odds_bucket": "EVEN",
            "outcomes": [{"selection": "HOME", "observed_probability": 0.60}, {"selection": "AWAY", "observed_probability": 0.50}],
            "winning_selection": winner, "observed_at": "2026-01-01T20:00:00Z",
            "available_at": "2026-01-02T00:00:00Z", "source": "settlement", "source_hash": f"hash-{row_id}",
        })
    response = client.post("/v1/backtest/devig", json={
        "rows": rows, "bookmaker": "book-a", "sport": "NBA", "market_class": "NBA/MONEYLINE",
        "odds_bucket": "EVEN", "as_of": "2026-01-02T01:00:00Z", "minimum_sample": 2,
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_promotion_registry_apis_are_shadow_only_and_temporal(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        result = _devig_result(client)
        promoted = client.post("/v1/calibration/devig/promote", json={
            "promotion_id": "cal-1", "result": result, "promoted_at": "2026-01-03T00:00:00Z",
        })
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["authority"] == "SHADOW_ONLY"
        before = client.get("/v1/calibration/devig", params={"at_or_before": "2026-01-02T12:00:00Z"}).json()
        after = client.get("/v1/calibration/devig", params={"at_or_before": "2026-01-03T00:00:00Z"}).json()
        assert before["records"] == []
        assert [record["promotion_id"] for record in after["records"]] == ["cal-1"]

        model = client.post("/v1/models/promote", json={
            "record_id": "model-promotion-1", "model_id": "joint-v1", "model_family": "JOINT",
            "sport": "NBA", "market_class": "NBA/PARLAY", "trained_at": "2026-01-01T00:00:00Z",
            "evaluated_at": "2026-01-02T00:00:00Z", "promoted_at": "2026-01-03T00:00:00Z",
            "artifact_hash": "a" * 64, "evidence_hash": "b" * 64, "sample_size": 30,
            "sample_minimum": 20, "metrics": {"joint_log_loss": 0.42},
        })
        assert model.status_code == 200, model.text
        assert model.json()["execution_authority"] is False
        assert client.get("/v1/models", params={"model_family": "JOINT"}).json()["records"][0]["model_id"] == "joint-v1"
        health = client.get("/v1/health/promotions").json()
        assert health["status"] == "PASS"
        assert health["devig_promotion_count"] == 1
        assert health["model_promotion_count"] == 1


def test_assembled_release_readiness_rejects_unbound_gate_scalars(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.post("/v1/release-readiness/assembled", json={
            "base": {
                "devig_sample_size": 100, "raw_implied_brier": 0.5, "fair_probability_brier": 0.1,
                "provenance": {"gate_b": "unbound"},
            },
            "thresholds": {
                "minimum_backtest_sample": 2, "minimum_qualified_fingerprints": 1,
                "maximum_prop_monotonic_violation_rate": 0.0, "maximum_prop_calibration_error": 0.1,
                "minimum_verdict_discrimination": 0.01, "minimum_pass_retained_sample": 2,
            },
        })
        assert response.status_code == 200, response.text
        body = response.json()
        gate_b = next(gate for gate in body["gates"] if gate["gate"] == "B")
        assert gate_b["status"] == "NOT_COMPUTABLE"
        assert body["evidence"]["devig_sample_size"] == 0
        assert "gate_b" not in body["evidence"]["provenance"]
