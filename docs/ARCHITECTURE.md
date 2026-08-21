# Architecture

## Scope and invariants

Mimir Aegir is a synchronous, local-first media-intelligence PoC. The CLI
orchestrates deterministic cheap-signal extraction and writes inspectable,
versioned JSON boundaries. It does not establish event semantics, render or
publish video, solve replay/aftermath packaging, or deploy Azure resources.

The core invariants are:

- candidates are recall-first event chains, not isolated fragments;
- transcript-only commentary is suppressed;
- `offside`, `replay`, and `aftermath` are context, not direct event proof;
- evidence carries source/time/frame/cue provenance;
- retained claims require human review;
- downstream QA cites indexed evidence or withholds;
- strict models reject unknown fields; stage failures stop the run.

## Control and data flow

`mimir_aegir/cli.py` loads strict TOML, creates the optional synthetic fixture,
and calls `pipeline.run_pipeline()`. The orchestrator computes all stage models
before atomically writing JSON artifacts. Evidence frames may be written while
evidence is built; a later failure is reported and is not disguised as a
completed run.

The call order is `cli -> config/demo -> pipeline -> ingest -> signals ->
candidates -> evidence/triage -> downstream`. Stage functions return strict
models to `pipeline.py`; the pipeline passes those models to `artifacts.py` for
atomic JSON writes. `evidence.py` writes optional JPEG frames directly under
the output root.

## Module ownership

| Module | Owns | Does not own |
| --- | --- | --- |
| `models.py` | Strict persisted and downstream contracts | Stage algorithms |
| `config.py` | TOML shape, ranges, threshold ordering | Runtime defaults outside config |
| `demo.py` | Deterministic synthetic MP4/WAV/VTT | User fixtures |
| `ingest.py` | Video metadata and sidecar discovery | Embedded audio extraction |
| `signals.py` | Video, PCM WAV, and transcript cheap signals | Semantic verification or ASR |
| `candidates.py` | Fusion seeds, suppression, chain consolidation | Editorial correctness |
| `evidence.py` | Frames, claims, confidence basis, provenance | Model inference |
| `triage.py` | Deterministic drop/keep/review routing | Human judgment |
| `downstream.py` | Plan-only clips, lexical grounded index/answer | Rendering, publishing, vector retrieval |
| `azure.py` | Optional settings, Event Grid event validation, strict Responses adapter | Default pipeline execution or deployment |
| `artifacts.py` | Atomic model JSON writes | Cross-artifact transactions |
| `pipeline.py` | Stage ordering, artifact registry, result counts/limits | Async or distributed execution |

## Stage contracts and lifecycle

| Stage | Input | Persisted output | Important contract |
| --- | --- | --- | --- |
| Ingest | video and optional sidecar paths | `manifest.json` | OpenCV clock assumptions and discovered source names |
| Signals | manifest sources/config | `signals/video.json`, `audio.json`, `transcript.json` | Missing optional modalities are explicit `available: false` |
| Candidates | all signal models/duration | `candidates.json` | `strategy=recall_first_event_chains`, source refs preserved |
| Evidence | video/candidates/output config | `evidence/evidence.json`, optional JPEG frames | Claims cite local refs and require review |
| Triage | candidates/thresholds | `triage.json` | Unsupported commentary drops; ambiguity routes to review |
| Downstream | candidates/evidence/triage | `highlight-plan.json`, `grounded-index.json` | Plan-only clips; claim-linked documents |
| Result | all stage models | `result.json` | Completion counts, artifact paths/versions, limitations |

Contract classes in `models.py` use Pydantic `extra="forbid"` and strict
validation. JSON is written through `artifacts.write_model()` using a temporary
file and `os.replace`. A `v1` artifact should retain field names, types, and
meaning. Incompatible changes require a new schema version, coordinated readers,
artifact registration, tests, and documentation.

## Failure behavior

Missing/invalid media, sidecars, configuration, decodes, frame extraction, or
strict model data become a non-zero CLI exit with `ERROR:` on stderr. Missing
optional sidecars are not errors and produce explicit unavailable signal
artifacts. The pipeline does not implement rollback of already-extracted JPEGs,
resume, retries, queues, or cross-file transactional commits.

## Local and Azure boundary

The CLI and `pipeline.py` never import or invoke `azure.py`. The optional
adapter must be called explicitly by library code after installing `.[azure]`
and supplying `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, and
`AZURE_OPENAI_REGION`. It validates strict model output and rejects unknown or
missing local claim ids. It is a generic integration boundary, not evidence of
a deployed or end-to-end validated Azure path.

An Azure ingestion implementation should use an Event Grid `BlobCreated`
boundary, durable work dispatch, scoped identity, and untrusted-input
validation. It must not bypass local contracts or the human-review boundary.

## Adding an extension

### Signal extractor

Add or adapt extraction in `signals.py`, model the output in `models.py`, and
keep unavailable input explicit. If it is persisted, register it in
`pipeline.py`, carry refs into `candidates.py`, and add deterministic contract
tests. A new modality also requires explicit fusion weighting and schema
version decisions; do not append it through unchecked dictionaries.

### Candidate rule

Change `candidates.py` while preserving recall-first seeds, transcript
subordination, chain consolidation, bounded scores, stable source refs, and the
suppression flag. Tune one variable at a time against the same review set.

### Evidence source

Add claims in `evidence.py` with a deterministic confidence basis and valid
`SourceRef` entries. Preserve `human_review_required=True`; do not describe a
detector/model output as verified fact.

### Downstream stage

Consume strict models rather than scraping files. Add a strict output model,
write it through `pipeline.py`, reference upstream claim ids, register it in
`PipelineResult.artifacts`, and test missing-evidence behavior. Rendering and
retrieval remain separate future stages, not implied by the current plan/index.
