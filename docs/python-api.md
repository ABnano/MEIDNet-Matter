# MEIDNet Matter from Python

The site's three stages, Explore → Train → Generate, and the Perov-5 project are one HTTP API (`/docs` on any server
lists every route). `matter.client.Matter` is a thin client for it: plain dicts in and out, the standard library only,
one session per client. It is part of the `meidnet-matter` package:

```bash
pip install --extra-index-url https://download.pytorch.org/whl/cpu "meidnet-matter"
```

```python
from matter.client import Matter

m = Matter("https://babu09-meidnet-matter.hf.space")   # the shared server; or http://127.0.0.1:8000 for your own
m.health()                                              # {'version': ..., 'model_loaded': True, 'judge_ready': True, ...}
```

## Explore

```python
points = m.explore()                 # every training material: material_id, formula, x, y (the latent map), heat_all, dir_gap, site_key
gapped = [p for p in points if p["dir_gap"] > 0]
one = m.material(gapped[0]["material_id"], k=6)
one["properties"]                    # {'heat_all': ..., 'dir_gap': ...}  reference values (DFT, PBE)
one["cell"]                          # {'lattice': [[a,0,0],[0,a,0],[0,0,a]], 'sites': [{'element': 'Sr', 'frac': [...]}, ...]}
one["neighbours"]                    # the nearest training materials in the full latent space, with cosine and properties
one["encoder_prediction"]            # the default model's reading of the same structure
```

`m.dataset()` gives the histograms and element counts the site draws; `m.studies()`, `m.study("mp20")`,
`m.checkpoints()` and `m.blocks()` give the research material.

## Train Lite

A real MEIDNet training on a fixed subset (1,500 Perov-5 materials, 30% with a non-zero band gap), the demo's own recipe,
10, 20 or 50 epochs, on the server's two CPU cores. The result is a model trained from scratch, measured on 500 validation
materials it never saw, next to the demo's full model measured on the same ones. It never drives generation on the server.

```python
m.train_options()                    # the subset, the recipe, the reference, the limits
job = m.train(epochs=20, seed=0)     # one job at a time per session on the shared server
job = m.wait(job, every=1)           # polls until done

for h in job["history"]:             # one record per epoch
    print(h["epoch"], h["loss"], h["val_mae"], h["alignment_cosine"])

r = job["result"]
r["against_spread"]                  # per property: MAE, the spread, their ratio (good < 0.25, fair < 0.5), the full model's MAE
r["predictions"]                     # columns and rows: material, formula, reference values, predicted values (500 rows)
r["map"]                             # the validation materials placed by the small model (two principal components)
r["full_training_command"]           # the same recipe at full size, on your computer

m.download(m.urls.train_model(job["job_id"]), "lite.pt")          # a MEIDNet checkpoint: meidnet.checkpoint.load_checkpoint
m.download(m.urls.train_config(job["job_id"]), "config.yaml")     # the recipe with your epochs and seed
m.download(m.urls.train_predictions(job["job_id"]), "pred.csv")
```

Then, at full size, on your own computer or cluster (the Method page has every step):

```bash
meidnet download-data            # the Perov-5 CSVs
# in config.yaml: data.table and data.val_table -> the CSVs, training.epochs: 200
meidnet train config.yaml
```

## Generate

```python
gen = m.wait(m.generate(targets=[2.0], per_target=4))             # cells for a 2.0 eV band gap, read by two models
for c in gen["candidates"]:
    print(c["formula"], c["label_structure_eV"], c["judge_eV"], c["statuses"], c["geometry"])
m.download(m.urls.generate_cif(gen["job_id"], gen["candidates"][0]["candidate_id"]), "first.cif")
m.download(m.urls.generate_zip(gen["job_id"]), "cells.zip")       # every CIF, the table, the record and the relax command
```

The readings are two machine-learning estimates of the PBE band gap MP-20 records: the generator's own label read from the
returned cell, and MEGNet, a second model that played no part in generation. Relaxation and stability are not computed on
the server; the zip carries the command that relaxes the cells locally with two potentials.

## The Perov-5 project (search within a family)

```python
goal = m.project()["default_goal"]                   # a 2.0 ± 0.3 eV band gap, formation enthalpy at most 1 eV/atom, lead excluded
report = m.readiness(goal)                           # verdict, the six indicators, whether an exploratory acknowledgement is needed
run = m.wait(m.search(goal, acknowledge_exploratory=report["exploratory_required"]))
cands = m.candidates(run["run_id"])                   # versioned candidate records, with their evidence
m.download(m.urls.bundle(run["run_id"]), "run.zip")   # the run bundle: goal, configuration, metrics, CIFs, manifest with hashes
```

## Errors and sessions

Every non-2xx answer raises `matter.client.MatterError` with `status`, `code` and `message` (the same envelope the site
shows). On the shared server a session runs one job at a time (`busy`, with `retry_after_s`), finished jobs are kept
for an hour after their last use (`gone` afterwards), and a restart starts empty (`run_not_found`). A `Matter(...)`
instance is one session; pass `session=` to continue one.
