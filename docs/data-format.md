# Data format (Phase 1, coming next)

This version does not take uploads. The layout below is what Phase 1 will read; it is the layout the engine already accepts (`meidnet check`).

## A table with a CIF column

A CSV or Excel file with one row per material:

| column | content |
|---|---|
| `material_id` | a unique id (any text) |
| `cif` | the structure as CIF text |
| one column per property | a number; the unit is given when the columns are mapped |

## A table and a folder of CIF files

A ZIP with `properties.csv` (`material_id` and the property columns) and `structures/<material_id>.cif`.

## What Matter will report after reading it

The number of rows, the usable structures, the properties detected and their distributions, missing values, duplicated ids, equivalent structures, malformed CIFs, cells with more than the model's site limit, partially occupied sites, elements present, and which family prototype the cells match. Every excluded row comes with its reason, in a downloadable table; nothing is cleaned silently.

## Caps on the shared Space

Phase 1 will state them here (rows, CIF size, archive size, training epochs and time); locally there are none.

# What leaves Matter (this version)

## The candidate record

Every candidate is a JSON document with `"schema": "meidnet-matter/candidate-record/1"`. `GET /api/schema/candidate-record` returns its JSON Schema; `GET /api/runs/{run_id}/candidates/{candidate_id}/record.json` downloads one record; the run bundle holds the schema as `candidate-record.schema.json`. The blocks:

| block | content |
|---|---|
| `identity` | formula, reduced formula, site key, element per site, family and variant, backend, model id |
| `structure` | the CIF path in the bundle, lattice, sites, a chemiscope block |
| `properties` | per property: label, unit, objective, target, predicted value, difference, training range, domain status with its reason, window, evidence label, the dataset's DFT value when the material is in it |
| `constraints` | every chemistry rule with its value, window and result |
| `model_evidence` | the encoder's own prediction and its agreement with the search, nearest training materials, local density, the latent |
| `novelty` | the dataset check by reduced formula and site key, against the whole dataset and the training split |
| `stability` | the validation ladder: `stage` (0–5), `status`, `label`, `stages`, `next`, and `records` (one per stage reached, with method and outcome) |
| `cluster` | the cluster of similar candidates (id, size, leader, rank, cosine to the leader), assigned when the search finished |
| `provenance` | Matter and meidnet versions, git commit, model sha256, dataset id and fingerprint, goal hash, run id, mode, created |
| `why` | the sentence that repeats these facts |

A later version of the record adds fields and never changes the meaning of an existing one; the version number in the schema id changes otherwise.

## targets.csv

One row per candidate CIF of the bundle, in the layout that `meidnet score` (MEIDNet 2.3.1 or later) reads:

| column | content |
|---|---|
| `file` | `cifs/<candidate_id>.cif`, named without the folder |
| `<property>_target` | the point target of a value objective; empty for a range, a bound or an untargeted property |
| `<property>_min`, `<property>_max` | the requested window: value ± tolerance, the range's ends, or the bound alone ("at most 1.0 eV/atom" fills only `_max`) |
| `<property>_value` | the value Matter reports: the search's prediction in this version |
| `source` | `predicted (<model_id>)` here; `dft` or `experiment` once you have validated the structure |
| `validation_stage`, `cluster` | the stage reached and the cluster id |

A property with a window counts as a success when its value lies inside the window; one with only a point target counts as a success within the tolerance given to `meidnet score` (5 % of the reference's range by default).

```bash
pip install "meidnet>=2.3.1"
meidnet download-data
meidnet score cifs/ --targets targets.csv --reference data/perov5
```

Replace the `<property>_value` column with your DFT or measured values and set `source` accordingly to score the candidates against what they actually do rather than what was predicted.
