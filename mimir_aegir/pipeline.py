"""Config-driven orchestration of the complete local pipeline."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from .artifacts import write_model
from .candidates import generate_candidates
from .config import PipelineConfig
from .downstream import build_grounded_index, build_highlight_plan
from .evidence import EvidenceError, build_evidence
from .ingest import IngestError, probe_media
from .models import ArtifactRef, PipelineResult
from .signals import SignalError, extract_audio_signals, extract_transcript_signals, extract_video_signals
from .triage import triage_candidates


class PipelineError(RuntimeError):
    pass


def run_pipeline(
    media_path: str | Path,
    output_dir: str | Path,
    config: PipelineConfig,
    *,
    audio_path: str | Path | None = None,
    transcript_path: str | Path | None = None,
) -> PipelineResult:
    media = Path(media_path)
    output = Path(output_dir)
    if output.exists() and not output.is_dir():
        raise PipelineError(f"output path exists and is not a directory: {output}")
    try:
        manifest = probe_media(
            media,
            audio_path=Path(audio_path) if audio_path else None,
            transcript_path=Path(transcript_path) if transcript_path else None,
        )
        discovered_audio = (
            Path(audio_path)
            if audio_path
            else media.with_suffix(".wav") if manifest.audio_source else None
        )
        discovered_transcript = (
            Path(transcript_path)
            if transcript_path
            else media.with_suffix(Path(manifest.transcript_source).suffix)
            if manifest.transcript_source
            else None
        )
        video = extract_video_signals(
            media, config.video.sample_interval_sec, config.video.analysis_width
        )
        audio = extract_audio_signals(discovered_audio, config.audio.window_sec)
        transcript = extract_transcript_signals(discovered_transcript)
        candidates = generate_candidates(
            video, audio, transcript, manifest.duration_sec, config.candidates
        )
        evidence = build_evidence(
            media,
            candidates,
            output,
            extract_frames=config.output.extract_evidence_frames,
            maximum_frames_per_candidate=(
                config.output.maximum_evidence_frames_per_candidate
            ),
        )
        triage = triage_candidates(candidates, config.triage)
        highlight_plan = build_highlight_plan(candidates, evidence, triage)
        grounded_index = build_grounded_index(evidence)
    except (IngestError, SignalError, EvidenceError, OSError, ValueError, ValidationError) as error:
        raise PipelineError(str(error)) from error

    artifacts = [
        ("ingest", "manifest.json", manifest),
        ("video_signals", "signals/video.json", video),
        ("audio_signals", "signals/audio.json", audio),
        ("transcript_signals", "signals/transcript.json", transcript),
        ("candidates", "candidates.json", candidates),
        ("evidence", "evidence/evidence.json", evidence),
        ("triage", "triage.json", triage),
        ("highlight_plan", "downstream/highlight-plan.json", highlight_plan),
        ("grounded_index", "downstream/grounded-index.json", grounded_index),
    ]
    refs: list[ArtifactRef] = []
    for stage, relative, model in artifacts:
        write_model(output / relative, model)
        refs.append(
            ArtifactRef(
                stage=stage,
                path=relative,
                schema_version=model.schema_version,
            )
        )
    counts = {
        route: sum(item.route == route for item in triage.items)
        for route in ("keep", "human_review", "drop")
    }
    result = PipelineResult(
        schema_version="mimir.aegir.result.v1",
        run_status="completed",
        source_file=media.name,
        candidate_count=len(candidates.candidates),
        kept_count=counts["keep"],
        review_count=counts["human_review"],
        dropped_count=counts["drop"],
        artifacts=refs,
        limitations=[
            "Local cheap signals propose review candidates; they do not establish event semantics.",
            "All retained evidence requires human review.",
            "Replay and aftermath packaging are not solved.",
        ],
    )
    write_model(output / "result.json", result)
    return result
