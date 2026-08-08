from __future__ import annotations

from .models import ContextResult, PlayerState, bounded_confidence, has_enough_samples, not_computable


def compute_relative_recovery_advantage(player: PlayerState, peer: PlayerState) -> ContextResult:
    """Compare recovery context against a peer/baseline without producing a betting verdict."""
    if not has_enough_samples(player.controlled_sample_size, player.history_sample_size) or not has_enough_samples(peer.controlled_sample_size, peer.history_sample_size):
        return not_computable("relative_recovery_advantage", ["inadequate controlled/history samples"], player.provenance + peer.provenance)
    if player.rest_hours is None or peer.rest_hours is None:
        return not_computable("relative_recovery_advantage", ["missing rest evidence"], player.provenance + peer.provenance)

    minute_penalty = ((player.minutes_last_7d or 0.0) - (peer.minutes_last_7d or 0.0)) / 60.0
    games_penalty = float((player.games_last_7d or 0) - (peer.games_last_7d or 0)) * 0.5
    value = round((player.rest_hours - peer.rest_hours) - minute_penalty - games_penalty, 4)
    sample_size = min(player.controlled_sample_size, player.history_sample_size, peer.controlled_sample_size, peer.history_sample_size)
    return ContextResult(status="COMPUTED", signal="relative_recovery_advantage", value=value, units="context_hours", confidence=bounded_confidence(sample_size, len(player.provenance) + len(peer.provenance), "deterministic_context_v0_6"), provenance=player.provenance + peer.provenance, reasons=[])
