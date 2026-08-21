# Contributing to Mimir Aegir

Mimir Aegir is an exploratory, local-first proof of concept. Changes should
make its implemented behavior easier to inspect or extend without implying
semantic accuracy, production readiness, or deployed Azure infrastructure.
Licensing is pending; do not infer redistribution or open-source rights.

## Setup and baseline

Use Python 3.11 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m mimir_aegir run \
  --config configs/default.toml \
  --demo \
  --output output/demo
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q mimir_aegir tests
```

The demo must print `candidates=2 keep=1 review=0 drop=1`. Generated input,
frames, and artifacts belong under ignored paths such as `output/`; never add
them to Git.

## Change workflow

1. Branch from current `main` and keep the change focused.
2. Read [the architecture contracts](docs/ARCHITECTURE.md) before changing a
   stage boundary.
3. Change one cue rule, threshold, schema, or stage behavior at a time.
4. Reuse the deterministic demo and the same evaluation set when comparing
   behavior. Do not claim improvement from spot checks.
5. Run the smallest relevant test first, then the full offline suite and
   compile check above.
6. Update the README, architecture, or roadmap when commands, contracts,
   limitations, or project state change.

For a single test:

```bash
python -m unittest tests.test_pipeline.PipelineTests.test_transcript_only_offside_context_is_suppressed -v
```

## Contract and compatibility rules

- `mimir_aegir/models.py` is the source of truth for artifact fields.
- Models are strict: unknown fields are rejected and each persisted artifact
  has a `schema_version`.
- Preserve provenance from candidate source references through evidence claim
  ids and downstream references.
- Candidate scores are bounded heuristic fusion scores, not probabilities.
- Retained evidence remains `human_review_required`.
- Grounded answers must cite an indexed document or provide a
  `withheld_reason`.
- Treat a field removal, meaning change, or type change as incompatible. Add a
  new schema version and migration/compatibility test rather than silently
  reusing `v1`.
- Update `PipelineResult.artifacts`, tests, diagrams, and documented output
  paths together when adding a persisted stage.

Failures should be explicit. Do not fabricate an unavailable modality, swallow
decode/schema errors, or continue with malformed cloud output.

## Fixture policy

The generated bundle in `mimir_aegir/demo.py` is the canonical offline fixture.
It must remain deterministic, synthetic, small, and free of private or
licensed media. Add behavior assertions in `tests/test_pipeline.py`; do not
commit generated media, frames, artifacts, corpora, labels, reports, or
telemetry. If an external review set is used, keep its identity and contents
outside the repository and compare iterations against the same set.

## Practical first contribution

A low-risk first change is extending the transparent transcript cue vocabulary
in `mimir_aegir/signals.py`.

1. Add one unambiguous event or context term to `EVENT_TERMS` or
   `CONTEXT_TERMS`; keep `offside` as context unless stronger non-text evidence
   supports an event.
2. Add a synthetic cue-focused test in `tests/test_pipeline.py`.
3. Confirm transcript-only commentary remains suppressed, event chains remain
   consolidated, and all existing `v1` artifact fields are unchanged.
4. Run the targeted test, full suite, demo, and compile check.

Do not broaden this first change into ASR, semantic classification, replay
packaging, or threshold tuning.

## Privacy, security, Azure, and cost

- Never commit credentials, connection strings, real endpoints, resource or
  deployment names, tenant/subscription ids, personal paths, private media, or
  identifying corpus information.
- Prefer environment variables, Managed Identity, and Key Vault for explicit
  Azure experiments.
- The default local command must remain credential-free and offline after
  dependency installation.
- Treat model output as untrusted; validate strict schemas and local provenance
  before use.
- Faces, biometrics, customer media, and personal data require human privacy
  and compliance review.
- Cloud inference, storage, and compute can create ongoing cost. Prefer local
  validation, set budgets, and tear down PoC resources after use.
- Reviewer automation is outside this repository's published pipeline; do not
  add reports, prompts, credentials, or runner implementation here.

PR descriptions should state what changed, why, assumptions, validation
commands, artifact/schema impact, and intentionally unresolved limitations.
