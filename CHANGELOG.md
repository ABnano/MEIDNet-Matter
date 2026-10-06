# Changelog

All notable changes to MEIDNet Matter are listed here. The format follows Keep a Changelog; versions follow semantic versioning.

## [Unreleased]

## [0.1.0] - 2026-10-06

Phase 0: the Perov-5 demo project end to end, live at https://babu09-meidnet-matter.hf.space/.

### Added
- A goal editor: target value, range or bound per property, family and variant, excluded elements and presets, the chemistry rules with their limits, the search budget; validated against the engine as you type.
- The Design Readiness report: six indicators measured before any search (held-out prediction error per targeted property, cross-modal retrieval in both directions, structural recoverability, the target's position in the training distribution and the data around it, one-to-many ambiguity, chemical-family support) and one verdict; a target that is not recommended can still be searched in exploratory mode.
- A candidate search with the MEIDNet engine; every candidate carries its predicted values with their domain status, the rules with values and windows, the encoder's own prediction and whether it agrees with the search's, the nearest training materials with their DFT values, the training data around the prediction, the dataset check by reduced formula and A|B|X site assignment, the stability stage, and a "why" sentence that repeats these facts. Table, cards and map; filters kept in the URL; comparison side by side; the search funnel with rejection reasons.
- Exports: CIF per candidate, the candidate table, the candidate record, and the run bundle with a manifest and file hashes.
- The demo artefacts (`examples/perov5`), built by `scripts/build_demo.py` from the Perov-5 CSVs and the published model with the engine's own benchmark functions.
- The API (`/api`), the Space deploy tooling (`deploy/`), the browser walk-through (`scripts/smoke_browser.mjs`) and the docs (scope, deployment, data, format of Phase 1).
