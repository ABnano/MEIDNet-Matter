"""
Benchmark tasks and their reference implementation.

A dataset's protocol (``benchmarks/datasets/<id>.json``, key ``protocol``) fixes the splits, the property targets,
the candidate budget and the metrics of each task. This module computes those metrics for a MEIDNet checkpoint and
for the baselines, and scores a set of candidate structures whatever model produced them, so that any method can
be compared under the same rules.

Tasks of the Perov-5 protocol:

    inverse_design        candidates for property targets in several chemical families, scored for stability
                          (MLIP formation energy), uniqueness, novelty and, where a DFT value exists, the target
    property_prediction   properties predicted from the crystal structure, on the test split
    representation        cross-modal retrieval, latent agreement and a k-nearest-neighbour probe, on the test split

Stability needs an MLIP (MACE-MP-0); it runs in a separate process (``scripts/mlip_stability.py``) so that the
environment holding MACE can differ from the one holding MEIDNet.
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
from dataclasses import dataclass, field

import numpy as np


# ───────────────────────── small helpers ─────────────────────────
def formula_key(formula: str) -> str:
    """Reduced formula used for novelty and uniqueness (BaTiO3, not Ba1Ti1O3)."""
    from pymatgen.core import Composition
    try:
        return Composition(str(formula)).reduced_formula
    except Exception:
        return str(formula).strip()


def _finite(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def regression(y: np.ndarray, p: np.ndarray) -> dict:
    """MAE, RMSE and R2 of predictions p for targets y."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    err = p - y
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {"mae": float(np.abs(err).mean()), "rmse": float(np.sqrt((err ** 2).mean())),
            "r2": float(1.0 - (err ** 2).sum() / ss_tot) if ss_tot > 0 else float("nan")}


def property_metrics(columns: list[str], Y: np.ndarray, P: np.ndarray) -> dict:
    """mae_/rmse_/r2_<column>, plus mae_<column>_nonzero on the materials whose true value is not zero (for
    properties such as a band gap that is zero for most materials, the error that matters for design)."""
    out = {}
    for j, c in enumerate(columns):
        r = regression(Y[:, j], P[:, j])
        out[f"mae_{c}"], out[f"rmse_{c}"], out[f"r2_{c}"] = r["mae"], r["rmse"], r["r2"]
        nz = Y[:, j] != 0
        if 0 < nz.sum() < len(nz):
            out[f"mae_{c}_nonzero"] = float(np.abs(P[nz, j] - Y[nz, j]).mean())
    out["n_evaluated"] = float(len(Y))
    return out


def retrieval(Zc: np.ndarray, Zp: np.ndarray, Y: np.ndarray | None = None) -> dict:
    """Structure -> property retrieval (unit-length latents).

    With Y (the property values), the candidates are the distinct property profiles of the split: materials with
    identical values have identical property latents, so retrieving either is equally right, and counting them
    separately would make the score depend on how ties are broken. Chance level is then 1 / n_profiles."""
    cos = (Zc * Zp).sum(1)
    if Y is not None:
        _, first, inv = np.unique(np.round(np.asarray(Y, dtype=float), 8), axis=0, return_index=True, return_inverse=True)
        inv = np.asarray(inv).reshape(-1)
        S = Zc @ Zp[first].T                               # one column per distinct profile
        own = S[np.arange(len(Zc)), inv]
        n_profiles = len(first)
    else:
        S = Zc @ Zp.T
        own = np.diag(S)
        n_profiles = len(Zp)
    rank = (S > own[:, None]).sum(1)                       # how many profiles beat the material's own
    return {"retrieval_top1": float((rank == 0).mean()), "retrieval_top5": float((rank < 5).mean()),
            "cosine_matched": float(cos.mean()),
            "l2_matched": float(np.sqrt(np.maximum(0.0, 2.0 - 2.0 * cos)).mean()), "n_profiles": float(n_profiles)}


def knn_predict(train_X: np.ndarray, train_Y: np.ndarray, test_X: np.ndarray, k: int = 5,
                metric: str = "cosine", chunk: int = 512) -> np.ndarray:
    """Mean property of the k nearest training points (cosine for unit latents, euclidean for features)."""
    out = np.zeros((len(test_X), train_Y.shape[1]))
    if metric == "cosine":
        A = train_X / np.maximum(np.linalg.norm(train_X, axis=1, keepdims=True), 1e-12)
    else:
        a2 = (train_X ** 2).sum(1)
    for i in range(0, len(test_X), chunk):
        x = test_X[i:i + chunk]
        if metric == "cosine":
            xn = x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)
            d = -(xn @ A.T)
        else:
            d = a2[None, :] - 2 * x @ train_X.T + (x ** 2).sum(1)[:, None]
        idx = np.argpartition(d, kth=min(k, d.shape[1] - 1) - 1, axis=1)[:, :k]
        out[i:i + chunk] = train_Y[idx].mean(1)
    return out


def composition_features(formulas: list[str], elements: list[str] | None = None) -> tuple[np.ndarray, list[str]]:
    """Element-fraction vectors (the usual composition-only representation)."""
    from pymatgen.core import Composition
    comps = []
    for f in formulas:
        try:
            comps.append(Composition(str(f)).fractional_composition.get_el_amt_dict())
        except Exception:
            comps.append({})
    if elements is None:
        elements = sorted({e for c in comps for e in c})
    pos = {e: i for i, e in enumerate(elements)}
    X = np.zeros((len(formulas), len(elements)))
    for r, c in enumerate(comps):
        for e, v in c.items():
            if e in pos:
                X[r, pos[e]] = v
    return X, elements


# ───────────────────────── data and latents ─────────────────────────
def load_split(data_dir: str, split: str, columns: list[str], max_sites: int):
    """Records of one split, read exactly as training reads them (atoms in file order, as in the paper)."""
    from meidnet.config import DataSection, PropertyColumn
    from meidnet.data import load_records, read_table
    table = os.path.join(data_dir, f"{split}.csv")
    if not os.path.exists(table):
        raise SystemExit(f"{table} is missing: run `meidnet download-data` first")
    df = read_table(table)
    dcfg = DataSection(table=table, id_column="material_id", cif_column="cif", align_to_prototype=False,
                       max_sites=max_sites, properties=[PropertyColumn(column=c) for c in columns])
    recs, _ = load_records(df, dcfg, lambda p: p, None, source=f"{split} split")
    formulas = dict(zip(df["material_id"].astype(str), df["formula"].astype(str))) if "formula" in df else {}
    return recs, formulas


SPACES = ("projection", "encoder")


def encode(lm, records, batch: int = 128, space: str = "projection"):
    """Structure latents, property latents and structure-only property predictions (physical units).

    `space` is where the two latents are read: "projection" (after the projection heads: what the decoders read) or
    "encoder" (the normalised encoder outputs, before the heads). A model aligns its modalities in one of the two,
    the one its contrastive loss acts on; measured in the other, the same model can look unaligned."""
    import torch
    import torch.nn.functional as F
    from torch.utils.data import DataLoader
    from meidnet.data import MaterialsDataset
    if space not in SPACES:
        raise ValueError(f"space must be one of {SPACES}")
    model = lm.model.eval()
    dev = next(model.parameters()).device
    Zc, Zp, P = [], [], []
    with torch.no_grad():
        for b in DataLoader(MaterialsDataset(records, lm.stats), batch_size=batch, shuffle=False):
            cv, props = b["crystal_vec"].to(dev), b["props"].to(dev)
            zc, zp, *_ = model.encode_modalities(cv, props)
            P.append(lm.stats.denormalize_tensor(model.property_decoder(zc)).cpu().numpy())
            if space == "encoder":
                zc = F.normalize(model.crystal_encoder(cv)[0], p=2, dim=1)
                zp = F.normalize(model.property_encoder(props), p=2, dim=1)
            Zc.append(zc.cpu().numpy())
            Zp.append(zp.cpu().numpy())
    return np.concatenate(Zc), np.concatenate(Zp), np.concatenate(P)


@dataclass
class ModelEvaluation:
    property_prediction: dict
    representation: dict
    predictions: list[dict] = field(default_factory=list)   # per test material: id, true_/pred_<col>, cos


def evaluate_checkpoint(lm, data_dir: str, k: int = 5, space: str = "projection") -> ModelEvaluation:
    """Property prediction and representation metrics of a checkpoint on the test split; the k-NN probe uses the
    training split's structure latents. The representation is read in `space` (see `encode`); the matched cosine
    in both spaces is reported next to it."""
    cols = list(lm.stats.columns)
    ms = lm.model.max_sites
    train, _ = load_split(data_dir, "train", cols, ms)
    test, _ = load_split(data_dir, "test", cols, ms)
    Zc_tr, _, _ = encode(lm, train, space=space)
    Zc, Zp, P = encode(lm, test, space=space)
    Y = np.array([r.properties for r in test], dtype=float)
    Y_tr = np.array([r.properties for r in train], dtype=float)
    prop = property_metrics(cols, Y, P)
    rep = retrieval(Zc, Zp, Y)
    knn = knn_predict(Zc_tr, Y_tr, Zc, k=k, metric="cosine")
    for j, c in enumerate(cols):
        rep[f"knn_mae_{c}"] = float(np.abs(knn[:, j] - Y[:, j]).mean())
    rep["n_evaluated"] = float(len(test))
    cos = (Zc * Zp).sum(1)
    other = next(s for s in SPACES if s != space)
    Zc_o, Zp_o, _ = encode(lm, test, space=other)
    rep[f"cosine_{space}"] = rep["cosine_matched"]
    rep[f"cosine_{other}"] = float((Zc_o * Zp_o).sum(1).mean())
    preds = [{"id": r.material_id, **{f"true_{c}": float(Y[i, j]) for j, c in enumerate(cols)},
              **{f"pred_{c}": float(P[i, j]) for j, c in enumerate(cols)}, "cos": float(cos[i])}
             for i, r in enumerate(test)]
    return ModelEvaluation(prop, rep, preds)


def evaluate_baselines(data_dir: str, columns: list[str], max_sites: int = 20, k: int = 5) -> dict:
    """Composition k-NN and training-mean baselines (property prediction), the composition k-NN probe and the
    chance level of retrieval (representation)."""
    train, f_tr = load_split(data_dir, "train", columns, max_sites)
    test, f_te = load_split(data_dir, "test", columns, max_sites)
    Y_tr = np.array([r.properties for r in train], dtype=float)
    Y = np.array([r.properties for r in test], dtype=float)
    X_tr, els = composition_features([f_tr.get(r.material_id, "") for r in train])
    X_te, _ = composition_features([f_te.get(r.material_id, "") for r in test], els)
    P_knn = knn_predict(X_tr, Y_tr, X_te, k=k, metric="euclidean")
    P_mean = np.repeat(Y_tr.mean(0, keepdims=True), len(Y), axis=0)
    n = len(Y)
    n_prof = len(np.unique(np.round(Y, 8), axis=0))
    knn_rep = {f"knn_mae_{c}": float(np.abs(P_knn[:, j] - Y[:, j]).mean()) for j, c in enumerate(columns)}
    knn_rep["n_evaluated"] = float(n)
    return {
        "composition_knn": {"property_prediction": property_metrics(columns, Y, P_knn), "representation": knn_rep},
        "train_mean": {"property_prediction": property_metrics(columns, Y, P_mean)},
        "chance": {"representation": {"retrieval_top1": 1.0 / n_prof, "retrieval_top5": min(1.0, 5.0 / n_prof),
                                      "cosine_matched": 0.0, "n_evaluated": float(n), "n_profiles": float(n_prof)}},
        "predictions": {"composition_knn": [{"id": r.material_id, **{f"true_{c}": float(Y[i, j]) for j, c in enumerate(columns)},
                                             **{f"pred_{c}": float(P_knn[i, j]) for j, c in enumerate(columns)}}
                                            for i, r in enumerate(test)]},
    }


# ───────────────────────── inverse design: candidates ─────────────────────────
@dataclass
class Candidate:
    id: str
    variant: str
    target: int                   # 1-based index into the protocol's targets
    targets: dict                 # the target values
    formula: str
    elements: dict
    cif: str                      # path relative to the run folder
    passes_rules: bool = True


def _family(family: str, variant: str):
    from meidnet.family import load_family
    return load_family(family, variant=variant)


def _write_cif(cand_struct, path: str):
    from pymatgen.io.cif import CifWriter
    os.makedirs(os.path.dirname(path), exist_ok=True)
    CifWriter(cand_struct).write_file(path)


def passing_compositions(family: str, variant: str) -> list[dict]:
    """Every composition of the family variant that passes all of its rules, in a fixed order."""
    from meidnet.designspace import enumerate_space
    space = enumerate_space(_family(family, variant), None)
    return [r["e"] for r in space["rows"] if all(r["ok"].values())]


def _materialise(family: str, variant: str, elements: dict, path: str) -> bool:
    """Build the prototype structure of a composition, check the rules, write the CIF."""
    from meidnet.constraints import build_candidate, evaluate
    fam = _family(family, variant)
    cand = build_candidate(fam, elements)
    evaluate(cand, fam.constraints)
    ok = all(r.passed for r in cand.results)
    _write_cif(getattr(cand, "structure", None) or cand.raw, path)
    return ok


def design_random(settings: dict, run_dir: str, seed: int = 0) -> list[Candidate]:
    """Baseline: compositions drawn at random (without replacement) from those that pass the family's rules."""
    out = []
    K, T = settings["per_target"], settings["targets"]
    for vi, variant in enumerate(settings["variants"]):
        pool = passing_compositions(settings["family"], variant)
        rng = random.Random(seed * 1000 + vi)
        picked = rng.sample(pool, min(len(pool), K * len(T)))
        for n, el in enumerate(picked):
            t = n // K + 1
            cid = f"{variant}_T{t}_{n % K + 1}"
            path = os.path.join("cifs", cid + ".cif")
            ok = _materialise(settings["family"], variant, el, os.path.join(run_dir, path))
            out.append(Candidate(cid, variant, t, T[t - 1], _formula_of(settings["family"], variant, el), el, path, ok))
    return out


def _formula_of(family: str, variant: str, elements: dict) -> str:
    from meidnet.constraints import build_candidate
    return build_candidate(_family(family, variant), elements).formula()


def design_screening(lm, settings: dict, objectives: list[dict], run_dir: str) -> list[Candidate]:
    """Baseline: rank the rule-passing compositions by the structure encoder's predictions (the model's forward
    direction, no latent search) and keep the closest to each target, using the generator's own selection score."""
    from meidnet.designspace import enumerate_space
    from meidnet.generate import objective_distance
    out = []
    K, T = settings["per_target"], settings["targets"]
    for variant in settings["variants"]:
        space = enumerate_space(_family(settings["family"], variant), lm)
        rows = [r for r in space["rows"] if all(r["ok"].values())]
        taken = set()
        for t, target in enumerate(T, start=1):
            def score(r):
                return sum(o.get("select_weight", 1.0) * objective_distance(r["p"][o["property"]], target[o["property"]],
                                                                             o.get("select_loss") or o.get("loss", "l2"))
                           for o in objectives)
            n = 0
            for r in sorted(rows, key=score):
                key = tuple(sorted(r["e"].items()))
                if key in taken:
                    continue
                taken.add(key)
                n += 1
                cid = f"{variant}_T{t}_{n}"
                path = os.path.join("cifs", cid + ".cif")
                ok = _materialise(settings["family"], variant, r["e"], os.path.join(run_dir, path))
                out.append(Candidate(cid, variant, t, target, r["f"], r["e"], path, ok))
                if n >= K:
                    break
    return out


def design_meidnet(lm, generation, settings: dict, run_dir: str, log=print, device=None) -> list[Candidate]:
    """MEIDNet's latent search, run per chemical family with the protocol's targets and budget."""
    import torch
    from meidnet.checkpoint import property_ranges
    from meidnet.generate import Designer
    device = device or torch.device("cpu")
    out = []
    for variant in settings["variants"]:
        g = generation.model_copy(deep=True)
        g.family, g.variant = settings["family"], variant
        g.targets = [dict(t) for t in settings["targets"]]
        g.per_target = settings["per_target"]
        g.rounds = settings["max_rounds"]
        g.output_prefix = variant
        fam = _family(settings["family"], variant)
        gen_dir = os.path.join(run_dir, "generation", variant)
        res = Designer(lm, fam, g, device=device, log=log).run(gen_dir, ranges=property_ranges(lm))
        for c in res.saved:
            n = sum(1 for x in out if x.variant == variant and x.target == c.target_index) + 1
            cid = f"{variant}_T{c.target_index}_{n}"
            src = os.path.join(gen_dir, c.file)
            path = os.path.join("cifs", cid + ".cif")
            os.makedirs(os.path.join(run_dir, "cifs"), exist_ok=True)
            with open(src, encoding="utf-8") as fi, open(os.path.join(run_dir, path), "w", encoding="utf-8", newline="\n") as fo:
                fo.write(fi.read())
            ok = all(r.get("passed", True) for r in c.constraint_results)
            out.append(Candidate(cid, variant, c.target_index, settings["targets"][c.target_index - 1], c.formula,
                                 dict(c.elements), path, ok))
    return out


def write_candidates(cands: list[Candidate], path: str) -> None:
    keys = sorted({k for c in cands for k in c.targets})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "variant", "target", *[f"target_{k}" for k in keys], "formula", "elements", "cif", "passes_rules"])
        for c in cands:
            w.writerow([c.id, c.variant, c.target, *[c.targets.get(k, "") for k in keys], c.formula,
                        json.dumps(c.elements, sort_keys=True), c.cif.replace(os.sep, "/"), c.passes_rules])


def read_candidates(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ───────────────────────── inverse design: scoring ─────────────────────────
ANIONS = {"O", "N", "F", "Cl", "Br", "I", "S", "Se", "Te", "H", "C", "P", "As", "Sb"}


def site_key(elements: dict) -> str | None:
    """A|B|X key of an ABX3 composition with one anion, from a candidate's site groups."""
    if all(g in elements for g in ("A", "B", "X")):
        return f"{elements['A']}|{elements['B']}|{elements['X']}"
    return None


def _structure_site_key(structure) -> str | None:
    """A|B|X key of a 5-atom cubic perovskite cell: the anion is the element on three sites, B the cation closest
    to an anion (centre of the octahedron, at a/2) and A the other cation (at a/sqrt 2)."""
    species = [str(sp) for sp in structure.species]
    anion_sites = [i for i, e in enumerate(species) if e in ANIONS]
    cations = [i for i in range(len(species)) if i not in anion_sites]
    if len(species) != 5 or len(anion_sites) != 3 or len({species[i] for i in anion_sites}) != 1 or len(cations) != 2:
        return None
    d = [min(structure.get_distance(i, j) for j in anion_sites) for i in cations]
    b = cations[int(np.argmin(d))]
    a = cations[1 - int(np.argmin(d))]
    return f"{species[a]}|{species[b]}|{species[anion_sites[0]]}"


def known_by_site(data_dir: str, column: str, cache: str | None = None) -> dict[str, list[float]]:
    """A|B|X -> DFT values of `column` over all splits, for the single-anion entries of the dataset. Perov-5 holds
    both site orderings of many compositions (BaTiO3 with Ba on A and with Ti on A), with very different band gaps,
    so the check matches sites, not formulas. Cached as JSON because it parses every CIF once."""
    if cache and os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    import pandas as pd
    from pymatgen.core import Structure
    out: dict[str, list[float]] = {}
    for split in ("train", "val", "test"):
        p = os.path.join(data_dir, f"{split}.csv")
        if not os.path.exists(p):
            continue
        df = pd.read_csv(p, usecols=["cif", column])
        for cif, v in zip(df["cif"], df[column]):
            try:
                key = _structure_site_key(Structure.from_str(cif, fmt="cif"))
            except Exception:
                key = None
            if key:
                out.setdefault(key, []).append(float(v))
    if cache:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(out, f, sort_keys=True)
    return out


def known_values(data_dir: str, column: str) -> dict[str, list[float]]:
    """Reduced formula -> DFT values of `column` over all splits (the materials whose property is known)."""
    import pandas as pd
    out: dict[str, list[float]] = {}
    for split in ("train", "val", "test"):
        p = os.path.join(data_dir, f"{split}.csv")
        if os.path.exists(p):
            df = pd.read_csv(p, usecols=["formula", column])
            for f, v in zip(df["formula"], df[column]):
                out.setdefault(formula_key(f), []).append(float(v))
    return out


def training_formulas(data_dir: str) -> set[str]:
    import pandas as pd
    df = pd.read_csv(os.path.join(data_dir, "train.csv"), usecols=["formula"])
    return {formula_key(f) for f in df["formula"]}


def dataset_formulas(data_dir: str) -> set[str]:
    """Every composition of the data set (training, validation and test splits): the novelty reference. A candidate
    is novel when the data set does not contain it, whichever part of it a model was trained on."""
    import pandas as pd
    out = set()
    for split in ("train", "val", "test"):
        p = os.path.join(data_dir, f"{split}.csv")
        if os.path.exists(p):
            out |= {formula_key(f) for f in pd.read_csv(p, usecols=["formula"])["formula"]}
    return out


def score_inverse_design(candidates: list[dict], stability: dict[str, dict], settings: dict, train_formulas: set[str],
                         known: dict[str, list[float]], gap_column: str = "dir_gap") -> tuple[dict, list[dict]]:
    """Metrics of a candidate set under the protocol. The SUN rate is over the requested budget
    (variants x targets x per_target): a candidate that was not delivered counts as a failure. Stable, unique and
    novel are fractions of the delivered candidates.

    stability: candidate id -> {"dHf": float, "artefact": bool} (from scripts/mlip_stability.py).
    known: A|B|X site key (or reduced formula) -> DFT values of the gap column (see known_by_site)."""
    budget = settings.get("budget") or len(settings["variants"]) * len(settings["targets"]) * settings["per_target"]
    thr, tol = settings["stability_threshold"], settings["gap_tolerance"]
    seen, rows = set(), []
    n_valid = n_unique = n_novel = n_stable = n_sun = known_n = hits = 0
    dhf = []
    for c in candidates:
        key = formula_key(c["formula"])
        valid = str(c.get("passes_rules", "True")) in ("True", "true", "1")
        unique = key not in seen
        seen.add(key)
        novel = key not in train_formulas
        st = stability.get(c["id"], {})
        e = st.get("dHf")
        artefact = bool(st.get("artefact", True)) if st else True
        stable = (not artefact) and _finite(e) and e <= thr
        if _finite(e) and not artefact:
            dhf.append(e)
        sun = valid and stable and unique and novel
        target_gap = float(c.get(f"target_{gap_column}", "nan") or "nan")
        el = c.get("elements") or {}
        if isinstance(el, str):
            try:
                el = json.loads(el)
            except ValueError:
                el = {}
        dft = known.get(site_key(el) or key)
        hit = None
        if dft is not None and math.isfinite(target_gap):
            known_n += 1
            hit = min(abs(v - target_gap) for v in dft) <= tol
            hits += int(hit)
        n_valid += valid
        n_unique += unique
        n_novel += novel
        n_stable += stable
        n_sun += sun
        rows.append({**c, "formula_key": key, "valid": valid, "unique": unique, "novel": novel,
                     "dHf": e if _finite(e) else None, "stable": stable, "sun": sun,
                     "dft_" + gap_column: (min(dft, key=lambda v: abs(v - target_gap)) if dft else None), "dft_hit": hit})
    nd = max(len(candidates), 1)
    metrics = {
        "sun_rate": n_sun / budget, "stable_rate": n_stable / nd, "unique_rate": n_unique / nd,
        "novel_rate": n_novel / nd, "valid_rate": n_valid / budget,
        "dhf_median": float(np.median(dhf)) if dhf else float("nan"),
        "dft_hit_rate": hits / known_n if known_n else float("nan"), "dft_known": float(known_n),
        "n_delivered": float(len(candidates)), "n_sun": float(n_sun), "n_budget": float(budget),
    }
    return metrics, rows


def read_stability(path: str) -> dict[str, dict]:
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                e = float(r.get("dHf", "nan"))
            except ValueError:
                e = float("nan")
            out[r["id"]] = {"dHf": e, "artefact": str(r.get("artefact", "True")) in ("True", "true", "1"),
                            "converged": str(r.get("converged", "False")) in ("True", "true", "1")}
    return out


__all__ = ["formula_key", "regression", "property_metrics", "retrieval", "knn_predict", "composition_features",
           "load_split", "encode", "evaluate_checkpoint", "evaluate_baselines", "Candidate", "passing_compositions",
           "design_random", "design_screening", "design_meidnet", "write_candidates", "read_candidates",
           "known_values", "known_by_site", "site_key", "training_formulas", "dataset_formulas", "score_inverse_design", "read_stability",
           "SPACES"]
