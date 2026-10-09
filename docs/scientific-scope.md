# Scientific scope

Matter generates crystal structures without a template (live, on MP-20) and searches within a structural family (the Perov-5 demo); the same stages run on your own data locally.

## What this version does

The Perov-5 demo project, end to end:

| Step | What happens |
|---|---|
| Goal | Per property: a target value with a tolerance, a range, a lower or upper bound, or "maximize"/"minimize" (run as a bound at the 1st or 99th percentile of the training values). Family and variant, excluded elements and presets, rule limits, rules switched off, the search budget. |
| Readiness | Six indicators measured before any search: held-out prediction error of each targeted property (with the engine's thresholds: good below 0.25 of the spread, fair below 0.5, weak above), cross-modal retrieval in both directions, structural recoverability of the decoder, the target's position in the training distribution and the amount of training data around it, the number of distinct structures that share the target window, and the coverage of the chosen family's elements in the data. One verdict: supported, caution, or not recommended; the last still allows an exploratory search. |
| Search | The engine's latent-space search (meidnet.generate.Designer): starts from the target's property latent, optimises a population of latents, decodes compositions onto the family's prototype, evaluates every chemistry rule and the target windows, keeps unique candidates. |
| Candidates | For every candidate: predicted values against the target with the same domain status as the readiness report, the rules with their values and windows, the encoder's own prediction of the decoded composition and whether it agrees with the search's, the three nearest training materials with their DFT values, the amount of training data around the prediction, whether the dataset already holds the composition (by reduced formula and by A|B|X site assignment), the engine's flags, and a "why" sentence that only repeats these facts. |
| Export | CIF per candidate, the candidate table as CSV (the domain status and the flags travel with it), the candidate record as JSON, and the run bundle with a manifest and file hashes. |

## The demo's models and data

* **Models:** two MEIDNet models of the same two properties, the direct band gap (eV, training range 0–7.9) and the formation enthalpy (eV/atom, training range −0.64–5.16), each with a 128-dimensional latent space.
  * `desc-full-sp4`, the default: retrained on the 11,356-material training split with element descriptors and four times the weight on reading the properties from the structure, cells of up to 5 sites. Of the 15 checkpoints trained on the training split (six new desc-full variants and nine existing models), it reads the band gap best on the validation split; the rule was written down before the new ones finished training. On the 3,785 held-out test materials its band-gap error is 0.41 of the spread on the materials with a non-zero gap (fair) and its formation-enthalpy error 0.08 of the spread (good). The price of the choice: from the joint encoding it rebuilds the exact composition of 20 % of held-out structures (desc-full 58 %) and matches 17 % of them (50 %), which is one of the reasons the default goal is graded CAUTION; the inverse path, from a property target to a structure, is unchanged (38.9 % of sites).
  * `meidnet-2k`, selectable: the published Perov-5 model of the MEIDNet paper (a MEIDNet v1 checkpoint, 2.8 MB), cells of up to 20 sites. It was trained on all 18,928 materials, so its numbers on the test split are optimistic; the report says so.
* **Data:** Perov-5 (Castelli et al. 2012) in the CDVAE split (Xie et al. 2022): 11,356 / 3,787 / 3,785 materials. 96 % of the band gaps are exactly 0 eV, so the readiness tests for the band gap use the 441 training materials with a non-zero gap. Perov-5 contains no Cl, Br or I: a halide search runs on anions the model never saw, and the family-support indicator says so. 94 % of the materials share their exact property pair with at least ten others: one target, many structures.
* **With the default model the demo's default goal** (a 2.0 ± 0.3 eV band gap, formation enthalpy at most 1 eV/atom, lead excluded) is graded CAUTION and runs as a normal search: band-gap MAE 0.63 eV against a spread of 1.56 eV on the non-zero gaps (fair), formation-enthalpy MAE 0.057 eV/atom against 0.739 (good), and the decoder rebuilds held-out structures poorly (above).
* **By the engine's thresholds the published model is weak on both properties** (band-gap MAE 1.68 eV against 1.56 eV; formation-enthalpy MAE 0.404 eV/atom against 0.739), while the five nearest training structures in the latent space read the formation enthalpy well (0.021 eV/atom) but not the non-zero band gaps (1.03 eV against 1.56, weak). With it the same goal is not recommended; since no other target changes a model's weakness, the page then leads with the exploratory search: the chemistry rules apply as usual, the predicted values are labelled unreliable, and the evidence next to each candidate (the encoder's own prediction, the nearest training materials with their DFT values) shows where the search and the data disagree.

## What this version does not do

* No upload in the browser: training, the scorecard and generation on your own data run on your own computer (the Method page has the commands).
* The Perov-5 demo searches within a family: its candidates are compositions placed on the family's prototype (cubic ABX₃ or A₂BB′X₆). Generation without a template runs live on MP-20 (Generate).
* No uncertainty per prediction (the model has no uncertainty head; the field is present and says so).
* No stability screening, DFT or experiment here: every candidate stands at stage 0 ("Generated") or stage 1 ("Chemistry checked", every rule of the family passed) of the six-stage validation ladder (Generated · Chemistry checked · MLIP screened · DFT relaxed · DFT property confirmed · Experimentally tested). The later stages are the user's own steps; the run bundle's `cifs/` and `targets.csv` are laid out for `meidnet screen` and for `meidnet score` on Prism, and the candidate record keeps a place for each stage's result.
* Clusters are a grouping of the search's own candidates by encoder latent (cosine ≥ 0.9), not a statement about polymorphs or phase stability: two candidates in one cluster are alternatives the model cannot tell apart well, not variants of one material.
* The seed-3 re-run of the paper's alignment training is not offered: measured the way this search uses it (after the projection heads) its property decoder gives a formation-enthalpy error of 5.3 eV/atom. It aligns before the heads, and a readiness measured in its own space is future work.

## Evidence labels

The labels are literal and never merged: "Predicted" (a model estimate), "Rule passed" / "Rule failed" (a deterministic chemistry check), "DFT-computed (Perov-5)" (a value of the dataset), "Not found in the Perov-5 dataset (18,928 materials)" / "Found in …" (the novelty check, naming what was checked), and the stability stages "Not screened", "ML-potential screened", "DFT relaxed", "DFT hull evaluated", "Experimentally tested".

## References

* A. Babu, R. Almeida Gouvêa, P. Vandergheynst, G.-M. Rignanese, MEIDNet: Multimodal generative AI framework for inverse materials design, npj Computational Materials 12, 287 (2026). doi:10.1038/s41524-026-02153-3
* I. E. Castelli et al., New cubic perovskites for one- and two-photon water splitting using the computational materials repository, Energy Environ. Sci. 5, 9034 (2012).
* T. Xie, X. Fu, O.-E. Ganea, R. Barzilay, T. Jaakkola, Crystal diffusion variational autoencoder for periodic material generation, ICLR (2022).
