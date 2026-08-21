# Next steps

This backlog reflects the current PoC implementation. Priorities describe
concrete continuation work, not commitments or production readiness.

## P0 — Stage 1 local accuracy and usability

| Gap | Deliverable and likely files | Acceptance criteria | Dependencies |
| --- | --- | --- | --- |
| Heuristic quality is only covered by one synthetic scenario | Add an external, non-committed review-set harness and deterministic metric summary around `candidates.py`, `triage.py`, and `tests/` | Same fixed review set compares one-variable changes; candidate recall, suppression errors, and route distribution are reported without private identifiers | Authorized media/labels and documented evaluation protocol |
| Decode and artifact failure recovery is minimal | Define run workspace semantics and stale/partial-output handling in `pipeline.py`, `evidence.py`, and `artifacts.py` | Interrupted/failed runs cannot be mistaken for `run_status=completed`; reruns have deterministic documented behavior | Lifecycle design and compatibility decision |
| Candidate timing is based on fixed windows and simple chain gaps | Add code-grounded boundary tests and an optional boundary policy in `candidates.py`/`config.py` | Event chains avoid duplicate short fragments on the fixed review set without reducing transcript-commentary suppression | P0 evaluation harness |

## P1 — Audio, transcript, and multimodal evidence

| Gap | Deliverable and likely files | Acceptance criteria | Dependencies |
| --- | --- | --- | --- |
| Audio requires a separate 16-bit PCM WAV | Add an explicit preprocessing adapter outside base signal logic, then feed the existing audio contract through `ingest.py`/`signals.py` | Supported formats, clock alignment, failures, and cost are documented; unavailable audio is never fabricated | Chosen local tool/runtime and licensing review |
| No ASR, diarization, or transcript alignment exists | Add an optional transcript adapter producing timestamped cues accepted by `signals.py` | Synthetic tests cover malformed cues and timing; text remains untrusted context; no credentials or private fixtures are tracked | Provider/tool selection, privacy review, optional dependency boundary |
| Fusion uses fixed transparent weights | Add a versioned, explainable fusion policy in `config.py`/`candidates.py` with evidence-aware evaluation | Scores stay bounded and source refs survive; one-variable evaluation shows tradeoffs, not unqualified improvement claims | P0 evaluation harness and representative authorized modalities |
| Evidence does not combine semantic multimodal claims | Add a strict evidence-enrichment interface in `models.py`/`evidence.py` or an explicit adapter, with optional `azure.py` integration | Every generated item cites known local claim ids, is schema-validated, and remains human-review-required | Approved model/deployment, cost budget, privacy/security review |

Replay and aftermath packaging are explicitly unsolved. Context terms are
preserved today, but a future deliverable must demonstrate separate event,
replay, aftermath, and editorial packaging behavior on the fixed review set
before any solved claim is made.

## P2 — Retrieval, reasoning, and grounded outputs

| Gap | Deliverable and likely files | Acceptance criteria | Dependencies |
| --- | --- | --- | --- |
| Grounded retrieval is lexical and in-memory | Introduce a replaceable retrieval interface behind `downstream.py` while retaining `GroundedIndex` compatibility or a versioned successor | Queries cite evidence-backed documents or withhold; no uncited answer path; persistence and deletion behavior documented | P1 evidence contract and privacy review |
| Highlight output is plan-only | Add a separate renderer consuming `downstream/highlight-plan.json` | Deterministic dry-run and render tests; no auto-publish; review status remains visible; replay/aftermath is not inferred | Explicit media tooling choice and licensing review |
| No orchestration/deployment stack exists | Design and validate an optional Event Grid plus durable-work implementation around the local worker boundary | Idempotency, retries, identity scope, input validation, teardown, and cost controls are tested and documented | Stable local contracts, Azure architecture/security review, budget |
| No grounded reasoning layer exists | Add strict cited output schemas and a review workflow consuming retrieved evidence | Unsupported questions withhold; citations resolve to immutable provenance; low confidence routes to human review | Retrieval interface and approved evaluation set |
