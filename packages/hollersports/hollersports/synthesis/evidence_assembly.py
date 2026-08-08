from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hollersports.bookmaker.devig_calibration import DevigCalibrationResult
from hollersports.dependency.backtest import JointBacktestResult
from hollersports.props.backtest import PropSurfaceBacktestResult
from hollersports.schemas.hashing import packet_hash

from .models import ReleaseGateEvidence


class ReleaseEvidenceAssembly(BaseModel):
    """Evidence packet with metric-bearing gates bound to validated backtests."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "V06ReleaseEvidenceAssembly.v1"
    evidence: ReleaseGateEvidence
    packet_fingerprints: dict[str, str]
    authority: str = "SHADOW_ONLY"
    mode: str = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False


def assemble_release_gate_evidence(
    base: ReleaseGateEvidence,
    *,
    devig: DevigCalibrationResult | None = None,
    props: PropSurfaceBacktestResult | None = None,
    joint: JointBacktestResult | None = None,
) -> ReleaseEvidenceAssembly:
    """Bind Gates B, D, and E to immutable validated backtest packets.

    Operational evidence for A, C, F, G, and H remains in ``base``. Any caller
    supplied values or provenance for B, D, and E are discarded so those gates
    cannot be made computable by unbound scalar metrics.
    """

    update: dict[str, object] = {
        "devig_sample_size": 0,
        "raw_implied_brier": None,
        "fair_probability_brier": None,
        "prop_sample_size": 0,
        "prop_monotonic_violation_rate": None,
        "prop_calibration_error": None,
        "joint_sample_size": 0,
        "independent_joint_log_loss": None,
        "modeled_joint_log_loss": None,
    }
    provenance = {key: value for key, value in base.provenance.items() if key not in {"gate_b", "gate_d", "gate_e"}}
    fingerprints: dict[str, str] = {}

    if devig is not None:
        digest = packet_hash(devig.model_dump(mode="json"))
        fingerprints["devig"] = digest
        if (
            devig.status == "COMPUTED"
            and devig.preferred_method is not None
            and devig.raw_implied.status == "COMPUTED"
        ):
            preferred = next((metric for metric in devig.methods if metric.method == devig.preferred_method), None)
            if preferred is not None and preferred.status == "COMPUTED":
                update.update(
                    devig_sample_size=min(devig.raw_implied.sample_size, preferred.sample_size),
                    raw_implied_brier=devig.raw_implied.brier,
                    fair_probability_brier=preferred.brier,
                )
                provenance["gate_b"] = f"DevigCalibrationComparison.v1:sha256:{digest}"

    if props is not None:
        digest = packet_hash(props.model_dump(mode="json"))
        fingerprints["props"] = digest
        if props.status == "COMPUTED" and props.monotonic_violation_rate.status == "COMPUTED" and props.calibration_error.status == "COMPUTED":
            update.update(
                prop_sample_size=props.row_count,
                prop_monotonic_violation_rate=props.monotonic_violation_rate.value,
                prop_calibration_error=props.calibration_error.value,
            )
            provenance["gate_d"] = f"PropSurfaceBacktest.v1:sha256:{digest}"

    if joint is not None:
        digest = packet_hash(joint.model_dump(mode="json"))
        fingerprints["joint"] = digest
        if joint.status == "COMPUTED" and joint.independent_log_loss.status == "COMPUTED" and joint.modeled_log_loss.status == "COMPUTED":
            update.update(
                joint_sample_size=min(joint.independent_log_loss.sample_size, joint.modeled_log_loss.sample_size),
                independent_joint_log_loss=joint.independent_log_loss.value,
                modeled_joint_log_loss=joint.modeled_log_loss.value,
            )
            provenance["gate_e"] = f"JointProbabilityBacktest.v1:sha256:{digest}"

    update["provenance"] = provenance
    return ReleaseEvidenceAssembly(evidence=base.model_copy(update=update), packet_fingerprints=fingerprints)
