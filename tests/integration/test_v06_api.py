from fastapi.testclient import TestClient

from hollersports.api.app import create_app


QUOTE = {
    "bookmaker": "book-a",
    "event_id": "event-1",
    "market_id": "market-1",
    "market_type": "MONEYLINE",
    "fetched_at": "2026-01-01T10:00:00Z",
    "source": "fixture",
    "outcomes": [
        {"selection": "HOME", "american_odds": -110},
        {"selection": "AWAY", "american_odds": -110},
    ],
}


def test_v06_market_memory_and_temporal_api(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        body = {
            "snapshot_id": "snap-1",
            "captured_at": "2026-01-01T10:00:00Z",
            "event_id": "event-1",
            "market_type": "MONEYLINE",
            "quotes": [QUOTE],
        }
        recorded = client.post("/v1/markets/snapshots", json=body)
        assert recorded.status_code == 200, recorded.text
        assert recorded.json()["capital_authority"] is False
        timeline = client.get("/v1/markets/market-1/timeline")
        assert timeline.status_code == 200
        assert [row["snapshot_id"] for row in timeline.json()["observations"]] == ["snap-1"]
        books = client.get("/v1/books").json()
        assert books["books"] == ["book-a"]


def test_v06_single_reconstructs_fair_probability(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.post("/v1/analyze/single", json={"quote": QUOTE})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "COMPUTED"
        assert body["fair_probability"]["method"] == "MULTIPLICATIVE"
        assert abs(sum(body["fair_probability"]["values"].values()) - 1.0) < 1e-12
        assert body["execution_authority"] is False


def test_v06_parlay_unknown_dependency_is_not_computable(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.post(
            "/v1/parlay/xray",
            json={
                "legs": [
                    {"leg_id": "a", "marginal_probability": 0.6},
                    {"leg_id": "b", "marginal_probability": 0.5},
                ]
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "NOT_COMPUTABLE"
        assert body["joint"]["joint_probability"] is None


def test_v06_prop_surface_repairs_inversion(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.post(
            "/v1/props/surface",
            json={
                "event_id": "event-1",
                "market": "POINTS",
                "player": "player-1",
                "thresholds": [
                    {"threshold": 20, "fair_probability": 0.60},
                    {"threshold": 25, "fair_probability": 0.64},
                    {"threshold": 30, "fair_probability": 0.30},
                ],
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        probabilities = [row["survival_probability"] for row in body["surface"]["points"]]
        assert probabilities == sorted(probabilities, reverse=True)
        assert body["surface"]["weak_fit"] is True
