"""Deterministic three-boundary triage over local evidence."""

from __future__ import annotations

from .config import TriageConfig
from .models import CandidateSet, TriageItem, TriageSet


def triage_candidates(candidates: CandidateSet, config: TriageConfig) -> TriageSet:
    items: list[TriageItem] = []
    for candidate in candidates.candidates:
        if candidate.commentary_only_suppressed:
            route, tier = "drop", "local_gate"
            reasons = ["commentary-only or context-only transcript signal was suppressed"]
        elif (
            candidate.score >= config.keep_score
            and len(candidate.modalities) >= config.minimum_supporting_modalities
        ):
            route, tier = "keep", "cheap_fusion"
            reasons = ["score and independent-modality support crossed the local keep boundary"]
        elif candidate.score <= config.drop_score:
            route, tier = "drop", "cheap_fusion"
            reasons = ["local evidence score stayed below the drop boundary"]
        else:
            route, tier = "human_review", "review_boundary"
            reasons = ["local evidence is plausible but insufficient for automatic routing"]
        items.append(
            TriageItem(
                candidate_id=candidate.candidate_id,
                route=route,
                tier=tier,
                confidence=candidate.score,
                reasons=reasons,
                human_review_required=route != "drop",
            )
        )
    return TriageSet(schema_version="mimir.aegir.triage.v1", items=items)
