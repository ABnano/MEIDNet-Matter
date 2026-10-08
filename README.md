<p align="center"><img src="docs/assets/screenshot.png" alt="MEIDNet Matter: the readiness report and the candidates of a search" width="820"></p>

# MEIDNet Matter

**From your materials data to candidate structures.**

MEIDNet Matter is a multimodal inverse-design workbench for crystalline materials. A researcher brings crystal structures and properties; Matter reports what the data and the model support (the Design Readiness report), then runs a constrained, property-conditioned search and returns candidate structures with their evidence and provenance. The scientific engine is [MEIDNet](https://github.com/ABnano/MEIDNet), imported as a package; the sibling platform [MEIDNet Prism](https://babu09-meidnet.hf.space/) is where to learn the method, reproduce the results and benchmark models.

[![ci](https://github.com/ABnano/MEIDNet-Matter/actions/workflows/ci.yml/badge.svg)](https://github.com/ABnano/MEIDNet-Matter/actions/workflows/ci.yml)
[![Space](https://img.shields.io/badge/%F0%9F%A4%97%20Space-MEIDNet--Matter-4f46e5)](https://huggingface.co/spaces/Babu09/MEIDNet-Matter)
[![engine](https://img.shields.io/badge/engine-meidnet%202.2-9333ea)](https://pypi.org/project/meidnet/)
[![licence](https://img.shields.io/badge/licence-MIT-0a7d0a)](LICENSE)
[![paper](https://img.shields.io/badge/npj%20Comput.%20Mater.-2026-1c5cab)](https://doi.org/10.1038/s41524-026-02153-3)

Matter currently searches property-conditioned candidates within supported structural families. Free-geometry crystal generation is planned as additional design backends mature.

## Try it

**Live:** https://babu09-meidnet-matter.hf.space/ — open the Perov-5 demo project, set a band-gap target, exclude lead, read the readiness report, run the search (about a minute on the shared CPU), open a candidate, download its CIF or the whole run bundle.

**Mirror for any network:** https://abnano.github.io/MEIDNet-Matter/ — the same site on GitHub Pages, for networks that block
`*.hf.space` (public Wi-Fi often does: the Space then shows a grey page). Everything that reads works there (studies, the
staged pipeline with its code, the method, checkpoints, every structure file); generation and the demo search point to the
Space, and the mirror says whether the Space is reachable from your network. It is rebuilt for every release
(`.github/workflows/pages.yml`: `npm run build:mirror`, then `scripts/build_mirror.py`). Prism has its own mirror at
https://abnano.github.io/MEIDNet/.

## What it does, in this version

The home page opens on a worked result: a real accepted structure with both of its readings, a small requested-versus-delivered
plot, an animated six-step walkthrough, and a rolling strip of the structures the generator delivered. From there: **Pipeline**
(the ten blocks with their bands and code), **Studies** (Perov-5, Materials Project perovskites, an external upload, MP-20, with
checkpoints), **Generate** (live band-gap generation on MP-20 with two independent readings per cell, 3D cards and an evidence
map) and **Method** (mechanism, strengths, limits, and the commands that run the same stages on your own data: whatever route produced your candidates, one check gives them the qualified judge, relaxation by two potentials, both readings again on the relaxed cells, the energy above the hull with one potential for every phase, novelty, and a class: new, rediscovered, or contradicted by your data's own value). The Perov-5
demo project below is the original flow and is kept as it was, with one change: every candidate now shows the
**structure-based prediction** first and the **search value** beside it, and says which of the two supports the target.


| Step | What you get |
|---|---|
| **Goal** | Target value, range or bound per property; family and variant; excluded elements and presets; the chemistry rules with their limits; the search budget. |
| **Readiness** | Six indicators before any search: prediction error of each targeted property on the evaluation split (a published-model diagnostic when the checkpoint saw that split in training), cross-modal retrieval in both directions, what the decoder recovers, where the target sits in the training distribution and how much data lies around it, how many structures share the target window, and whether the family's elements occur in the data. One verdict; a "not recommended" target can still be searched in exploratory mode. |
| **Candidates** | A search with the engine; every candidate carries the structure-based prediction and the search value of each property, each with its domain status, and what the evidence supports, the rules with values and windows, the encoder's own prediction of the composition and whether it agrees with the search's, the nearest training materials with their DFT values, the training data around the prediction, whether the dataset already holds it, the stability stage, and a "why" sentence that repeats these facts. Table, cards and map; filters; comparison side by side. |
| **One target, many structures** | When the search has finished, candidates are grouped into clusters of similar encoder latents (cosine ≥ 0.9). The cards view shows the clusters; the "Prioritise" control orders candidates by target accuracy, diversity (one per cluster first), stability, novelty, search score, encoder agreement or order found. |
| **Validation ladder** | Six stages: Generated · Chemistry checked · MLIP screened · DFT relaxed · DFT property confirmed · Experimentally tested. Every candidate records the highest stage it reached and the result of each stage; this version records stages 0 and 1, the later ones are your own steps and keep their place in the record. |
| **Export** | CIF per candidate, the candidate table, the candidate record (versioned: `meidnet-matter/candidate-record/1`, JSON Schema at `/api/schema/candidate-record`), and the run bundle: goal, engine configuration, metrics, readiness, candidates, CIFs, `targets.csv`, the record schema, a manifest with file hashes. |
| **Score on Prism** | The bundle's `cifs/` and `targets.csv` are the input of `meidnet score` (MEIDNet 2.3.1 or later): validity, uniqueness, novelty, diversity, distribution and the conditional metrics, named as in LeMat-GenBench. The export page gives the commands; [the metrics are defined on Prism](https://babu09-meidnet.hf.space/docs/benchmarks/compatibility.html). |

The demo project: cubic ABX₃ perovskites of the Perov-5 dataset, the published MEIDNet model, the direct band gap and the formation enthalpy. By the engine's thresholds the published model is weak on both properties on held-out data, so the demo opens its searches in exploratory mode by design; [docs/scientific-scope.md](docs/scientific-scope.md) has the numbers and what the evidence shows instead.

Coming next (Phase 1): upload your own property table and CIF files, a data-quality report, training in the browser, readiness on your own held-out data, the same search with your model; then imports from Materials Project and NOMAD, a bring-your-own-model backend, and synthesis context linked from existing resources. [docs/data-format.md](docs/data-format.md) describes the upload layout, the candidate record and `targets.csv`.

Matter is one half of the MEIDNet ecosystem: [MEIDNet Prism](https://babu09-meidnet.hf.space/) is where the method is learned, benchmarked and developed ([the ecosystem](https://babu09-meidnet.hf.space/docs/ecosystem.html)); Matter is where a dataset becomes candidates.

## Run it yourself

Supported: Linux, macOS, and Windows through WSL (Windows 11 with Smart App Control blocks unsigned wheels, so use WSL
there). One command installs the engine and the application from the release, with CPU torch; the last line proves it:

```bash
pip install --extra-index-url https://download.pytorch.org/whl/cpu \
  "meidnet @ https://github.com/ABnano/MEIDNet-Matter/releases/latest/download/meidnet-2.4.0.dev2-py3-none-any.whl" \
  "meidnet-matter[judge] @ https://github.com/ABnano/MEIDNet-Matter/releases/latest/download/meidnet_matter-0.6.0-py3-none-any.whl"
python -c "import meidnet, matter, matgl; print(meidnet.__version__, matter.__version__)" && meidnet --version
```

From a clone instead (the engine first, never from PyPI, which only has the older 2.2.0):

```bash
git clone https://github.com/ABnano/MEIDNet-Matter && cd MEIDNet-Matter
pip install --extra-index-url https://download.pytorch.org/whl/cpu ./engine && pip install -e ".[dev,judge]"
python scripts/fetch_assets.py                 # the checkpoints the studies use, each verified against its checksum
cd frontend && npm ci && npm run build && cd ..
python -m uvicorn matter.app:app --port 8000   # http://127.0.0.1:8000/
```

The potentials used for relaxation (TensorNet, CHGNet) are fetched from the Hugging Face Hub on first use; the classic
transfer is used by default because the Hub's Xet transfer can stall silently on some networks (`HF_HUB_DISABLE_XET`).
The known-good versions of every dependency are the ones in [deploy/requirements.txt](deploy/requirements.txt), which the
public Space runs.

Nothing leaves your computer. Details, the Docker image and the Space deploy: [docs/deployment.md](docs/deployment.md). What happens to your data on the shared Space: [docs/privacy.md](docs/privacy.md).

## How it works

Data → readiness → shared latent space → search → candidates. MEIDNet learns one latent space shared by crystal structures and their properties and searches it for compositions that hit property targets while obeying the chemistry rules of a material family; Matter adds the readiness report before the search, the evidence next to every candidate, the run manifest, and the interface. The backend (`matter/`, FastAPI) calls the `meidnet` package through one backend interface so that other design engines can be added; the frontend (`frontend/`, React + TypeScript) is built into `matter/static` and served by the backend.

## Development

```bash
python -m pytest -q                                          # backend; -m "not slow" skips the model and the tiny search
cd frontend && npm run typecheck && npm test && npm run lint  # frontend
node scripts/smoke_browser.mjs http://127.0.0.1:8000 build/smoke   # the browser walk-through against a running server
```

## Citation

If you use MEIDNet Matter, please cite the MEIDNet paper and the software ([CITATION.cff](CITATION.cff)):

> A. Babu, R. Almeida Gouvêa, P. Vandergheynst, G.-M. Rignanese, MEIDNet: Multimodal generative AI framework for inverse materials design, npj Computational Materials 12, 287 (2026). doi:10.1038/s41524-026-02153-3

Data: Perov-5 (Castelli et al. 2012) in the CDVAE split (Xie et al. 2022). Licence: MIT. Author: Anand Babu.
