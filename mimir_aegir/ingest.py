"""Media probing and sidecar discovery."""

from __future__ import annotations

import math
from pathlib import Path

import cv2

from .models import MediaManifest


class IngestError(RuntimeError):
    pass


def _discover_sidecar(video: Path, suffixes: tuple[str, ...]) -> Path | None:
    for suffix in suffixes:
        candidate = video.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def probe_media(
    media_path: Path,
    *,
    audio_path: Path | None = None,
    transcript_path: Path | None = None,
) -> MediaManifest:
    if not media_path.is_file():
        raise IngestError(f"input media does not exist or is not a file: {media_path}")
    capture = cv2.VideoCapture(str(media_path))
    if not capture.isOpened():
        raise IngestError(f"OpenCV could not open input media: {media_path.name}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    capture.release()
    if not math.isfinite(fps) or fps <= 0 or frame_count <= 0 or width <= 0 or height <= 0:
        raise IngestError("input media has invalid or incomplete video metadata")

    resolved_audio = audio_path or _discover_sidecar(media_path, (".wav",))
    resolved_transcript = transcript_path or _discover_sidecar(
        media_path, (".vtt", ".srt", ".json", ".txt")
    )
    for label, candidate in (
        ("audio sidecar", resolved_audio),
        ("transcript sidecar", resolved_transcript),
    ):
        if candidate is not None and not candidate.is_file():
            raise IngestError(f"{label} does not exist or is not a file: {candidate}")

    return MediaManifest(
        schema_version="mimir.aegir.manifest.v1",
        source_file=media_path.name,
        duration_sec=round(frame_count / fps, 6),
        fps=round(fps, 6),
        frame_count=frame_count,
        width=width,
        height=height,
        audio_source=resolved_audio.name if resolved_audio else None,
        transcript_source=resolved_transcript.name if resolved_transcript else None,
        assumptions=[
            "OpenCV-reported timing is treated as the local video clock.",
            "Audio analysis requires a PCM WAV sidecar in the default installation.",
            "Transcript cues are treated as untrusted contextual evidence.",
        ],
    )
