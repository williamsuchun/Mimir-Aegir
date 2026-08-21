"""Recall-first candidate generation and event-chain consolidation."""

from __future__ import annotations

from dataclasses import dataclass

from .config import CandidateConfig
from .models import (
    AudioSignals,
    Candidate,
    CandidateSet,
    SourceRef,
    TranscriptCue,
    TranscriptSignals,
    VideoSignal,
    VideoSignals,
)


@dataclass(frozen=True)
class _Seed:
    time: float
    score: float
    modalities: tuple[str, ...]
    reasons: tuple[str, ...]
    context: tuple[str, ...]
    commentary_only: bool
    refs: tuple[SourceRef, ...]


def _audio_at(audio: AudioSignals, time: float) -> float:
    for window in audio.windows:
        if window.start_sec <= time < window.end_sec:
            return window.rms
    return 0.0


def _cues_at(transcript: TranscriptSignals, time: float) -> list[TranscriptCue]:
    return [cue for cue in transcript.cues if cue.start_sec <= time <= cue.end_sec]


def _unique_refs(refs: list[SourceRef]) -> list[SourceRef]:
    unique: dict[str, SourceRef] = {}
    for ref in refs:
        unique.setdefault(ref.model_dump_json(), ref)
    return list(unique.values())


def generate_candidates(
    video: VideoSignals,
    audio: AudioSignals,
    transcript: TranscriptSignals,
    duration_sec: float,
    config: CandidateConfig,
) -> CandidateSet:
    seeds: list[_Seed] = []
    for sample in video.samples:
        cues = _cues_at(transcript, sample.timestamp_sec)
        audio_rms = _audio_at(audio, sample.timestamp_sec)
        video_strength = min(1.0, sample.motion / 0.12)
        audio_strength = min(1.0, audio_rms / 0.35)
        event_terms = sorted({term for cue in cues for term in cue.event_terms})
        context = sorted({term for cue in cues for term in cue.context_terms})
        commentary = sorted({term for cue in cues for term in cue.commentary_terms})
        transcript_strength = min(1.0, len(event_terms) * 0.45)
        score = min(
            1.0,
            video_strength * 0.50 + audio_strength * 0.30 + transcript_strength * 0.20,
        )
        modalities: list[str] = []
        reasons: list[str] = []
        refs = [
            SourceRef(
                artifact="signals/video.json",
                timestamp_sec=sample.timestamp_sec,
                frame_index=sample.frame_index,
            )
        ]
        if video_strength >= 0.08:
            modalities.append("video")
            reasons.append("local motion change")
        if audio_strength >= 0.08:
            modalities.append("audio")
            reasons.append("local audio energy")
            refs.append(
                SourceRef(artifact="signals/audio.json", timestamp_sec=sample.timestamp_sec)
            )
        if event_terms:
            modalities.append("transcript")
            reasons.append(f"transcript event terms: {', '.join(event_terms)}")
        if event_terms or context:
            refs.extend(
                SourceRef(
                    artifact="signals/transcript.json",
                    timestamp_sec=cue.start_sec,
                    cue_id=cue.cue_id,
                )
                for cue in cues
                if cue.event_terms or cue.context_terms
            )
        commentary_only = bool(event_terms or context) and video_strength < 0.08 and audio_strength < 0.08
        if commentary and commentary_only:
            reasons.append("transcript-only commentary lacked non-text support")
        if context and not event_terms:
            reasons.append("context terms do not independently trigger a candidate")
        if score >= config.minimum_score or commentary_only:
            seeds.append(
                _Seed(
                    time=sample.timestamp_sec,
                    score=score,
                    modalities=tuple(dict.fromkeys(modalities)),
                    reasons=tuple(reasons),
                    context=tuple(context),
                    commentary_only=commentary_only,
                    refs=tuple(refs),
                )
            )

    half = config.window_sec / 2.0
    chains: list[list[_Seed]] = []
    for seed in seeds:
        if chains and seed.time - chains[-1][-1].time <= config.chain_gap_sec:
            chains[-1].append(seed)
        else:
            chains.append([seed])
    candidates: list[Candidate] = []
    for chain in chains:
        anchor = max(chain, key=lambda item: item.score)
        start = max(0.0, chain[0].time - half)
        end = min(duration_sec, chain[-1].time + half)
        suppressed = all(item.commentary_only for item in chain)
        candidates.append(
            Candidate(
                candidate_id=f"candidate-{len(candidates) + 1:03d}",
                start_sec=round(start, 6),
                end_sec=round(end, 6),
                anchor_sec=round(anchor.time, 6),
                score=round(max(item.score for item in chain), 6),
                modalities=sorted({mode for item in chain for mode in item.modalities}),
                reasons=sorted({reason for item in chain for reason in item.reasons}),
                context=sorted({term for item in chain for term in item.context}),
                commentary_only_suppressed=suppressed,
                source_refs=_unique_refs([ref for item in chain for ref in item.refs]),
            )
        )
    candidates.sort(key=lambda item: (-item.score, item.start_sec))
    candidates = candidates[: config.maximum_candidates]
    for index, candidate in enumerate(candidates, start=1):
        candidate.candidate_id = f"candidate-{index:03d}"
    return CandidateSet(
        schema_version="mimir.aegir.candidates.v1",
        strategy="recall_first_event_chains",
        candidates=candidates,
    )
