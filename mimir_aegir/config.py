"""Configuration loading with strict validation."""

from __future__ import annotations

import math
import tomllib
from pathlib import Path

from pydantic import Field, model_validator

from .models import StrictModel


class VideoConfig(StrictModel):
    sample_interval_sec: float = 0.5
    analysis_width: int = Field(default=160, ge=32, le=1920)

    @model_validator(mode="after")
    def finite_interval(self) -> "VideoConfig":
        if not math.isfinite(self.sample_interval_sec) or self.sample_interval_sec <= 0:
            raise ValueError("sample_interval_sec must be finite and positive")
        return self


class AudioConfig(StrictModel):
    window_sec: float = 0.5

    @model_validator(mode="after")
    def finite_window(self) -> "AudioConfig":
        if not math.isfinite(self.window_sec) or self.window_sec <= 0:
            raise ValueError("window_sec must be finite and positive")
        return self


class CandidateConfig(StrictModel):
    window_sec: float = 2.5
    minimum_score: float = Field(default=0.16, ge=0.0, le=1.0)
    chain_gap_sec: float = Field(default=1.25, ge=0.0)
    maximum_candidates: int = Field(default=12, ge=1, le=100)


class TriageConfig(StrictModel):
    keep_score: float = Field(default=0.55, ge=0.0, le=1.0)
    drop_score: float = Field(default=0.12, ge=0.0, le=1.0)
    minimum_supporting_modalities: int = Field(default=2, ge=1, le=3)

    @model_validator(mode="after")
    def thresholds_are_ordered(self) -> "TriageConfig":
        if self.drop_score >= self.keep_score:
            raise ValueError("drop_score must be lower than keep_score")
        return self


class OutputConfig(StrictModel):
    extract_evidence_frames: bool = True
    maximum_evidence_frames_per_candidate: int = Field(default=3, ge=0, le=12)


class PipelineConfig(StrictModel):
    schema_version: str
    video: VideoConfig
    audio: AudioConfig
    candidates: CandidateConfig
    triage: TriageConfig
    output: OutputConfig

    @model_validator(mode="after")
    def known_schema(self) -> "PipelineConfig":
        if self.schema_version != "mimir.aegir.config.v1":
            raise ValueError("unsupported configuration schema_version")
        return self


def load_config(path: str | Path) -> PipelineConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise ValueError(f"configuration file does not exist: {config_path}")
    with config_path.open("rb") as handle:
        return PipelineConfig.model_validate(tomllib.load(handle))
