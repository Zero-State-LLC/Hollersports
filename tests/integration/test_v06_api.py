from fastapi.testclient import TestClient

from hollersports.api.app import create_app


QUOTE = {
    "bookmaker": "book-a",
    "event_id": "event-1",
    "market_id": "market-1",
    "market_type": "MONEYLINE",
    "fetched_at": "2026-01-01T10:00:00Z",
    "source": "fixture",
    "source_hash": "fixture-sha256",
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
        duplicate = client.post("/v1/markets/snapshots", json=body)
        assert duplicate.status_code == 409
        timeline = client.get("/v1/markets/market-1/timeline")
        assert timeline.status_code == 200
        assert [row["snapshot_id"] for row in timeline.json()["observations"]] == ["snap-1"]
        books = client.get("/v1/books").json()
        assert books["books"] == ["book-a"]
        invalid_time = client.get(
            "/v1/markets/market-1/timeline", params={"at_or_before": "not-a-time"}
        )
        assert invalid_time.status_code == 422


def test_v06_single_reconstructs_fair_probability(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.post("/v1/analyze/single", json={"quote": QUOTE})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "COMPUTED"
        assert body["fair_probability"]["method"] == "MULTIPLICATIVE"
        assert abs(sum(body["fair_probability"]["values"].values()) - 1.0) < 1e-12
        assert body["execution_authority"] is False

        additive = client.post(
            "/v1/analyze/single",
            json={"quote": QUOTE, "devig_method": "ADDITIVE"},
        )
        assert additive.status_code == 200
        assert additive.json()["fair_probability"]["method"] == "ADDITIVE"

        unsupported = client.post(
            "/v1/analyze/single",
            json={"quote": QUOTE, "devig_method": "BOOK_CALIBRATED"},
        )
        assert unsupported.status_code == 200
        assert unsupported.json()["status"] == "NOT_COMPUTABLE"


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


def test_v06_prop_observation_persistence_and_temporal_replay(tmp_path):
    observation = {
        "observation_id": "prop-obs-1", "market_id": "prop-market-1", "book_id": "book-a",
        "event_id": "event-1", "player_id": "player-1", "stat_type": "points",
        "observed_at": "2026-01-01T10:00:00Z", "source": "fixture", "source_hash": "prop-source-hash",
        "ladder": {"event_id": "event-1", "market": "PLAYER_POINTS", "player": "player-1", "thresholds": [
            {"threshold": 20, "fair_probability": 0.60, "source": "fixture"},
            {"threshold": 25, "fair_probability": 0.45, "source": "fixture"},
            {"threshold": 30, "fair_probability": 0.30, "source": "fixture"},
        ]},
    }
    with TestClient(create_app(data_root=tmp_path)) as client:
        recorded = client.post("/v1/props/observations", json={"observation": observation, "surface_id": "surface-1", "derived_at": "2026-01-01T10:01:00Z"})
        assert recorded.status_code == 200, recorded.text
        assert recorded.json()["capital_authority"] is False
        assert client.post("/v1/props/observations", json={"observation": observation, "surface_id": "surface-2", "derived_at": "2026-01-01T10:02:00Z"}).status_code == 409

        before_derivation = client.get("/v1/props/prop-market-1", params={"at_or_before": "2026-01-01T10:00:30Z"}).json()
        assert before_derivation["status"] == "NOT_COMPUTABLE"
        assert before_derivation["ladder"]["source_hash"] == "prop-source-hash"
        replay = client.get("/v1/props/prop-market-1", params={"at_or_before": "2026-01-01T10:01:00Z"}).json()
        assert replay["status"] == "COMPUTED"
        assert replay["surface"]["ladder_fingerprint"] == replay["ladder_fingerprint"]


def test_v06_fingerprint_and_backtest_require_evidence(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        fingerprint = client.post(
            "/v1/books/book-a/fingerprint/compute",
            json={
                "minimum_sample": 2,
                "rows": [
                    {
                        "bookmaker": "book-a",
                        "probability": 0.6,
                        "outcome": 1,
                        "source": "fixture",
                        "source_hash": "row-1",
                    }
                ],
            },
        )
        assert fingerprint.status_code == 200
        assert fingerprint.json()["status"] == "NOT_COMPUTABLE"

        backtest = client.post(
            "/v1/backtest/bookmaker",
            json={
                "minimum_sample": 2,
                "rows": [
                    {
                        "row_id": "row-1",
                        "event_id": "event-1",
                        "market_type": "MONEYLINE",
                        "selection": "HOME",
                        "source": "fixture",
                        "source_hash": "backtest-row-1",
                        "predicted_probability": 0.6,
                        "prediction_at": "2026-01-01T10:00:00Z",
                    }
                ],
            },
        )
        assert backtest.status_code == 200
        body = backtest.json()
        assert body["status"] == "NOT_COMPUTABLE"
        assert all(metric["status"] == "NOT_COMPUTABLE" for metric in body["metrics"])
        assert body["capital_authority"] is False


def test_v06_context_persistence_temporal_replay_and_evidence_separation(tmp_path):
    observation = {
        "observation_id": "context-1", "event_id": "event-1", "entity_id": "team-a",
        "context_type": "TRAVEL", "observed_at": "2026-01-01T10:00:00Z",
        "recorded_at": "2026-01-01T10:00:30Z",
        "source": "fixture", "source_hash": "context-source-hash",
        "payload": {
            "team_id": "team-a", "miles_last_72h": 1200, "timezone_delta_hours": 2,
            "rest_hours": 28, "controlled_sample_size": 5, "history_sample_size": 10,
            "provenance": [{"source": "fixture", "observed_at": "2026-01-01T10:00:00Z"}],
        },
    }
    with TestClient(create_app(data_root=tmp_path)) as client:
        recorded = client.post("/v1/context/observations", json={"observation": observation, "derivation_id": "context-derived-1", "derived_at": "2026-01-01T10:05:00Z"})
        assert recorded.status_code == 200, recorded.text
        assert recorded.json()["status"] == "COMPUTED"
        assert recorded.json()["execution_authority"] is False

        early = client.get("/v1/context/event-1/team-a/TRAVEL", params={"at_or_before": "2026-01-01T10:02:00Z"}).json()
        assert early["status"] == "NOT_COMPUTABLE"
        assert early["evidence"]["context"]["source_hash"] == "context-source-hash"
        replay = client.get("/v1/context/event-1/team-a/TRAVEL", params={"at_or_before": "2026-01-01T10:05:00Z"}).json()
        assert replay["status"] == "COMPUTED"
        assert replay["evidence"]["bookmaker"] is None
        assert replay["evidence"]["dependency"] is None
        health = client.get("/v1/health/context").json()
        assert health["status"] == "PASS"
        assert health["recorded_at_gate"] is True
        assert health["integrity_issues"] == []

        derivations_path = tmp_path / "context" / "derivations" / "derivations.jsonl"
        row = derivations_path.read_text(encoding="utf-8").replace(
            recorded.json()["observation_fingerprint"], "0" * 64
        )
        derivations_path.write_text(row, encoding="utf-8")
        tampered = client.get("/v1/health/context").json()
        assert tampered["status"] == "NOT_COMPUTABLE"
        assert any("fingerprint mismatch" in issue for issue in tampered["integrity_issues"])


def test_v06_recovery_requires_explicit_peer_and_fails_closed_without_samples(tmp_path):
    player = {"player_id": "player-a", "rest_hours": 48, "controlled_sample_size": 0, "history_sample_size": 0}
    peer = {"player_id": "player-b", "rest_hours": 24, "controlled_sample_size": 0, "history_sample_size": 0}
    with TestClient(create_app(data_root=tmp_path)) as client:
        result = client.post("/v1/context/recovery", json={"player": player, "peer": peer})
        assert result.status_code == 200
        assert result.json()["status"] == "NOT_COMPUTABLE"
        assert result.json()["capital_authority"] is False


def test_v06_dependency_persistence_replay_and_health(tmp_path):
    observation = {
        "observation_id": "dependency-1", "event_id": "event-1", "parlay_id": "parlay-1",
        "observed_at": "2026-01-01T10:00:00Z", "recorded_at": "2026-01-01T10:01:00Z",
        "source": "fixture", "source_hash": "dependency-source-hash",
        "legs": [{"leg_id": "a", "marginal_probability": 0.6}, {"leg_id": "b", "marginal_probability": 0.5}],
        "method": "INDEPENDENT_EXPLICITLY_ALLOWED", "explicitly_allow_independence": True,
    }
    with TestClient(create_app(data_root=tmp_path)) as client:
        recorded = client.post("/v1/dependency/observations", json={"observation": observation, "analysis_id": "analysis-1", "analyzed_at": "2026-01-01T10:05:00Z"})
        assert recorded.status_code == 200, recorded.text
        assert recorded.json()["status"] == "COMPUTABLE"
        assert recorded.json()["execution_authority"] is False

        early = client.get("/v1/dependency/event-1/parlay-1", params={"at_or_before": "2026-01-01T10:03:00Z"}).json()
        assert early["status"] == "NOT_COMPUTABLE"
        assert early["evidence"]["dependency"]["source_hash"] == "dependency-source-hash"
        replay = client.get("/v1/dependency/event-1/parlay-1", params={"at_or_before": "2026-01-01T10:05:00Z"}).json()
        assert replay["status"] == "COMPUTABLE"
        assert replay["analysis"]["analysis"]["joint"]["joint_probability"] == 0.3
        assert replay["evidence"]["market"] is None

        health = client.get("/v1/health/dependency").json()
        assert health["status"] == "PASS"
        assert health["integrity_issues"] == []


def test_v06_structural_persistence_and_release_readiness(tmp_path):
    thresholds = {
        "minimum_data_quality": 0.7, "maximum_market_entropy": 0.4,
        "minimum_dependency_confidence": 0.6, "edge_probability_points": 0.03,
        "conflict_probability_points": 0.08, "fair_pricing_tolerance": 0.015,
    }
    observation = {
        "observation_id": "struct-1", "subject_id": "market-1", "subject_type": "SINGLE",
        "observed_at": "2026-01-01T10:00:00Z", "recorded_at": "2026-01-01T10:01:00Z",
        "source": "fixture", "source_hash": "struct-source", "threshold_source_id": "cal-1",
        "threshold_source_hash": "cal-hash", "book_probability": 0.59,
        "consensus_probability": 0.52, "reality_probability": 0.51,
        "data_quality": 0.9, "market_entropy": 0.1, "thresholds": thresholds,
        "evidence_references": {"bookmaker": "book-1", "market": "market-1", "context": "context-1", "player": "player-1"},
    }
    gate_thresholds = {
        "minimum_backtest_sample": 20, "minimum_qualified_fingerprints": 2,
        "maximum_prop_monotonic_violation_rate": 0.0, "maximum_prop_calibration_error": 0.05,
        "minimum_verdict_discrimination": 0.1, "minimum_pass_retained_sample": 10,
    }
    with TestClient(create_app(data_root=tmp_path)) as client:
        stored = client.post("/v1/structural/observations", json={"observation": observation, "analysis_id": "analysis-1", "analyzed_at": "2026-01-01T10:02:00Z"})
        assert stored.status_code == 200, stored.text
        assert stored.json()["status"] == "RETAIL_PRICED"
        replay = client.get("/v1/structural/market-1", params={"at_or_before": "2026-01-01T10:02:00Z"}).json()
        assert replay["analysis"]["verdict_packet"]["verdict"] == "RETAIL_PRICED"
        assert set(replay["evidence_references"]) == {"bookmaker", "market", "context", "player"}

        readiness = client.post("/v1/release-readiness", json={"evidence": {}, "thresholds": gate_thresholds})
        assert readiness.status_code == 200
        assert readiness.json()["status"] == "NOT_READY"
        assert all(gate["status"] == "NOT_COMPUTABLE" for gate in readiness.json()["gates"])
        health = client.get("/v1/health/structural").json()
        assert health["status"] == "PASS"
