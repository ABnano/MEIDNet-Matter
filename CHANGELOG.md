# Changelog

All notable changes to MEIDNet Matter are listed here. The format follows Keep a Changelog; versions follow semantic versioning.

## [Unreleased]

## [0.9.0] - 2026-10-09

What a new visitor meets first: the demo search, the links that outlive a run, the page head, and small fixes.

### Changed
- Perov-5 demo: the default model is now desc-full-sp4, the desc-full recipe with four times the weight on reading the
  properties from the structure: of the 15 checkpoints trained on the training split (six new desc-full variants and nine
  existing models), the one with the best band-gap reading on the validation split, under a rule written down before the
  new ones finished training. On the held-out test split its band-gap
  error is 0.41 of the spread on the materials with a non-zero gap (fair; desc-full: 0.53, weak) and its formation-enthalpy
  error 0.08 (good), so the default goal is graded CAUTION and runs as a normal search instead of in exploratory mode. The
  trade-off: it rebuilds held-out structures from their joint encoding less often (composition 20%, desc-full 58%), which
  the readiness report shows; the inverse path, from a property target to a structure, is unchanged (38.9% of sites).
  The published model stays selectable. A checkpoints folder without the new file falls back to the published model and
  says so.
- When every reason against a target is the model's weak reading of a property, the readiness page leads with "Run
  exploratory search" and says why; "Adjust target" stays the first action when the target itself is the problem. A
  "fair" reading states its ratio to the spread, and the latent-neighbourhood sentence no longer says the neighbours read a
  property better when they do not.
- The front door says what Matter does in five lines (what, for whom, input, output, time) on the Space card and in the
  README; the page title, description, preview image and short description no longer promise an upload. One main action,
  "Run a band-gap search", in the header and on the home page. `/demo`, an old landing page, now leads to the demo.
- The Space image installs every dependency at a pinned version (`deploy/constraints.txt`, frozen from a clean install of
  exactly what the image installs: CPU torch, the engine, `meidnet-matter[judge]` and the Space's own requirements, uvicorn's
  extras included), and the release's `constraints.txt` now includes the judge's stack (matgl, torch-geometric, lightning).

### Fixed
- A run or a generation job the server no longer has says so at once: 410 `gone` when this server removed it (a finished
  run is kept for an hour after its last use), 404 `run_not_found` with the reason otherwise (every restart starts empty).
  Its pages explain it and offer "Re-run this goal" (the search's goal is kept in the browser that ran or opened it) or
  "Generate again" instead of a spinner and a raw error code. A goal kept in a tab that names a model the demo no longer
  has falls back to the default model.
- A refused search (busy, host full) no longer leaves a record stuck in "queued".
- Pages keep their side margins on narrow screens (`.page` sets only its vertical padding).
- Every page has its own title; the formula in the candidate tables is a button that opens the candidate from the
  keyboard; the faint text colour reaches 4.5:1 contrast; large responses travel gzip-compressed.

## [0.8.1] - 2026-10-09

### Fixed
- A checkpoints folder from before 0.8.0 holds only the published Perov-5 model. The demo now runs on that model, and
  `/health` says why under `notes`, instead of failing at the first search because the new default model's file is
  missing; `python scripts/fetch_assets.py` fetches every model. CI fetches both demo models.

## [0.8.0] - 2026-10-09

### Fixed
- MP-20 study: three accepted cells were not bulk crystals. HfZrAuI₄ and KTe hold an empty layer of 8.9 and 6.6 Å (slabs),
  and BaBHS₂ has a packing fraction of 0.11. A bulk test now sets such relaxed cells aside next to the contact test: an
  empty layer over 6 Å or a packing fraction under 0.12, lines that 98.7% of the 45,229 known MP-20 crystals meet. The
  study keeps 4 accepted structures (Na₂Ag₂Sb₂Te, a new composition; Na₂O₂ and SrO, new polymorphs; CaO, matching
  mp-545512, recorded at 3.12 eV), and its calibration comes from the 13 relaxed cells that pass both tests: MAE 0.88 eV,
  delivered = 0.34 + 0.71 × requested.
- "Rediscovered known structure" now needs a structural match (StructureMatcher) with an MP-20 entry of the same formula,
  every entry compared. It came from a composition-blind AMD distance to a 4,000-structure sample, which had called Na₂O₂
  and SrO rediscoveries.
- Before and after relaxation are compared on the same cells: the judge's error against the request is 0.25 eV on the 13
  cells before relaxation and 0.88 eV after. The 1.10 eV of all 175 generated cells describes a different set.
- Scorecard (engine): every component runs inside `--out`, so no result is read from or written to the package folder; a
  failed component marks its blocks NOT COMPUTED with the reason, and the command exits non-zero. `--cost` defaults to
  the intake's formation-energy column.
- On a shared host, a generation job or a search can be stopped only from the session that started it, and the session id
  is no longer served in job or run records or written into downloaded zips.
- Perov-5 demo: the default model is now desc-full, MEIDNet retrained on the training split with element descriptors. On
  the held-out test split it reads formation enthalpy with R² 0.99 and the band gap with R² 0.80 (the published model: 0.48
  and −31.4), and the published model stays selectable. The band gap is graded on the materials with a non-zero gap, where
  its error (0.83 eV against a spread of 1.56 eV) is still weak by the engine's thresholds, so a band-gap target runs in
  exploratory mode.

### Changed
- The live generator drops cells with an empty layer over 6 Å or a packing fraction under 0.12 as it draws them (in the
  MP-20 study no such cell became bulk-like on relaxation), and every generated cell carries its contact ratio, thickest
  empty layer and packing fraction; under a contact ratio of 0.6 the page says to relax the cell before any use.
- Band-gap readings are described as what they are: two machine-learning estimates of the PBE band gap the data records
  (the generator's label and MEGNet, a second model that played no part in generation), not independent measurements.
- `candidates.csv` drops the `predicted_<property>` and `difference_<property>` columns kept from 0.2: they held the search
  value, which `search_<property>` and `search_difference_<property>` carry under their own name, next to
  `structure_<property>`.
- Engine snapshot 2.4.0.dev3.

## [0.7.1] - 2026-10-09

### Fixed
- The MP-20 study counted collapsed cells: 20 of its 37 relaxed cells, 6 of the 13 accepted among them (ZnCdPS₂, CsI,
  Sr(HgCl)₂, CaTe, LaI, Zn₅I₈), have atoms pushed into each other after relaxation (P–S 0.31 Å, Hg–Hg 0.95 Å,
  Te–Te 1.23 Å). With the contact test the study keeps 7 accepted structures (3 new compositions, 1 new polymorph, 3 known
  compounds at their recorded gaps), and its calibration comes from the 17 relaxed cells that stayed physical: MAE 0.80 eV
  (0.68 before), delivered = 0.24 + 0.80 × requested (0.09 + 0.86 before), novelty 88%. The Method page and the home page
  quote the corrected numbers; a test checks every accepted cell with the contact test.

## [0.7.0] - 2026-10-09

A new case study: double perovskites from public JARVIS-DFT data, the independent user's journey run again from the
published packages.

### Added
- The study "Double perovskites from public JARVIS-DFT data": the user's dataset (1,282 A₂BB′X₆ compounds), their two
  trained models, and every stage from S0 to S9, run again end to end with the packages installed from PyPI and the release
  in a fresh environment. Five routes (three screenings, family generation, family-free generation) go through the same check;
  the page shows a funnel per route, the accepted structures with their relaxed cells (CIF), the label from each cell, the
  qualified judge, the energy above the hull with one potential for every phase and its calibration on known materials,
  novelty against the data and JARVIS-DFT, checks against other databases, the limits, and what the study taught the
  pipeline. Its new double perovskites join the home page's strip, and its verdicts the per-dataset columns of the pipeline
  pages.
- Study pages render routes, a stability card, and per structure its route and its energy above the hull, with the reason
  when that value is not a stability statement.

### Changed
- `scripts/install.sh` pins the release's known-good versions only on the Python they were resolved for (3.12); on another
  Python it installs unpinned and says so (numpy 2.5, for one, has no Python 3.10 build).
- The list of studies is defined once for every page that shows a verdict per dataset.

## [0.6.1] - 2026-10-08

The install, the way a newcomer expects it: `pip install "meidnet-matter[judge]"`.

### Added
- PyPI: the release workflow uploads the application (`meidnet-matter`) and the engine snapshot (`meidnet` 2.4.0.dev2, so the
  application's dependency resolves without a clone) by trusted publishing, one step per project; the upstream MEIDNet release
  2.4.0 will replace the snapshot on PyPI.
- `constraints.txt` on every release: every dependency at the version the release's own install check used (Linux, Python
  3.12, CPU torch). `pip install -c <that file> "meidnet-matter[judge]"` reproduces a tested environment; the independent
  tester had asked for a lock file of known-good versions.
- `scripts/install.sh`: the install in one go with retries (three attempts, long timeouts), a fresh virtual environment (venv,
  or uv when venv is missing, as on a stock Ubuntu), CPU torch first, the pinned install from PyPI or from the release's wheels
  (`MATTER_SOURCE=release`), and the import check. It refuses to run in a Windows shell and points to WSL, where Smart App
  Control does not block the wheels.

### Changed
- README and Method page: the PyPI command first, the release-wheel command as the fallback for a mirror or an offline
  machine, the installer for slow networks. The README's links are absolute, so the PyPI project page renders them.

## [0.6.0] - 2026-10-08

The independent user's double-perovskite journey run again end to end with the fixed engine (snapshot 2.4.0.dev2), and
what their package had left open made runnable: relaxation and stability for every route, block S8, the local web app,
scoring on Prism. The site now has a mirror on GitHub Pages for networks that block `*.hf.space`.

### Added
- `meidnet_eval.check_candidates`: one check for any candidate table, whichever route produced it (family-free generation,
  screening, family generation): the label read from each cell, the MEGNet judge qualified on the test split, the two-model
  consensus, relaxation by two potentials (TensorNet, CHGNet), both readings again on the relaxed cells, optionally the
  energy above the hull, novelty against the data, REPORT.md, report.json, the instrument sheet and a Prism-ready
  `targets.csv`. Every accepted structure is classed as a new composition, a rediscovery (a DFT value inside the window) or
  contradicted by a DFT value; the DFT value comes from the user's own data first, then from the hull's reference set (JARVIS-DFT
  or the Materials Project), so "new" means absent from both. `generate_to_target` now runs its back half through it, `screen_local
  --check` runs it on the screening shortlist, and `meidnet generate` prints the command for its candidates (the glue the
  tester had to write by hand).
- `meidnet_eval.hull_mlip`: the energy above the convex hull with one potential for every phase. The candidates and every
  near-hull competing phase of their chemical systems, taken from a reference set of known crystals (the public JARVIS-DFT 3D
  file, or the Materials Project with an API key), are relaxed by the same potential, in a process pool, with a cache keyed by
  structure content. `--validate INTAKE --stability-col COL` calibrates the estimate on known materials of the user's data and
  reports the mean and median error, the rank correlation, the agreement on "within 0.1 eV/atom", and the reference values that
  are implausible for a known compound (listed, with the statistics given without them too). The same option,
  `--hull-reference`, works on `screen_local`, `generate_to_target` and `check_candidates`; block S7's stable share is computed
  by it.
- Block S8 in the scorecard: `--judge megnet` qualifies the MEGNet band-gap judge on the intake's test split before it judges
  anything (every fidelity head is measured, the best is kept).
- The Method page: S8 in the scorecard step, `--check` in the screening step, and a stability step for any route (with
  where to download the JARVIS-DFT file).
- A static mirror of the site on GitHub Pages, https://abnano.github.io/MEIDNet-Matter/, for networks that block
  `*.hf.space` (public Wi-Fi often does, and the Space then shows a grey page). `npm run build:mirror` builds the same app
  with relative paths and its routes after `#`, `scripts/build_mirror.py` writes every read-only API response the pages
  use as a file beside it (from the application itself), and `.github/workflows/pages.yml` publishes it for every release.
  Everything that reads works there; generation and the demo search point to the Space, and a banner says whether the
  Space is reachable from the visitor's network (with the secure-DNS remedy when it is not). The Space's card, the README
  and the site's footer link the mirror; from the mirror, Prism links go to Prism's own mirror.
- The release workflow uploads the application and the engine wheel to PyPI with trusted publishing, once the publishers
  are registered on pypi.org (`meidnet-matter`, and `meidnet` for the engine wheel); until then that job fails on its own
  and the GitHub release is unaffected.
- A relaxed cell whose closest atoms sit nearer than 0.6 of their two radii is collapsed, not a crystal: `check_candidates`
  sets it aside before judging the relaxed cells again and lists it in the report, and the instrument sheet leaves it out of
  every number (counted in its funnel). Every one of the 1,282 known materials of the tester's data lies above 0.73.
- The hull module marks a value it cannot read as a stability statement and leaves it out of the stable share: a cell that
  collapsed during its relaxation, or one more than 0.1 eV/atom below every known phase of its system (the note names the
  element pairs the reference set has no compound for: JARVIS-DFT has, for one, no cesium halide). A relaxation stopped by
  the step limit is noted as an upper estimate. The relaxation record says whether the optimiser converged.

### Changed
- The screening report is `screening_report.md` (it would collide with the check's `REPORT.md` on case-insensitive file
  systems); with `--check` the screening skips its quick judge, which the check runs on the same cells and again after
  relaxation. `screen_local --relax tensornet` (0.5.0) now means `--check`.
- `relaxer()` can load a potential quietly (process-pool workers).
- The pipeline pages: block S8 lists `scorecard.py --judge megnet` as the component that computes it (its code opens on the
  block page), S6 and S7 list the check and the hull module, and S0's upload adapter is described as joining on the file name.

### Fixed
- The potential loader looked for cached models in the wrong folder for matgl 4 and always said "downloading"; it now
  reports matgl's own cache folder (`~/.cache/matgl/models--materialyze--<name>`).
- Links to a section of a page (`/studies/mp20#accepted`, `/method#run`) now scroll to it once the section has loaded.
- The page preloaded two font files that were never shipped (the server answered with its HTML page); the references are
  gone, so the site loads nothing beyond its own scripts and styles. The look is unchanged.
- Requests to the Materials Project from the new hull module name their client: the API's front end refuses Python's default user
  agent (Cloudflare error 1010), which would have made `--reference mp` fail for every user.

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
