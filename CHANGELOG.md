# Changelog

All notable changes to MEIDNet Matter are listed here. The format follows Keep a Changelog; versions follow semantic versioning.

## [Unreleased]

## [0.2.0] - 2026-10-06

Validation ladder, versioned candidate records, candidate clusters, and the link to Prism's scoring.

### Added
- The six-stage validation ladder (Generated · Chemistry checked · MLIP screened · DFT relaxed · DFT property confirmed · Experimentally tested). Every candidate records the highest stage it reached and the result of each stage; this version records stages 0 and 1 (a candidate that passed every chemistry rule stands at "Stage 1 · Chemistry checked"). The export page shows how many candidates reached each stage and which stages are the user's own.
- The candidate record is versioned: every candidate carries `"schema": "meidnet-matter/candidate-record/1"` and a provenance block (software versions, git commit, model sha256, dataset fingerprint, goal hash, run id). `GET /api/schema/candidate-record` returns the JSON Schema; the run bundle holds it as `candidate-record.schema.json`.
- One target, many structures: when the search has finished, candidates are grouped into clusters of similar encoder latents (cosine ≥ 0.9, leader clustering). The candidate carries its cluster, the run lists the clusters, the cards view shows them as groups, and the "Prioritise" control orders candidates by target accuracy, diversity (one per cluster first), stability, novelty, search score, encoder agreement or order found.
- `targets.csv` in the run bundle (and `GET /api/schema/targets-csv`): the layout that `meidnet score` (MEIDNet 2.3.1 or later) reads, so a run's candidates can be scored on Prism with the LeMat-GenBench metric families and the conditional extension. Each property carries the point target and/or the window that was asked for: "1.5 ± 0.3 eV" is target 1.5 with window 1.2–1.8, "at most 1.0 eV/atom" is a window with only its upper edge. The export page gives the three commands and links to the metric definitions.
- The candidate table exports `validation_stage`, `validation` and `cluster`; the manifest's validation block reports the ladder, the highest stage reached, the candidates per stage and the number of clusters.

### Changed
- The candidate's stability block is now the validation block (`status`, `stage`, `label`, `stages`, `next`, `records`); "Not screened" is replaced by the ladder's stage names.
- The landing page's ecosystem section links to Prism's scoring and ecosystem pages.

## [0.1.0] - 2026-10-06

Phase 0: the Perov-5 demo project end to end, live at https://babu09-meidnet-matter.hf.space/.

### Added
- A goal editor: target value, range or bound per property, family and variant, excluded elements and presets, the chemistry rules with their limits, the search budget; validated against the engine as you type.
- The Design Readiness report: six indicators measured before any search (held-out prediction error per targeted property, cross-modal retrieval in both directions, structural recoverability, the target's position in the training distribution and the data around it, one-to-many ambiguity, chemical-family support) and one verdict; a target that is not recommended can still be searched in exploratory mode.
- A candidate search with the MEIDNet engine; every candidate carries its predicted values with their domain status, the rules with values and windows, the encoder's own prediction and whether it agrees with the search's, the nearest training materials with their DFT values, the training data around the prediction, the dataset check by reduced formula and A|B|X site assignment, the stability stage, and a "why" sentence that repeats these facts. Table, cards and map; filters kept in the URL; comparison side by side; the search funnel with rejection reasons.
- Exports: CIF per candidate, the candidate table, the candidate record, and the run bundle with a manifest and file hashes.
- The demo artefacts (`examples/perov5`), built by `scripts/build_demo.py` from the Perov-5 CSVs and the published model with the engine's own benchmark functions.
- The API (`/api`), the Space deploy tooling (`deploy/`), the browser walk-through (`scripts/smoke_browser.mjs`) and the docs (scope, deployment, data, format of Phase 1).
