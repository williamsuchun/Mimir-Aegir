"""Strict schemas shared by all pipeline stages."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ArtifactRef(StrictModel):
    stage: str
    path: str
    schema_version: str


class SourceRef(StrictModel):
    artifact: str
    timestamp_sec: float | None = None
    frame_index: int | None = None
    cue_id: str | None = None


class MediaManifest(StrictModel):
    schema_version: Literal["mimir.aegir.manifest.v1"]
    source_file: str
    duration_sec: float
    fps: float
    frame_count: int
    width: int
    height: int
    audio_source: str | None
    transcript_source: str | None
    assumptions: list[str]


class VideoSignal(StrictModel):
    timestamp_sec: float
    frame_index: int
    motion: float = Field(ge=0.0, le=1.0)
    brightness: float = Field(ge=0.0, le=1.0)
    sharpness: float = Field(ge=0.0)


class VideoSignals(StrictModel):
    schema_version: Literal["mimir.aegir.video-signals.v1"]
    sample_interval_sec: float
    samples: list[VideoSignal]


class AudioSignal(StrictModel):
    start_sec: float
    end_sec: float
    rms: float = Field(ge=0.0, le=1.0)
    peak: float = Field(ge=0.0, le=1.0)
    zero_crossing_rate: float = Field(ge=0.0, le=1.0)


class AudioSignals(StrictModel):
    schema_version: Literal["mimir.aegir.audio-signals.v1"]
    available: bool
    reason: str | None
    source_file: str | None
    sample_rate_hz: int | None
    windows: list[AudioSignal]


class TranscriptCue(StrictModel):
    cue_id: str
    start_sec: float
    end_sec: float
    text: str
    event_terms: list[str]
    context_terms: list[str]
    commentary_terms: list[str]


class TranscriptSignals(StrictModel):
    schema_version: Literal["mimir.aegir.transcript-signals.v1"]
    available: bool
    reason: str | None
    source_file: str | None
    cues: list[TranscriptCue]


class Candidate(StrictModel):
    candidate_id: str
    start_sec: float
    end_sec: float
    anchor_sec: float
    score: float = Field(ge=0.0, le=1.0)
    modalities: list[Literal["video", "audio", "transcript"]]
    reasons: list[str]
    context: list[str]
    commentary_only_suppressed: bool
    source_refs: list[SourceRef]


class CandidateSet(StrictModel):
    schema_version: Literal["mimir.aegir.candidates.v1"]
    strategy: Literal["recall_first_event_chains"]
    candidates: list[Candidate]


class EvidenceClaim(StrictModel):
    claim_id: str
    candidate_id: str
    kind: Literal["visual_signal", "audio_signal", "transcript_cue", "context"]
    statement: str
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_basis: str
    provenance: list[SourceRef]
    human_review_required: bool


class EvidenceSet(StrictModel):
    schema_version: Literal["mimir.aegir.evidence.v1"]
    claims: list[EvidenceClaim]


class TriageItem(StrictModel):
    candidate_id: str
    route: Literal["drop", "keep", "human_review"]
    tier: Literal["local_gate", "cheap_fusion", "review_boundary"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str]
    human_review_required: bool


class TriageSet(StrictModel):
    schema_version: Literal["mimir.aegir.triage.v1"]
    items: list[TriageItem]


class HighlightClip(StrictModel):
    candidate_id: str
    start_sec: float
    end_sec: float
    score: float
    review_status: Literal["ready_for_review", "requires_review"]
    evidence_claim_ids: list[str]


class HighlightPlan(StrictModel):
    schema_version: Literal["mimir.aegir.highlight-plan.v1"]
    render_status: Literal["plan_only"]
    clips: list[HighlightClip]
    limitations: list[str]


class GroundedDocument(StrictModel):
    document_id: str
    candidate_id: str
    text: str
    claim_ids: list[str]


class GroundedIndex(StrictModel):
    schema_version: Literal["mimir.aegir.grounded-index.v1"]
    documents: list[GroundedDocument]


class GroundedAnswer(StrictModel):
    answer: str | None
    citation_ids: list[str]
    withheld_reason: str | None

    @model_validator(mode="after")
    def require_citations_or_withholding(self) -> "GroundedAnswer":
        if self.answer and not self.citation_ids:
            raise ValueError("an answer must cite at least one indexed document")
        if not self.answer and not self.withheld_reason:
            raise ValueError("a withheld answer requires a reason")
        return self


class PipelineResult(StrictModel):
    schema_version: Literal["mimir.aegir.result.v1"]
    run_status: Literal["completed"]
    source_file: str
    candidate_count: int
    kept_count: int
    review_count: int
    dropped_count: int
    artifacts: list[ArtifactRef]
    limitations: list[str]
