# Agent instructions

- Treat this repository as an exploratory local-first PoC, not production.
- Start with `README.md`, `docs/ARCHITECTURE.md`, and `docs/NEXT_STEPS.md`.
- Baseline: install `requirements.txt`; run the documented `--demo`; run
  `python -m unittest discover -s tests -p 'test_*.py' -v` and
  `python -m compileall -q mimir_aegir tests`.
- Preserve strict versioned schemas, artifact paths, provenance, confidence
  basis, and human-review boundaries. Coordinate incompatible schema changes.
- Keep candidates recall-first, suppress transcript-only commentary, treat
  `offside` as context, and consolidate event chains.
- Change one cue rule, threshold, schema, or evaluation variable at a time and
  reuse the same review set. Do not claim accuracy gains from spot checks.
- Do not claim semantic verification, production/Azure readiness,
  replay/aftermath packaging, rendering/publishing, or skill certification.
- Never commit secrets, real infrastructure identifiers, personal paths,
  private media/corpus data, generated artifacts, reports, or telemetry.
- Keep Azure optional and explicit; prefer Managed Identity/Key Vault, flag
  cost, require privacy/compliance review for faces, biometrics, or personal
  data, and tear down PoC resources.
- Do not add or run reviewer automation as part of the published pipeline.
- The project is MIT licensed (see `LICENSE`).
