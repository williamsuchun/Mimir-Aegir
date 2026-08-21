"""Command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from .config import load_config
from .demo import DemoError, create_demo_bundle
from .pipeline import PipelineError, run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mimir-aegir")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run the configured local pipeline")
    run.add_argument("--config", default="configs/default.toml")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="input video path")
    source.add_argument("--demo", action="store_true", help="generate deterministic media")
    run.add_argument("--audio", help="optional 16-bit PCM WAV sidecar")
    run.add_argument("--transcript", help="optional VTT, SRT, JSON, or TXT sidecar")
    run.add_argument("--output", default="output/demo")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output)
    try:
        config = load_config(args.config)
        media = create_demo_bundle(output / "input") if args.demo else Path(args.input)
        result = run_pipeline(
            media,
            output,
            config,
            audio_path=args.audio,
            transcript_path=args.transcript,
        )
    except (PipelineError, DemoError, ValidationError, ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(output / "result.json")
    print(
        f"candidates={result.candidate_count} keep={result.kept_count} "
        f"review={result.review_count} drop={result.dropped_count}"
    )
    return 0
