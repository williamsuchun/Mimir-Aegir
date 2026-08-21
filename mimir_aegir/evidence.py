"""Evidence extraction with explicit provenance and review boundaries."""

from __future__ import annotations

import math
from pathlib import Path

import cv2

from .models import CandidateSet, EvidenceClaim, EvidenceSet, SourceRef


class EvidenceError(RuntimeError):
    pass


def _extract_frame(media_path: Path, timestamp: float, destination: Path) -> float:
    capture = cv2.VideoCapture(str(media_path))
    if not capture.isOpened():
        capture.release()
        raise EvidenceError(f"could not open media for evidence extraction: {media_path.name}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if not math.isfinite(fps) or fps <= 0 or frame_count <= 0:
        capture.release()
        raise EvidenceError("input media has invalid timing for evidence extraction")
    last_frame_timestamp = (frame_count - 1) / fps
    decode_timestamp = max(0.0, min(timestamp, last_frame_timestamp))
    capture.set(cv2.CAP_PROP_POS_MSEC, decode_timestamp * 1000.0)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise EvidenceError(f"could not decode evidence frame at {decode_timestamp:.3f}s")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(destination), frame):
        raise EvidenceError(f"could not write evidence frame: {destination.name}")
    return round(decode_timestamp, 6)


def build_evidence(
    media_path: Path,
    candidates: CandidateSet,
    output_root: Path,
    *,
    extract_frames: bool,
    maximum_frames_per_candidate: int,
) -> EvidenceSet:
    claims: list[EvidenceClaim] = []
    for candidate in candidates.candidates:
        frame_refs: list[SourceRef] = []
        if (
            extract_frames
            and maximum_frames_per_candidate > 0
            and not candidate.commentary_only_suppressed
        ):
            timestamps = [
                candidate.start_sec,
                candidate.anchor_sec,
                max(candidate.start_sec, candidate.end_sec - 0.001),
            ]
            unique_timestamps = list(dict.fromkeys(round(value, 6) for value in timestamps))
            for frame_number, timestamp in enumerate(
                unique_timestamps[:maximum_frames_per_candidate], start=1
            ):
                relative = (
                    Path("evidence/frames")
                    / f"{candidate.candidate_id}-{frame_number:02d}.jpg"
                )
                decoded_timestamp = _extract_frame(
                    media_path, timestamp, output_root / relative
                )
                frame_refs.append(
                    SourceRef(
                        artifact=relative.as_posix(),
                        timestamp_sec=decoded_timestamp,
                    )
                )
        for modality in candidate.modalities:
            matching = [
                ref
                for ref in candidate.source_refs
                if ref.artifact.startswith(f"signals/{modality}")
            ]
            if modality == "video":
                matching.extend(frame_refs)
            statements = {
                "video": "Local frame differences indicate visual change in this window.",
                "audio": "Local WAV energy indicates an audio change in this window.",
                "transcript": "Transcript wording contains an event-oriented term.",
            }
            kinds = {
                "video": "visual_signal",
                "audio": "audio_signal",
                "transcript": "transcript_cue",
            }
            claims.append(
                EvidenceClaim(
                    claim_id=f"claim-{len(claims) + 1:04d}",
                    candidate_id=candidate.candidate_id,
                    kind=kinds[modality],
                    statement=statements[modality],
                    confidence=round(candidate.score, 6),
                    confidence_basis="deterministic local signal fusion; not semantic verification",
                    provenance=matching,
                    human_review_required=True,
                )
            )
        if candidate.context:
            claims.append(
                EvidenceClaim(
                    claim_id=f"claim-{len(claims) + 1:04d}",
                    candidate_id=candidate.candidate_id,
                    kind="context",
                    statement=f"Context terms: {', '.join(candidate.context)}.",
                    confidence=0.25,
                    confidence_basis="transcript context is not treated as event proof",
                    provenance=[
                        ref
                        for ref in candidate.source_refs
                        if ref.artifact == "signals/transcript.json"
                    ],
                    human_review_required=True,
                )
            )
    return EvidenceSet(schema_version="mimir.aegir.evidence.v1", claims=claims)
