# Prefer active venv python, else python3 (macOS often has no bare `python`).
PYTHON ?= $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)
export PYTHONPATH := packages/hollersports:$(PYTHONPATH)

.PHONY: validate test test-unit test-integration test-golden test-calibration test-cov \
	install smoke calibration-suite backfill backfill-status v06-backfill-audit api web free-first free-first-day \
	ml-e2e ml-train ml-compete ml-retrain-check ml-doc-model ml-axial-train \
	ml-axial-train-large ml-axial-train-transformer ml-rss-demo field-test

install:
	$(PYTHON) -m pip install -U pip
	$(PYTHON) -m pip install -e "packages/hollersports[dev]"

test:
	$(PYTHON) -m pytest tests/ --ignore=hollersports-core -q

test-unit:
	$(PYTHON) -m pytest tests/unit -q -m "unit or not integration"

test-integration:
	$(PYTHON) -m pytest tests/integration -q

test-golden:
	$(PYTHON) -m pytest tests/golden tests/calibration -q -m "golden or calibration"

test-calibration:
	$(PYTHON) -m pytest tests/unit/test_calibration_evaluator.py tests/unit/test_settlement_history.py tests/calibration -q -m calibration

test-cov:
	$(PYTHON) -m pytest tests/ --ignore=hollersports-core -q \
		--cov=hollersports --cov-report=term-missing \
		--cov-config=packages/hollersports/pyproject.toml

smoke:
	$(PYTHON) scripts/smoke_operator_day.py --out docs/evidence/smoke_operator_day.last.json

calibration-suite:
	$(PYTHON) scripts/run_calibration_suite.py --out docs/evidence/calibration_suite.last.json

# Multi-fixture accumulation into data/backfill (grows calibration sample).
# Hermes: see docs/agents/HERMES_BACKFILL.md — run backfill-status first.
backfill-status:
	$(PYTHON) scripts/backfill_status.py

v06-backfill-audit:
	$(PYTHON) scripts/audit_v06_backfill.py --data-root data --fixtures-root fixtures

backfill:
	$(PYTHON) scripts/backfill_fixtures.py --out docs/evidence/backfill_calibration.last.json
	$(PYTHON) scripts/backfill_status.py

validate: install test smoke calibration-suite
	@echo "validate OK"

api:
	$(PYTHON) -m uvicorn hollersports.api.app:create_app --factory --reload --port 8000

web:
	cd packages/operator-web && npm run dev

# Optional live observation (ESPN free; Odds API if THE_ODDS_API_KEY set). Advisory only.
free-first:
	$(PYTHON) scripts/holler_free_first_ingest.py --out out/free_first_observation.json

# Closed free-first day → compete → paper → ESPN settle → calibration bank.
# Prefer injected JSON for CI; live finals need --fetch-espn-finals (network).
# Example (injected): python scripts/free_first_operator_day.py --espn-raw ... --odds-raw ... --settle-espn-raw ...
FREE_FIRST_LEAGUES ?= NBA
free-first-day:
	$(PYTHON) scripts/free_first_operator_day.py --leagues $(FREE_FIRST_LEAGUES) --fetch-espn-finals \
		--data-root data/backfill --out docs/evidence/free_first_day.last.json

# Track F research ML (offline fixtures; advisory only; no sklearn required).
# Train on day001+day002, apply day003 → docs/evidence/ml_pipeline_e2e.last.json
ml-e2e:
	$(PYTHON) scripts/holler/ml_e2e.py

ml-train:
	$(PYTHON) scripts/holler/train_gbm.py fixtures/day001 fixtures/day002 --out-dir data/ml

# Annotate day003 + strategy competition with explicit model-edge opt-in (offline demo).
ml-compete:
	$(PYTHON) scripts/holler/ml_compete_day.py \
		--fixture-day fixtures/day003 \
		--train-days fixtures/day001 fixtures/day002 \
		--allow-model-edge \
		--out-dir data/ml/compete

# Advisory retrain proposal only (never auto-trains).
ml-retrain-check:
	$(PYTHON) scripts/holler/ml_retrain_check.py

ml-doc-model:
	$(PYTHON) scripts/holler/doc_model.py --ensemble data/ml/ensemble.json

# Requires: pip install -e "packages/hollersports[torch]"
ml-axial-train:
	$(PYTHON) scripts/holler/train_axial.py fixtures/day001 fixtures/day002 fixtures/day003 \
		--out-dir data/ml/axial --arch axial_small

# Track G larger / dist presets (requires [torch])
ml-axial-train-large:
	$(PYTHON) scripts/holler/train_axial.py fixtures/day001 fixtures/day002 fixtures/day003 \
		--out-dir data/ml/axial --arch axial_large \
		--sequences fixtures/sequences/synthetic_totals.json

ml-axial-train-transformer:
	$(PYTHON) scripts/holler/train_axial.py fixtures/day001 fixtures/day002 fixtures/day003 \
		--out-dir data/ml/axial --arch transformer_dist \
		--sequences fixtures/sequences/synthetic_totals.json

# Offline RSS inject example needs a local XML; live uses --fetch
ml-rss-demo:
	$(PYTHON) scripts/holler/fetch_rss_sentiment.py \
		--markets-json fixtures/day003/odds_records.json \
		--out data/ml/rss_sentiment.last.json

# v0.5 field-test freeze receipt (offline; no torch required)
field-test: install smoke ml-e2e
	$(PYTHON) scripts/write_field_test_receipt.py
	@echo "field-test OK → docs/evidence/FIELD_TEST_RECEIPT_v0.5.0.json"
