"""Research ML pipeline: features → train → calibrate → EV annotate (advisory only).

Never grants capital or execution authority. Fail closed when models are missing.
"""

from __future__ import annotations

from hollersports.ml.apply import apply_ensemble_to_markets, apply_ensemble_to_odds_file
from hollersports.ml.calibrate import calibrate_temperature, predict_calibrated
from hollersports.ml.ev import compute_ev
from hollersports.ml.features import (
    FEATURE_NAMES,
    american_to_decimal,
    american_to_implied,
    build_feature_rows,
)
from hollersports.ml.promotion_registry import (
    ModelFamily,
    PromotionRecord,
    RegistryHealth,
    RegistryHealthStatus,
    ShadowPromotionRegistry,
    stable_hash,
)
from hollersports.ml.train import predict_proba, train_baseline

__all__ = [
    "FEATURE_NAMES",
    "ModelFamily",
    "PromotionRecord",
    "RegistryHealth",
    "RegistryHealthStatus",
    "ShadowPromotionRegistry",
    "american_to_decimal",
    "american_to_implied",
    "apply_ensemble_to_markets",
    "apply_ensemble_to_odds_file",
    "build_feature_rows",
    "calibrate_temperature",
    "compute_ev",
    "predict_calibrated",
    "predict_proba",
    "stable_hash",
    "train_baseline",
]
