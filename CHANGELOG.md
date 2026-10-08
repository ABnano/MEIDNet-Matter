# Changelog

All notable changes to MEIDNet Matter are listed here. The format follows Keep a Changelog; versions follow semantic versioning.

## [Unreleased]

## [0.5.1] - 2026-10-08

### Fixed
- The 0.5.0 release workflow stopped before publishing: the engine wheel carried no readme, which the strict metadata check
  refuses. The vendored engine's project file now names its README, and the screening command no longer uses a Python 3.12-only
  f-string form, so the engine imports on Python 3.10 as well. A test checks that the install line on the Method page names the
  current application and engine versions. The release workflow inspects the application wheel by name now that two wheels sit in
  `dist/`.

## [0.5.0] - 2026-10-08

What an independent first-time user found while taking a public double-perovskite dataset from the Space through every
command of the "Run it on your data" guide, fixed at the source (engine snapshot 2.4.0.dev1). Their package of evidence
(install logs, every console, both trained models, the generation and screening runs) drove each item.

### Added
- One-command install: the engine wheel is attached to every release next to the application wheel; the README and the
  Method page print the command with CPU torch and an import check, and name the supported platforms (Linux, macOS,
  Windows through WSL; Windows 11 with Smart App Control blocks unsigned wheels).
- `meidnet` is a real command after `pip install` (console script and `python -m meidnet`); CI runs `meidnet --version`.
- `meidnet init --template generation`: the symmetry-decoder configuration of the live generator, for the guide's
  generation route; `meidnet train` builds the symmetry side-car itself when it is missing.
- Screening mode on a laptop: `meidnet_eval.screen_local` enumerates any family (any number of cation groups, any anion),
  labels every composition from its template cell with the trained model, keeps the ones inside the window, judges them with
  the independent MEGNet judge qualified on the test split, and marks known compositions with the data's own value. Block S0's
  remedy prints the command; `generate_to_target` warns when S0 graded the data for screening.
- `meidnet generate` marks every candidate known or new against the training table, prints the data's own value beside the
  model's estimate, and prints the model's validation error next to the targets.
- `ingest_upload` joins on the structure file's name as well as on composition, uses a -<space group> tag to pick a polymorph,
  reports how each row was matched, and exits non-zero when nothing matched.
- `preview --family` accepts a shipped family name, `--variant` or `family:variant`, measures the novelty frontier over the
  union of variants when none is given, and counts how many structures have the family's own prototype.
- A test runs `--help` on every command the Method page prints and fails when a flag is unknown.

### Changed
- `scorecard` computes every block for the first model named, whatever its name (`mine=` works; `main=` still names it).
- `conditional_generate` no longer requires `--tag` and `--gap`: the run folder defaults to `pool` and the target column to the
  checkpoint's gap column. `instrument_sheet` runs on a pool alone (unrelaxed cells, said so) and accepts `--relax` for the
  relaxation shards; `generate_to_target` is the one-command chain the Method page now prints.
- Training on CPU uses 4 threads unless OMP_NUM_THREADS or `training.threads` says otherwise (16 threads were 35× slower on
  small cells) and prints the measured pace after two epochs.
- Relaxation fetches the potentials with the classic Hub transfer (`HF_HUB_DISABLE_XET=1` unless set) and prints the cache
  path and the load time, so a stalled download is recognisable.
- `metrics_sun` says "not assessed" instead of "0 of N stable" when no hull energies were given.
- The scorecard's remedy no longer says "switch the structure losses on" when the configuration already has them on.
- The live generator points family-specific needs to the own-data route; a known formula whose recorded gaps all lie outside
  the window says so. The 246-structure study names its material classes. The Space card, the new-project page and the
  start-with-my-data page describe the local workflow as available now.

## [0.4.2] - 2026-10-08

### Fixed
- The code viewer on a block page never finished loading: the API client parsed every response as JSON, so a component's
  plain-text source came back as nothing and the viewer waited forever. Plain-text resources now have their own request path, with
  a unit test, and the live check waits for the viewer to render.

## [0.4.1] - 2026-10-08

### Added
- Workflow diagrams. The pipeline page opens with the ten blocks as a three-phase flow (before training, after training, after a
  run), each box opening its block; every block page starts with its own flow: what the block receives, the programs that compute
  it (a code box opens the source), the metrics it grades, and its verdict on each dataset.
- A link to MEIDNet Prism in the header and in the hero.

### Fixed
- On narrow screens the per-dataset verdicts of a pipeline block fell into the 48 px id column, leaving the row empty; they now span
  the row as one wrapping line.
- A component name followed by a comma in a block's note (`relax_cache.py,`) is now recognised as a viewable file.

## [0.4.0] - 2026-10-08

What a first external tester saw, taken up: what "matches" means, a result at the visual centre of the first visit, and the
same evidence view for both generators.

### Changed
- Perov-5 candidates distinguish the **search value** (the property head read at the search point, which kept the candidate
  and tends to repeat the request) from the **structure-based prediction** (the decoded structure encoded again). The second is
  shown first everywhere (cards, table, detail, compare, map, export); the results headline says how many candidates passed the
  search filters and how many are supported by a structure-based prediction. The candidate record gains
  `structure_predicted`, `structure_difference`, `structure_in_window`, `structure_domain` and a `support` block; `targets.csv`
  gains `<property>_search_value` and reports the structure-based value as `<property>_value`.
- The candidate map auto-scales to include every candidate, draws the training range as a dashed box, and lets the viewer place
  candidates by the search value, the structure-based prediction or the dataset's DFT value; clicking a point opens the card.
- Readiness: a published checkpoint that saw the test split in training is labelled a **published-model diagnostic**; "held-out"
  is reserved for genuinely untouched evaluation. The domain explanation names its test (percentile band or range) and says
  when a value lies inside the training range but outside the 1st–99th percentile band.
- The goal editor shows the training distribution of each targeted property with the requested window before anything runs,
  with the zero spike drawn apart (96 % of Perov-5 gaps are zero).
- Live generation results: 3D cards and a requested-versus-delivered evidence map, a detail panel with the cell, and three
  statuses kept apart — gap window (both models / label only / judge only / neither), charge balance, relaxed and re-judged
  (not in the live run). The generation record gains `sites`, `lattice_matrix` and `statuses`.
- Home page rebuilt around a worked result: a two-column hero with a real, clickable accepted structure and a compact
  requested-versus-delivered plot; an animated six-step walkthrough with plain and precise captions; a rolling strip of the
  accepted structures (paused on hover, static under reduced motion); three ways in (explore a result, set my target, use my
  data locally); the featured MP-20 study with its funnel, per-request table and limits; then the block × dataset matrix and
  the studies.
- The MP-20 study's accepted materials carry their relaxed cells as sites and lattice.

## [0.3.0] - 2026-10-07

The staged pipeline, four executed studies, the checkpoints behind them, and target-following generation with two judgements.

### Added
- The engine is vendored as a snapshot (`engine/`, distribution `meidnet` 2.4.0.dev0) with the symmetry decoder (space group and symmetry-distinct sites, expanded by the symmetry operations), labels read from the returned structure, and the evaluation components as the `meidnet_eval` package; `scripts/vendor_engine.py` refreshes it and records every file's sha256 in `engine/SNAPSHOT.json`.
- The staged pipeline, S0–S9: `GET /api/pipeline/blocks` serves the ten blocks with their metrics, bands, meanings and remedies from the single definition in `meidnet_eval.stages`; `GET /api/pipeline/components/{file}` serves each component's source read-only from an allowlist. Pages `/pipeline` and `/pipeline/{block}` with a code viewer.
- Four studies (`GET /api/studies`, `/api/studies/{id}`, `/api/studies/{id}/files/{name}`): Perov-5, the Materials Project perovskites, an external 246-structure upload (aggregates only) and MP-20, each with its block verdicts, target-following result, candidates and reproduction commands; built deterministically by `scripts/build_studies.py`. The MP-20 study carries the calibration of the generator (response curve, accuracy with a confidence interval, precision, resolution, range) and the thirteen accepted structures classified as rediscovered, new polymorph or new composition.
- A checkpoints manifest (`checkpoints/manifest.json`, `GET /api/checkpoints`) with sha256 and size for every model the studies refer to, downloads from the server when present and from the release assets otherwise; `scripts/fetch_assets.py` reads the manifest.
- Generation jobs (`POST /api/generate`, `GET /api/generate/{id}`, stop, per-candidate CIF, zip export, `GET /api/schema/generation-result`): a band-gap request in, structures out with the label read from the returned cell, an independent judge qualified on the dataset's test split, the two-judge consensus, charge balance, known-formula lookup and AMD novelty; relaxation is not run on the server and the record carries the local command. Page `/play`.
- Pages `/` (results, how a request becomes a structure, the blocks, the studies), `/method` (mechanism, strengths, limits, data requirements); the former landing page is at `/demo`.
- `/health` reports the engine version, whether the symmetry decoder is present, whether the judge is ready and whether the research artefacts are present.

### Changed
- The Space image installs the vendored engine, pymatgen, matgl and PyTorch Geometric, and prefetches the judge's weights at build time; `meidnet` is no longer installed from PyPI there.
- `deploy/deploy_space.py` stages every checkpoint the manifest marks for shipping and verifies each checksum.

### Fixed
- The home page's block × dataset verdict matrix is filled from the research build; it was empty on the first deploy because the server served the engine's blocks without the per-dataset verdicts.
- Header wraps on phones, footer links are spaced, and the model selector no longer widens the Generate page beyond the viewport.
- A generation job's final progress counters show the real number of draws and kept cells.
- Method page: a step-by-step "Run it on your data" guide with the exact commands of the shipped components; the Pipeline page points to it.
- The `size` npm script now has its `scripts/size-budget.mjs`.

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
