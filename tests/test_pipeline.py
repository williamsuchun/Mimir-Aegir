from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError

from mimir_aegir.azure import (
    AzureConfigurationError,
    BlobCreatedEvent,
    FoundrySettings,
    request_cloud_evidence,
)
from mimir_aegir.config import load_config
from mimir_aegir.demo import create_demo_bundle
from mimir_aegir.downstream import answer_grounded_question
from mimir_aegir.evidence import build_evidence
from mimir_aegir.ingest import probe_media
from mimir_aegir.models import (
    Candidate,
    CandidateSet,
    EvidenceSet,
    GroundedIndex,
    SourceRef,
)
from mimir_aegir.pipeline import PipelineError, run_pipeline

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/default.toml"


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.media = create_demo_bundle(self.root / "media")
        self.output = self.root / "artifacts"

    def test_demo_runs_all_stages_with_strict_artifacts(self) -> None:
        result = run_pipeline(self.media, self.output, load_config(CONFIG))
        self.assertEqual(result.schema_version, "mimir.aegir.result.v1")
        self.assertGreaterEqual(result.candidate_count, 1)
        self.assertGreaterEqual(result.kept_count + result.review_count, 1)
        expected = {
            "manifest.json",
            "signals/video.json",
            "signals/audio.json",
            "signals/transcript.json",
            "candidates.json",
            "evidence/evidence.json",
            "triage.json",
            "downstream/highlight-plan.json",
            "downstream/grounded-index.json",
            "result.json",
        }
        self.assertTrue(expected.issubset({
            path.relative_to(self.output).as_posix()
            for path in self.output.rglob("*.json")
        }))
        candidates = json.loads((self.output / "candidates.json").read_text())
        self.assertEqual(candidates["strategy"], "recall_first_event_chains")
        self.assertTrue(any(not item["commentary_only_suppressed"] for item in candidates["candidates"]))
        evidence = json.loads((self.output / "evidence/evidence.json").read_text())
        self.assertTrue(all(claim["provenance"] for claim in evidence["claims"]))
        self.assertTrue(all(claim["human_review_required"] for claim in evidence["claims"]))

    def test_transcript_only_offside_context_is_suppressed(self) -> None:
        run_pipeline(self.media, self.output, load_config(CONFIG))
        candidates = json.loads((self.output / "candidates.json").read_text())["candidates"]
        offside = [item for item in candidates if "offside" in item["context"]]
        self.assertTrue(offside)
        self.assertTrue(all(item["commentary_only_suppressed"] for item in offside))
        triage = {
            item["candidate_id"]: item
            for item in json.loads((self.output / "triage.json").read_text())["items"]
        }
        self.assertTrue(all(triage[item["candidate_id"]]["route"] == "drop" for item in offside))

    def test_grounded_qa_withholds_unknown_answer(self) -> None:
        run_pipeline(self.media, self.output, load_config(CONFIG))
        index = GroundedIndex.model_validate_json(
            (self.output / "downstream/grounded-index.json").read_text()
        )
        answer = answer_grounded_question("Was there a submarine?", index)
        self.assertIsNone(answer.answer)
        self.assertTrue(answer.withheld_reason)

    def test_missing_input_fails_explicitly(self) -> None:
        with self.assertRaisesRegex(PipelineError, "does not exist"):
            run_pipeline(self.root / "missing.mp4", self.output, load_config(CONFIG))
        self.assertFalse(self.output.exists())

    def test_video_only_user_media_writes_explicit_unavailable_modalities(self) -> None:
        user_media = self.root / "user" / "input.mp4"
        user_media.parent.mkdir()
        shutil.copyfile(self.media, user_media)
        run_pipeline(user_media, self.output, load_config(CONFIG))
        audio = json.loads((self.output / "signals/audio.json").read_text())
        transcript = json.loads((self.output / "signals/transcript.json").read_text())
        self.assertFalse(audio["available"])
        self.assertFalse(transcript["available"])
        self.assertIn("No PCM WAV sidecar", audio["reason"])
        self.assertIn("No VTT", transcript["reason"])

    def test_evidence_timestamp_at_end_of_stream_uses_last_decodable_frame(self) -> None:
        manifest = probe_media(self.media)
        candidate = Candidate(
            candidate_id="candidate-001",
            start_sec=manifest.duration_sec - 0.5,
            end_sec=manifest.duration_sec,
            anchor_sec=manifest.duration_sec - 0.25,
            score=0.5,
            modalities=["video"],
            reasons=["test end-of-stream boundary"],
            context=[],
            commentary_only_suppressed=False,
            source_refs=[
                SourceRef(
                    artifact="signals/video.json",
                    timestamp_sec=manifest.duration_sec - 0.25,
                )
            ],
        )
        evidence = build_evidence(
            self.media,
            CandidateSet(
                schema_version="mimir.aegir.candidates.v1",
                strategy="recall_first_event_chains",
                candidates=[candidate],
            ),
            self.output,
            extract_frames=True,
            maximum_frames_per_candidate=3,
        )
        frame_timestamps = [
            ref.timestamp_sec
            for ref in evidence.claims[0].provenance
            if ref.artifact.startswith("evidence/frames/")
        ]
        expected_last_frame = round(
            (manifest.frame_count - 1) / manifest.fps,
            6,
        )
        self.assertIn(expected_last_frame, frame_timestamps)
        self.assertLess(max(frame_timestamps), manifest.duration_sec)

    def test_unknown_config_key_is_rejected(self) -> None:
        bad = self.root / "bad.toml"
        bad.write_text(CONFIG.read_text() + "\nunknown = true\n", encoding="utf-8")
        with self.assertRaises(ValidationError):
            load_config(bad)

    def test_optional_azure_boundaries_are_strict_and_generic(self) -> None:
        settings = FoundrySettings(
            endpoint="https://example.invalid",
            deployment="example-deployment",
            region="example-region",
        )
        self.assertEqual(
            settings.responses_base_url,
            "https://example.invalid/openai/v1/",
        )
        event = BlobCreatedEvent.model_validate(
            {
                "eventType": "Microsoft.Storage.BlobCreated",
                "subject": "/blobServices/default/containers/media/blobs/input.mp4",
                "data": {
                    "url": "https://example.invalid/media/input.mp4",
                    "contentType": "video/mp4",
                },
            }
        )
        self.assertEqual(event.data["contentType"], "video/mp4")
        with self.assertRaises(ValidationError):
            BlobCreatedEvent.model_validate(
                {
                    "eventType": "Microsoft.Storage.BlobCreated",
                    "subject": "/unexpected/path",
                    "data": {
                        "url": "http://example.invalid/input.mp4",
                        "contentType": "video/mp4",
                    },
                }
            )

    def test_optional_cloud_evidence_rejects_unknown_provenance(self) -> None:
        run_pipeline(self.media, self.output, load_config(CONFIG))
        evidence = EvidenceSet.model_validate_json(
            (self.output / "evidence/evidence.json").read_text()
        )
        settings = FoundrySettings(
            endpoint="https://example.invalid",
            deployment="example-deployment",
            region="example-region",
        )

        class FakeResponses:
            @staticmethod
            def parse(**_kwargs: object) -> SimpleNamespace:
                return SimpleNamespace(
                    output_parsed={
                        "schema_version": "mimir.aegir.cloud-evidence.v1",
                        "items": [
                            {
                                "candidate_id": evidence.claims[0].candidate_id,
                                "summary": "Synthetic semantic enrichment.",
                                "confidence": 0.5,
                                "provenance_claim_ids": ["unknown-claim"],
                                "model_generated": True,
                                "human_review_required": True,
                            }
                        ],
                    }
                )

        client = SimpleNamespace(responses=FakeResponses())
        with self.assertRaisesRegex(AzureConfigurationError, "unknown claim"):
            request_cloud_evidence(
                client,
                settings,
                evidence,
                instructions="Return only evidence supported by cited local claims.",
            )

    def test_documented_cli_demo(self) -> None:
        output = self.root / "cli-output"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "mimir_aegir",
                "run",
                "--config",
                str(CONFIG),
                "--demo",
                "--output",
                str(output),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue((output / "result.json").is_file())


if __name__ == "__main__":
    unittest.main()
