"""Reusable, evidence-grounded highlight and QA foundations."""

from __future__ import annotations

import re

from .models import (
    CandidateSet,
    EvidenceSet,
    GroundedAnswer,
    GroundedDocument,
    GroundedIndex,
    HighlightClip,
    HighlightPlan,
    TriageSet,
)


def build_highlight_plan(
    candidates: CandidateSet, evidence: EvidenceSet, triage: TriageSet
) -> HighlightPlan:
    by_id = {candidate.candidate_id: candidate for candidate in candidates.candidates}
    clips: list[HighlightClip] = []
    for item in triage.items:
        if item.route == "drop":
            continue
        candidate = by_id[item.candidate_id]
        clips.append(
            HighlightClip(
                candidate_id=candidate.candidate_id,
                start_sec=candidate.start_sec,
                end_sec=candidate.end_sec,
                score=candidate.score,
                review_status=(
                    "ready_for_review" if item.route == "keep" else "requires_review"
                ),
                evidence_claim_ids=[
                    claim.claim_id
                    for claim in evidence.claims
                    if claim.candidate_id == candidate.candidate_id
                ],
            )
        )
    return HighlightPlan(
        schema_version="mimir.aegir.highlight-plan.v1",
        render_status="plan_only",
        clips=clips,
        limitations=[
            "This is a reviewable edit decision list, not a rendered or published video.",
            "Replay and aftermath packaging are not implemented.",
        ],
    )


def build_grounded_index(evidence: EvidenceSet) -> GroundedIndex:
    grouped: dict[str, list] = {}
    for claim in evidence.claims:
        grouped.setdefault(claim.candidate_id, []).append(claim)
    return GroundedIndex(
        schema_version="mimir.aegir.grounded-index.v1",
        documents=[
            GroundedDocument(
                document_id=f"document-{index:03d}",
                candidate_id=candidate_id,
                text=" ".join(claim.statement for claim in claims),
                claim_ids=[claim.claim_id for claim in claims],
            )
            for index, (candidate_id, claims) in enumerate(sorted(grouped.items()), start=1)
        ],
    )


def answer_grounded_question(question: str, index: GroundedIndex) -> GroundedAnswer:
    terms = set(re.findall(r"[a-z0-9']+", question.lower())) - {
        "a",
        "an",
        "did",
        "in",
        "is",
        "of",
        "the",
        "there",
        "what",
    }
    ranked = sorted(
        (
            (len(terms & set(re.findall(r"[a-z0-9']+", document.text.lower()))), document)
            for document in index.documents
        ),
        key=lambda item: (-item[0], item[1].document_id),
    )
    if not ranked or ranked[0][0] == 0:
        return GroundedAnswer(
            answer=None,
            citation_ids=[],
            withheld_reason="No indexed evidence overlaps the question.",
        )
    document = ranked[0][1]
    return GroundedAnswer(
        answer=document.text,
        citation_ids=[document.document_id],
        withheld_reason=None,
    )
