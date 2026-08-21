"""Local video, WAV audio, and transcript signal extraction."""

from __future__ import annotations

import json
import re
import wave
from pathlib import Path

import cv2
import numpy as np

from .models import (
    AudioSignal,
    AudioSignals,
    TranscriptCue,
    TranscriptSignals,
    VideoSignal,
    VideoSignals,
)

EVENT_TERMS = {
    "cheer",
    "finish",
    "goal",
    "impact",
    "jump",
    "save",
    "score",
    "shot",
    "splash",
    "start",
}
CONTEXT_TERMS = {"offside", "replay", "aftermath"}
COMMENTARY_TERMS = {"analysis", "commentary", "earlier", "recap", "talking"}
TIMESTAMP = re.compile(
    r"(?P<h1>\d{1,2}):(?P<m1>\d{2}):(?P<s1>\d{2}(?:[.,]\d+)?)\s+-->\s+"
    r"(?P<h2>\d{1,2}):(?P<m2>\d{2}):(?P<s2>\d{2}(?:[.,]\d+)?)"
)


class SignalError(RuntimeError):
    pass


def extract_video_signals(
    media_path: Path, sample_interval_sec: float, analysis_width: int
) -> VideoSignals:
    capture = cv2.VideoCapture(str(media_path))
    if not capture.isOpened():
        raise SignalError(f"OpenCV could not decode input media: {media_path.name}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, round(sample_interval_sec * fps))
    samples: list[VideoSignal] = []
    previous: np.ndarray | None = None
    for frame_index in range(0, frame_count, step):
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        analysis_height = max(18, round(gray.shape[0] * analysis_width / gray.shape[1]))
        reduced = cv2.resize(
            gray, (analysis_width, analysis_height), interpolation=cv2.INTER_AREA
        )
        motion = (
            float(np.mean(cv2.absdiff(reduced, previous))) / 255.0
            if previous is not None
            else 0.0
        )
        samples.append(
            VideoSignal(
                timestamp_sec=round(frame_index / fps, 6),
                frame_index=frame_index,
                motion=round(min(1.0, motion), 6),
                brightness=round(float(np.mean(gray)) / 255.0, 6),
                sharpness=round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 6),
            )
        )
        previous = reduced
    capture.release()
    if len(samples) < 2:
        raise SignalError("input media produced fewer than two decodable samples")
    return VideoSignals(
        schema_version="mimir.aegir.video-signals.v1",
        sample_interval_sec=sample_interval_sec,
        samples=samples,
    )


def extract_audio_signals(audio_path: Path | None, window_sec: float) -> AudioSignals:
    if audio_path is None:
        return AudioSignals(
            schema_version="mimir.aegir.audio-signals.v1",
            available=False,
            reason="No PCM WAV sidecar was provided or auto-discovered.",
            source_file=None,
            sample_rate_hz=None,
            windows=[],
        )
    try:
        with wave.open(str(audio_path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frame_count = handle.getnframes()
            payload = handle.readframes(frame_count)
    except (wave.Error, OSError) as error:
        raise SignalError(f"could not read PCM WAV sidecar {audio_path.name}: {error}") from error
    if sample_width != 2:
        raise SignalError("default audio analysis supports 16-bit PCM WAV sidecars only")
    raw = np.frombuffer(payload, dtype="<i2").astype(np.float64)
    if channels > 1:
        raw = raw.reshape(-1, channels).mean(axis=1)
    normalized = raw / 32768.0
    window_samples = max(1, round(window_sec * sample_rate))
    windows: list[AudioSignal] = []
    for start in range(0, len(normalized), window_samples):
        chunk = normalized[start : start + window_samples]
        if chunk.size == 0:
            continue
        rms = float(np.sqrt(np.mean(np.square(chunk))))
        peak = float(np.max(np.abs(chunk)))
        crossings = (
            float(np.count_nonzero(np.diff(np.signbit(chunk)))) / max(1, chunk.size - 1)
        )
        windows.append(
            AudioSignal(
                start_sec=round(start / sample_rate, 6),
                end_sec=round(min(len(normalized), start + chunk.size) / sample_rate, 6),
                rms=round(min(1.0, rms), 6),
                peak=round(min(1.0, peak), 6),
                zero_crossing_rate=round(min(1.0, crossings), 6),
            )
        )
    return AudioSignals(
        schema_version="mimir.aegir.audio-signals.v1",
        available=True,
        reason=None,
        source_file=audio_path.name,
        sample_rate_hz=sample_rate,
        windows=windows,
    )


def _seconds(parts: re.Match[str], prefix: str) -> float:
    return (
        int(parts.group(f"h{prefix}")) * 3600
        + int(parts.group(f"m{prefix}")) * 60
        + float(parts.group(f"s{prefix}").replace(",", "."))
    )


def _classify_cue(cue_id: str, start: float, end: float, text: str) -> TranscriptCue:
    words = set(re.findall(r"[a-z0-9']+", text.lower()))
    return TranscriptCue(
        cue_id=cue_id,
        start_sec=round(start, 6),
        end_sec=round(end, 6),
        text=" ".join(text.split()),
        event_terms=sorted(words & EVENT_TERMS),
        context_terms=sorted(words & CONTEXT_TERMS),
        commentary_terms=sorted(words & COMMENTARY_TERMS),
    )


def _timed_text_cues(text: str) -> list[TranscriptCue]:
    lines = text.replace("\r\n", "\n").splitlines()
    cues: list[TranscriptCue] = []
    index = 0
    while index < len(lines):
        match = TIMESTAMP.search(lines[index])
        if not match:
            index += 1
            continue
        start, end = _seconds(match, "1"), _seconds(match, "2")
        index += 1
        content: list[str] = []
        while index < len(lines) and lines[index].strip():
            content.append(lines[index].strip())
            index += 1
        if content and end > start:
            cues.append(_classify_cue(f"cue-{len(cues) + 1:03d}", start, end, " ".join(content)))
    return cues


def extract_transcript_signals(transcript_path: Path | None) -> TranscriptSignals:
    if transcript_path is None:
        return TranscriptSignals(
            schema_version="mimir.aegir.transcript-signals.v1",
            available=False,
            reason="No VTT, SRT, JSON, or TXT transcript sidecar was provided or auto-discovered.",
            source_file=None,
            cues=[],
        )
    text = transcript_path.read_text(encoding="utf-8")
    cues: list[TranscriptCue]
    if transcript_path.suffix.lower() == ".json":
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise SignalError("JSON transcript must be a list of cue objects")
        cues = [
            _classify_cue(
                f"cue-{index:03d}",
                float(item["start_sec"]),
                float(item["end_sec"]),
                str(item["text"]),
            )
            for index, item in enumerate(payload, start=1)
            if isinstance(item, dict)
        ]
    elif transcript_path.suffix.lower() in {".vtt", ".srt"}:
        cues = _timed_text_cues(text)
    else:
        cues = [_classify_cue("cue-001", 0.0, 0.001, text)] if text.strip() else []
    return TranscriptSignals(
        schema_version="mimir.aegir.transcript-signals.v1",
        available=True,
        reason=None,
        source_file=transcript_path.name,
        cues=cues,
    )
