"""Build the demo project's artefacts from the Perov-5 CSVs and the model files.

    python scripts/build_demo.py --data-dir data/perov5 --out examples/perov5 \
        --model meidnet-2k=checkpoints/dual_autoencoder_clip_earlyfusion_propertyaware_2k.pth \
        --model meidnet-alignment-seed3=checkpoints/meidnet_paper_rerun_seed3.pth

Written (all JSON with sorted keys, no NaN, LF; deterministic except manifest.json's computed_at):
    dataset.json                  fingerprints, rows, per-property statistics and histograms, element counts,
                                  family coverage, property profiles, the ambiguity grid
    materials.csv.gz              one row per material: id, split, formula, reduced formula, A|B|X site key, properties
    latents_train.<model>.npz     structure latents of the training split (projection space, float16), with ids,
                                  the encoder-side predictions and the property columns
    readiness/<model>.json        held-out evaluation on the test split (the same code path as meidnet's benchmark),
                                  reverse retrieval, structural recoverability, caveats
    models.json  project.json  manifest.json

The metrics use meidnet's own functions (benchmark.encode, property_metrics, retrieval, knn_predict) on the same
records; the structure-matching loop follows scripts/reproduce_alignment.py of the MEIDNet repository.
"""
from __future__ import annotations

import datetime as _dt
import gzip
import hashlib
import json
import os
from collections import Counter

import numpy as np

LABELS = {"heat_all": ("Formation energy", "eV/atom"), "dir_gap": ("Direct band gap", "eV")}
PERCENTILES = (1, 5, 10, 25, 50, 75, 90, 95, 99)
FAMILIES = {"perovskite_abx3": ["oxide", "halide", "chalcogenide", "nitride"], "double_perovskite_a2bbx6": ["halide", "oxide"]}
SCOPE = ("This demo searches property-conditioned candidates within a structural family; generation without a template "
         "runs live on MP-20, and the same stages run on your own data locally.")
SPLITS = ("train", "val", "test")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1, sort_keys=True, allow_nan=False, ensure_ascii=False)
        f.write("\n")


# ───────────────────────── materials ─────────────────────────
def read_materials(data_dir: str, columns: list[str], max_sites: int | list[int], limit: int | None, log=print) -> tuple[list, dict]:
    """Every material of every split, parsed once: a meidnet Record per model size (max_sites) plus the facts Matter
    indexes (site key, elements).  A material that does not fit every size is skipped, so every model sees the same rows."""
    import pandas as pd
    from meidnet.benchmark import _structure_site_key, formula_key
    from meidnet.data import Record, featurize, parse_structure

    sizes = list(dict.fromkeys([max_sites] if isinstance(max_sites, int) else max_sites))
    rows, skipped = [], Counter()
    for split in SPLITS:
        path = os.path.join(data_dir, f"{split}.csv")
        if not os.path.exists(path):
            raise SystemExit(f"{path} is missing: run `python -m meidnet.cli download-data` first")
        df = pd.read_csv(path, usecols=["material_id", "cif", "formula", *columns])
        if limit:
            df = df.head(limit)
        for mid, cif, formula, *props in df[["material_id", "cif", "formula", *columns]].itertuples(index=False):
            props = np.array(props, dtype=float)
            if not np.all(np.isfinite(props)):
                skipped["missing property value"] += 1
                continue
            try:
                s = parse_structure(cif_text=cif)
                dense = {ms: featurize(s, ms) for ms in sizes}
            except Exception as e:
                skipped[f"structure could not be processed ({type(e).__name__})"] += 1
                continue
            try:
                key = _structure_site_key(s)
            except Exception:
                key = None
            rows.append({"material_id": str(mid), "split": split, "formula": str(formula),
                         "reduced_formula": formula_key(formula), "site_key": key or "",
                         "elements": sorted(str(e) for e in s.composition.elements),
                         # the cell itself, compactly: every Perov-5 cell is cubic with five sites (checked at build time)
                         "cell": {"a": float(s.lattice.a), "species": [str(site.specie.symbol) for site in s],
                                  "frac": [[round(float(x), 4) for x in site.frac_coords] for site in s],
                                  "cubic": bool(abs(s.lattice.a - s.lattice.b) < 1e-3 and abs(s.lattice.a - s.lattice.c) < 1e-3
                                                and all(abs(ang - 90) < 1e-2 for ang in s.lattice.angles))},
                         "records": {ms: Record(str(mid), d, props, s.composition.reduced_formula) for ms, d in dense.items()},
                         **{c: float(v) for c, v in zip(columns, props)}})
        log(f"  {split}: {sum(r['split'] == split for r in rows):,} materials read")
    rows.sort(key=lambda r: (int(r["material_id"]) if r["material_id"].isdigit() else 1 << 40, r["material_id"]))
    return rows, dict(skipped)


def property_stats(values: np.ndarray, label: str, unit: str, edges: np.ndarray | None = None) -> dict:
    v = np.asarray(values, dtype=float)
    lo, hi = float(v.min()), float(v.max())
    edges = np.linspace(lo, hi, 41) if edges is None else edges
    counts, _ = np.histogram(v, bins=edges)
    nz = v[v != 0]
    out = {"label": label, "unit": unit, "n": int(len(v)), "mean": float(v.mean()), "std": float(v.std()),
           "min": lo, "max": hi, "median": float(np.median(v)), "span": hi - lo,
           "percentiles": {f"p{p}": float(np.percentile(v, p)) for p in PERCENTILES},
           "zero_share": float((v == 0).mean()),
           "histogram": {"edges": [float(e) for e in edges], "counts": [int(c) for c in counts]}}
    if 0 < len(nz) < len(v):
        c2, _ = np.histogram(nz, bins=edges)
        out["nonzero"] = {"n": int(len(nz)), "mean": float(nz.mean()), "std": float(nz.std()), "min": float(nz.min()),
                          "max": float(nz.max()), "median": float(np.median(nz)),
                          "percentiles": {f"p{p}": float(np.percentile(nz, p)) for p in PERCENTILES},
                          "histogram": {"edges": [float(e) for e in edges], "counts": [int(c) for c in c2]}}
    return out


def family_coverage(elements_all: Counter) -> dict:
    from meidnet.family import load_family
    out = {}
    for name, variants in FAMILIES.items():
        out[name] = {}
        for v in variants:
            fam = load_family(name, variant=v)
            out[name][v] = {}
            for grp in fam.groups.values():
                allowed = list(grp.sample)
                present = [e for e in allowed if elements_all.get(e, 0) > 0]
                out[name][v][grp.name] = {"allowed": allowed, "present": present, "absent": [e for e in allowed if e not in present],
                                         "n_materials": {e: int(elements_all.get(e, 0)) for e in allowed}}
    return out


def ambiguity_grid(Y: np.ndarray, formulas: list[str], columns: list[str], stats: dict) -> dict:
    """On a grid of property values: how many training materials fall in the tolerance box around each point, and
    how many distinct compositions they have. The tolerance is 5 % of each property's span."""
    tol = np.array([0.05 * stats[c]["span"] for c in columns])
    axes = [np.linspace(stats[c]["min"], stats[c]["max"], 31) for c in columns]
    f = np.array(formulas)
    n_box = np.zeros((len(axes[0]), len(axes[1])), dtype=int)
    n_formulas = np.zeros_like(n_box)
    for i, a in enumerate(axes[0]):
        m0 = np.abs(Y[:, 0] - a) <= tol[0]
        for j, b in enumerate(axes[1]):
            m = m0 & (np.abs(Y[:, 1] - b) <= tol[1])
            n_box[i, j] = int(m.sum())
            n_formulas[i, j] = len(set(f[m])) if n_box[i, j] else 0
    return {"columns": columns, "tolerance": tol.tolist(), "axes": {c: ax.tolist() for c, ax in zip(columns, axes)},
            "n_box": n_box.tolist(), "n_formulas": n_formulas.tolist()}


def profiles(rows: list[dict], columns: list[str]) -> dict:
    out = {}
    for name, sel in (("train", [r for r in rows if r["split"] == "train"]), ("all", rows)):
        keys = Counter(tuple(round(r[c], 8) for c in columns) for r in sel)
        shared = sum(1 for r in sel if keys[tuple(round(r[c], 8) for c in columns)] >= 11)
        largest = max(keys.values()) if keys else 0
        out[name] = {"n_materials": len(sel), "n_profiles": len(keys), "largest_group": largest,
                     "share_with_10_or_more_pct": 100.0 * shared / len(sel) if sel else 0.0}
    return out


# ───────────────────────── models ─────────────────────────
def evaluate_split(lm, train, test, columns: list[str], k: int = 5) -> dict:
    """The benchmark's evaluation (meidnet.benchmark.evaluate_checkpoint) on records already in memory, plus the
    reverse direction, property -> structure, which is the direction a design query runs in."""
    from meidnet.benchmark import SPACES, encode, knn_predict, property_metrics, retrieval
    Zc_tr, _, _ = encode(lm, train, space="projection")
    Zc, Zp, P = encode(lm, test, space="projection")
    Y = np.array([r.properties for r in test], dtype=float)
    Y_tr = np.array([r.properties for r in train], dtype=float)
    prop = property_metrics(columns, Y, P)
    rep = retrieval(Zc, Zp, Y)
    knn = knn_predict(Zc_tr, Y_tr, Zc, k=k, metric="cosine")
    for j, c in enumerate(columns):
        err = np.abs(knn[:, j] - Y[:, j])
        rep[f"knn_mae_{c}"] = float(err.mean())
        nz = Y[:, j] != 0
        if 0 < nz.sum() < len(nz):
            rep[f"knn_mae_{c}_nonzero"] = float(err[nz].mean())
    rep["n_evaluated"] = float(len(test))
    rep["cosine_projection"] = rep["cosine_matched"]
    Zc_e, Zp_e, _ = encode(lm, test, space="encoder")
    rep["cosine_encoder"] = float((Zc_e * Zp_e).sum(1).mean())
    rep["chance_top1"] = 1.0 / rep["n_profiles"]
    rep["chance_top5"] = min(1.0, 5.0 / rep["n_profiles"])
    # reverse retrieval: from each distinct property profile to the structures
    _, first, inv = np.unique(np.round(Y, 8), axis=0, return_index=True, return_inverse=True)
    inv = np.asarray(inv).reshape(-1)
    S = Zp[first] @ Zc.T                                    # profiles x materials
    order = np.argsort(-S, axis=1)[:, :5]
    hit = inv[order] == np.arange(len(first))[:, None]
    rep["reverse_top1"] = float(hit[:, 0].mean())
    rep["reverse_top5"] = float(hit.any(1).mean())
    return {"property_prediction": prop, "representation": rep, "space": "projection", "k": k,
            "_latents": (Zc_tr, Zc, Zp, P)}


def recoverability(lm, test, log=print) -> dict:
    """What the decoder recovers of the held-out structures, from the joint latent (the paper's path: the decoder
    receives the true positions) and from the property latent alone (positions start at zero)."""
    import torch
    from pymatgen.analysis.structure_matcher import StructureMatcher
    from pymatgen.core import Element, Lattice, Structure
    from torch.utils.data import DataLoader
    from meidnet.data import MaterialsDataset, split_dense

    model, ms = lm.model.eval(), lm.model.max_sites
    matcher = StructureMatcher(stol=0.5, angle_tol=10, ltol=0.3)
    scale = np.array([20, 20, 20, 180, 180, 180], dtype=float)

    def structure(lat, species_idx, coords, n):
        abc = lat * scale
        if not np.all(np.isfinite(abc)) or np.any(abc[:3] <= 0.5) or np.any(abc[3:] <= 5) or np.any(abc[3:] >= 175):
            return None
        return Structure(Lattice.from_parameters(*abc), [Element.from_Z(int(z) + 1) for z in species_idx[:n]], coords[:n] % 1.0)

    acc = {p: {"matched": 0, "composition_exact": 0, "sites_correct": 0, "sites": 0, "lattice_err": 0.0, "coord_err": 0.0, "n": 0}
           for p in ("from_joint", "from_property")}
    done = 0
    with torch.no_grad():
        for b in DataLoader(MaterialsDataset(test, lm.stats), batch_size=256, shuffle=False):
            cv, props = b["crystal_vec"], b["props"]
            true = split_dense(cv, ms)
            n_sites = (true["species"].sum(-1) > 0).sum(1).numpy()
            _, _, lat_j, _, spc_j, crd_j, _ = model(cv, props)
            z_p = model.encode_properties(props)
            lat_p, _, spc_p, crd_p = model.crystal_decoder(z_p)
            for path, (lat, spc, crd) in (("from_joint", (lat_j, spc_j, crd_j)), ("from_property", (lat_p, spc_p, crd_p))):
                a = acc[path]
                for i in range(len(cv)):
                    n = int(n_sites[i])
                    t_sp = true["species"][i].argmax(-1).numpy()[:n]
                    p_sp = spc[i].argmax(-1).numpy()[:n]
                    a["n"] += 1
                    a["sites"] += n
                    a["sites_correct"] += int((t_sp == p_sp).sum())
                    a["composition_exact"] += int(np.array_equal(np.sort(t_sp), np.sort(p_sp)))
                    a["lattice_err"] += float(np.abs((lat[i].numpy()[:3] - true["lat"][i].numpy()[:3]) * 20.0).mean())
                    d = np.abs((crd[i].numpy()[:n] - true["coords"][i].numpy()[:n]) % 1.0)
                    a["coord_err"] += float(np.minimum(d, 1.0 - d).mean())
                    try:
                        s_true = structure(true["lat"][i].numpy(), true["species"][i].argmax(-1).numpy(), true["coords"][i].numpy(), n)
                        s_pred = structure(lat[i].numpy(), spc[i].argmax(-1).numpy(), crd[i].numpy(), n)
                        a["matched"] += int(bool(s_true is not None and s_pred is not None and matcher.fit(s_true, s_pred)))
                    except Exception:
                        pass
            done += len(cv)
            if done % 1024 < 256:
                log(f"  recoverability: {done:,} of {len(test):,}")
    out = {}
    for path, a in acc.items():
        n = max(1, a["n"])
        out[path] = {"n": a["n"], "structure_match_pct": 100.0 * a["matched"] / n, "composition_exact_pct": 100.0 * a["composition_exact"] / n,
                     "site_accuracy_pct": 100.0 * a["sites_correct"] / max(1, a["sites"]), "lattice_mae_angstrom": a["lattice_err"] / n,
                     "coord_mae_frac": a["coord_err"] / n}
    out["matcher"] = {"stol": 0.5, "angle_tol": 10, "ltol": 0.3, "element": "most likely per site"}
    return out


# ───────────────────────── the build ─────────────────────────
def build(data_dir: str, models: dict[str, str], out: str, skip_recoverability: bool = False, limit: int | None = None,
          log=print) -> dict:
    import meidnet
    from meidnet.checkpoint import load_checkpoint, property_ranges

    if not models:
        raise SystemExit("at least one --model ID=PATH is needed")
    loaded = {}
    for mid, path in models.items():
        if not os.path.exists(path):
            raise SystemExit(f"model file {path} is missing: run python scripts/fetch_assets.py")
        loaded[mid] = load_checkpoint(path, device="cpu")
    first = next(iter(loaded.values()))
    columns = list(first.stats.columns)
    for mid, lm in loaded.items():
        if list(lm.stats.columns) != columns:
            raise SystemExit(f"model {mid} predicts {list(lm.stats.columns)}; the demo needs {columns}")

    log(f"reading {data_dir} ...")
    rows, skipped = read_materials(data_dir, columns, [lm.model.max_sites for lm in loaded.values()], limit, log)
    by_split = {s: [r for r in rows if r["split"] == s] for s in SPLITS}
    Y_tr = np.array([[r[c] for c in columns] for r in by_split["train"]], dtype=float)
    Y_all = np.array([[r[c] for c in columns] for r in rows], dtype=float)
    labels = {c: (first.stats.labels[i] if first.stats.labels and first.stats.labels[i] != c else LABELS.get(c, (c, ""))[0],
                  first.stats.units[i] if first.stats.units and first.stats.units[i] else LABELS.get(c, (c, ""))[1])
              for i, c in enumerate(columns)}

    # dataset.json
    stats_train = {c: property_stats(Y_tr[:, j], *labels[c]) for j, c in enumerate(columns)}
    stats_all = {c: property_stats(Y_all[:, j], *labels[c], edges=np.array(stats_train[c]["histogram"]["edges"]) if
                                   stats_train[c]["min"] <= Y_all[:, j].min() and stats_train[c]["max"] >= Y_all[:, j].max() else None)
                 for j, c in enumerate(columns)}
    elements_all = Counter(e for r in rows for e in r["elements"])
    elements_split = {s: dict(sorted(Counter(e for r in by_split[s] for e in r["elements"]).items())) for s in SPLITS}
    dataset = {
        "dataset_id": "perov5", "title": "Perov-5", "columns": ["material_id", "cif", "formula", *columns],
        "id_column": "material_id", "cif_column": "cif",
        "source": {"name": "Perov-5 (Castelli et al. 2012), CDVAE split (Xie et al. 2022)",
                   "url": "https://github.com/txie-93/cdvae/tree/main/data/perov_5"},
        "fingerprint": {s: sha256_file(os.path.join(data_dir, f"{s}.csv")) for s in SPLITS},
        "rows": {**{s: len(by_split[s]) for s in SPLITS}, "all": len(rows)},
        "skipped": skipped, "limit": limit,
        "properties": stats_train, "properties_all": stats_all, "properties_basis": "train split",
        "elements": dict(sorted(elements_all.items())), "elements_by_split": elements_split,
        "family_coverage": family_coverage(elements_all),
        "family_like_rows": {**{s: sum(1 for r in by_split[s] if r["site_key"]) for s in SPLITS}, "all": sum(1 for r in rows if r["site_key"])},
        "profiles": profiles(rows, columns),
        "ambiguity_grid": ambiguity_grid(Y_tr, [r["reduced_formula"] for r in by_split["train"]], columns, stats_train),
    }
    dataset["fingerprint"]["combined"] = hashlib.sha256("".join(dataset["fingerprint"][s] for s in SPLITS).encode()).hexdigest()
    os.makedirs(out, exist_ok=True)
    write_json(os.path.join(out, "dataset.json"), dataset)

    # materials.csv.gz
    import io
    with gzip.GzipFile(os.path.join(out, "materials.csv.gz"), "wb", compresslevel=9, mtime=0) as gz,             io.TextIOWrapper(gz, encoding="utf-8", newline="") as f:        # mtime 0: identical bytes on every build
        f.write(",".join(["material_id", "split", "formula", "reduced_formula", "site_key", *columns]) + "\n")
        for r in rows:
            f.write(",".join([r["material_id"], r["split"], r["formula"], r["reduced_formula"], r["site_key"],
                              *(repr(float(r[c])) for c in columns)]) + "\n")

    # per model
    model_entries, project_models, latents_by_model = [], [], {}
    for mid, lm in loaded.items():
        path = models[mid]
        train = [r["records"][lm.model.max_sites] for r in by_split["train"]]          # featurised at this model's size
        test = [r["records"][lm.model.max_sites] for r in by_split["test"]]
        log(f"model {mid}: evaluating on {len(test):,} held-out materials ...")
        ev = evaluate_split(lm, train, test, columns)
        Zc_tr, Zc, Zp, P = ev.pop("_latents")
        latents_by_model[mid] = Zc_tr
        ids_tr = np.array([r.material_id for r in train])
        _, _, P_tr = __import__("meidnet.benchmark", fromlist=["encode"]).encode(lm, train, space="projection")
        np.savez_compressed(os.path.join(out, f"latents_train.{mid}.npz"), z=Zc_tr.astype(np.float16), material_id=ids_tr,
                            pred=P_tr.astype(np.float32), columns=np.array(columns), model_id=np.array(mid), space=np.array("projection"))
        trained_on = "all" if lm.legacy or lm.meta.get("data_report", {}).get("rows", 0) >= dataset["rows"]["all"] else "train"
        rec = {"status": "not_computed"} if skip_recoverability else recoverability(lm, test, log)
        readiness = {"model_id": mid, "split": "test", "n": len(test), "space": "projection", "k": 5,
                     "evaluation": {"property_prediction": ev["property_prediction"], "representation": ev["representation"]},
                     "recoverability": rec,
                     "caveats": (["test split was part of this model's training data"] if trained_on == "all" else []),
                     "meidnet_version": meidnet.__version__, "checkpoint_sha256": sha256_file(path),
                     "columns": columns, "limit": limit}
        write_json(os.path.join(out, "readiness", f"{mid}.json"), readiness)
        entry = {"model_id": mid, "file": os.path.basename(path), "sha256": readiness["checkpoint_sha256"],
                 "backend": "meidnet", "legacy": bool(lm.legacy), "trained_on": trained_on,
                 "training_rows": dataset["rows"]["all"] if trained_on == "all" else dataset["rows"]["train"],
                 "properties": [{**p, "label": labels[p["column"]][0], "unit": labels[p["column"]][1]} for p in lm.stats.to_dict()],
                 "max_sites": lm.model.max_sites, "latent_dim": lm.model.latent_dim, "family": lm.family,
                 "property_ranges": {c: list(v) for c, v in property_ranges(lm).items()},
                 "note": lm.meta.get("note", ""),
                 "description": ("The published Perov-5 model of the MEIDNet paper (MEIDNet v1 checkpoint)." if mid == "meidnet-2k" else
                                 "A re-run of the paper's alignment training with seed 3 (MEIDNet v1 checkpoint)." if "seed3" in mid else
                                 "MEIDNet retrained on the Perov-5 training split with element descriptors: the final Perov-5 "
                                 "configuration of the research pipeline (MEIDNet 2 checkpoint)." if mid == "desc-full" else
                                 "MEIDNet retrained on the Perov-5 training split with element descriptors and four times the weight "
                                 "on reading the properties from the structure; chosen by its band-gap error on the validation split "
                                 "(MEIDNet 2 checkpoint)." if mid == "desc-full-sp4" else
                                 lm.meta.get("note") or "MEIDNet checkpoint"),
                 "latents_file": f"latents_train.{mid}.npz"}
        model_entries.append(entry)
        project_models.append(mid)
        log(f"  {mid}: MAE " + ", ".join(f"{c} {ev['property_prediction'][f'mae_{c}']:.3f}" for c in columns)
            + f"; retrieval@1 {ev['representation']['retrieval_top1']:.3f}")
    write_json(os.path.join(out, "models.json"), model_entries)

    default_model = project_models[0]
    build_explore(out, rows, by_split, columns, default_model, latents_by_model[default_model], log)
    build_trainlite(data_dir, out, loaded[default_model], default_model, columns, log, limit=limit)
    project = {
        "project_id": "perov5-demo", "title": "Perov-5 example", "dataset_id": "perov5",
        "description": "Cubic ABX3 perovskites from the Perov-5 dataset with two DFT properties, the direct band gap and the "
                       "formation energy, and " + _models_sentence(model_entries),
        "models": project_models, "default_model": default_model,
        "default_goal": {
            "project_id": "perov5-demo", "model_id": default_model, "family": "perovskite_abx3", "variant": "oxide",
            "objectives": [{"property": "dir_gap", "kind": "value", "value": 2.0, "tolerance": 0.3, "priority": "primary"},
                           {"property": "heat_all", "kind": "at_most", "value": 1.0, "priority": "secondary"}],
            "elements": {"exclude": ["Pb"], "only": {}, "presets": ["pb_free"]},
            "max_elements": None, "rule_overrides": {}, "disabled_rules": [],
            "novelty": {"require_not_in_dataset": False},
            "budget": {"per_target": 3, "population": 24, "rounds": 3, "steps": 300, "seed": 937, "min_cosine_sep": 0.98},
            "diverse_set": None,
        },
        "scope_statement": SCOPE,
        "privacy": {"hosted": "On the shared Space, a search runs in the container; its run folder lives on the container's disk, "
                              "is removed after an hour of inactivity and on every restart, and is never used to train anything. "
                              "No account, no analytics beyond the Space's own metrics.",
                    "local": "Run locally, nothing leaves your computer."},
        "citations": [{"key": "meidnet", "text": "A. Babu, R. Almeida Gouvêa, P. Vandergheynst, G.-M. Rignanese, MEIDNet: Multimodal generative AI "
                                                 "framework for inverse materials design, npj Computational Materials 12, 287 (2026).",
                       "doi": "10.1038/s41524-026-02153-3"},
                      {"key": "perov5", "text": "I. E. Castelli et al., New cubic perovskites for one- and two-photon water splitting using the "
                                                "computational materials repository, Energy Environ. Sci. 5, 9034 (2012).", "doi": "10.1039/C2EE22341D"},
                      {"key": "cdvae", "text": "T. Xie, X. Fu, O.-E. Ganea, R. Barzilay, T. Jaakkola, Crystal diffusion variational autoencoder for "
                                               "periodic material generation, ICLR (2022).", "url": "https://github.com/txie-93/cdvae"}],
    }
    write_json(os.path.join(out, "project.json"), project)

    manifest = {"artefacts_version": 1, "built_with": {"meidnet": meidnet.__version__, "numpy": np.__version__, "torch": _torch_version()},
                "models": {m["model_id"]: m["sha256"] for m in model_entries}, "rows": dataset["rows"], "limit": limit,
                "dataset_fingerprint": dataset["fingerprint"]["combined"],
                "computed_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")}
    write_json(os.path.join(out, "manifest.json"), manifest)
    log(f"wrote {out}")
    return manifest


# ───────────────────────── Explore: the map and the cells ─────────────────────────
def pca2(Z: np.ndarray) -> tuple[np.ndarray, list[float]]:
    """A 2D principal-component projection of unit latents; the sign of each axis is fixed (largest loading positive),
    so a rebuild gives the same picture."""
    X = Z.astype(np.float64)
    X = X - X.mean(0)
    _, s, vt = np.linalg.svd(X, full_matrices=False)
    comps = vt[:2].copy()
    for i in range(2):
        if comps[i, np.argmax(np.abs(comps[i]))] < 0:
            comps[i] = -comps[i]
    xy = X @ comps.T
    var = s ** 2 / max(1, len(X) - 1)
    return xy, [float(var[0] / var.sum()), float(var[1] / var.sum())]


def build_explore(out: str, rows: list[dict], by_split: dict, columns: list[str], model_id: str, Zc_tr: np.ndarray, log=print) -> None:
    """explore.json: every training material as a point of the default model's latent map (PCA of the projection-space
    latents, two coordinates), with its formula, properties and A|B|X sites; explore_cells.npz: the cell of every
    material of every split, for the viewer and the per-material route."""
    train = by_split["train"]
    xy, explained = pca2(Zc_tr)
    assert len(xy) == len(train)
    points = [[r["material_id"], r["formula"], round(float(x), 3), round(float(y), 3), *[round(float(r[c]), 4) for c in columns], r["site_key"]]
              for r, (x, y) in zip(train, xy)]
    write_json(os.path.join(out, "explore.json"), {
        "schema": "meidnet-matter/explore/1", "project_id": "perov5-demo", "model_id": model_id, "split": "train",
        "columns": ["material_id", "formula", "x", "y", *columns, "site_key"], "points": points,
        "projection": {"method": "PCA of the structure latents (projection space, unit sphere)", "explained_variance": [round(v, 4) for v in explained],
                       "note": "Two principal components of a 128-dimensional space: a projection for looking, not a measure of similarity. "
                               "Nearest neighbours on the material card are computed in the full space."},
        "n": len(points)})
    if not all(r["cell"]["cubic"] for r in rows):
        raise SystemExit("a Perov-5 cell is not cubic: the compact cell store assumes a cubic lattice")
    n_sites = {len(r["cell"]["species"]) for r in rows}
    if n_sites != {5}:
        raise SystemExit(f"Perov-5 cells with {sorted(n_sites)} sites: the compact cell store assumes five")
    np.savez_compressed(os.path.join(out, "explore_cells.npz"), material_id=np.array([r["material_id"] for r in rows]),
                        a=np.array([r["cell"]["a"] for r in rows], dtype=np.float32),
                        species=np.array([r["cell"]["species"] for r in rows]),
                        frac=np.array([r["cell"]["frac"] for r in rows], dtype=np.float32))
    log(f"explore: {len(points):,} points ({100 * sum(explained):.0f}% of the variance in two axes), {len(rows):,} cells")


# ───────────────────────── Train Lite: a small, fixed experiment ─────────────────────────
TRAINLITE = {"train": 1500, "val": 500, "nonzero_share": 0.3, "seed": 0}
# the demo's own recipe (checkpoints/configs/desc_full_sp4.yaml) at the subset's size; the table paths are placeholders
# because the subset ships featurised, and are replaced when a user runs the same recipe at full size locally
TRAINLITE_CONFIG = {
    "name": "perov5_trainlite",
    "description": "Train Lite: the demo's recipe (element descriptors, perovskite site order, periodic encoder, four times the "
                   "weight on reading the properties from the structure) on a 1,500-material subset of Perov-5.",
    "output_dir": "trainlite/out",
    "data": {"table": "trainlite/train.csv", "val_table": "trainlite/val.csv", "id_column": "material_id", "cif_column": "cif",
             "properties": [{"column": "heat_all", "label": "Formation enthalpy", "unit": "eV/atom", "normalize": True},
                            {"column": "dir_gap", "label": "Direct band gap", "unit": "eV", "normalize": True}],
             "max_sites": 5, "site_order": "perovskite", "align_to_prototype": False},
    "model": {"decoder_coordinate_input": "zeros", "periodic_encoder": True, "element_features": "cgcnn"},
    "training": {"epochs": 20, "batch_size": 64, "learning_rate": 0.001, "seed": 0, "device": "cpu", "save_every": 1000,
                 "loss_weights": {"structure_reconstruction": 1.0, "structure_property": 4.0}},
}


def trainlite_subset(df, n: int, seed: int, nonzero_share: float):
    """A sample that keeps the band gaps visible: Perov-5 has 96% zero gaps, so a plain sample would hold about 60 non-zero
    gaps in 1,500 rows; this one holds 30% (or every one there is)."""
    import pandas as pd
    nz, z = df[df["dir_gap"] > 0], df[df["dir_gap"] == 0]
    n = min(n, len(df))
    k = min(len(nz), int(n * nonzero_share))
    return pd.concat([nz.sample(k, random_state=seed), z.sample(n - k, random_state=seed)]).sample(frac=1, random_state=seed)


def build_trainlite(data_dir: str, out: str, lm, model_id: str, columns: list[str], log=print, limit: int | None = None) -> None:
    """trainlite/subset.npz (the subset featurised the way the recipe trains, so the server never parses a CIF),
    trainlite/config.yaml (the recipe for a local run at full size) and trainlite/reference.json (the sizes, the sampling,
    and the demo's default model measured on the same 500 validation materials)."""
    import yaml
    from meidnet.benchmark import encode, property_metrics
    from matter.jsonsafe import finite
    from meidnet.config import config_from_dict
    from meidnet.data import load_records, read_table
    tl = os.path.join(out, "trainlite"); os.makedirs(tl, exist_ok=True)
    cfg = config_from_dict(dict(TRAINLITE_CONFIG), base_dir=out)
    parts, records = {}, {}
    for split, n in (("train", TRAINLITE["train"]), ("val", TRAINLITE["val"])):
        if limit:                                             # a small build (tests): the same shape, fewer rows
            n = max(64, min(n, limit if split == "train" else limit // 3))
        df = trainlite_subset(read_table(os.path.join(data_dir, f"{split}.csv")), n, TRAINLITE["seed"] + (0 if split == "train" else 1), TRAINLITE["nonzero_share"])
        recs, _ = load_records(df, cfg.data, lambda p: p, None, source=f"trainlite {split}")
        if len(recs) != n:
            raise SystemExit(f"Train Lite {split}: {len(recs)} of {n} rows usable")
        records[split], parts[split] = recs, df
    dense = np.concatenate([np.stack([r.dense for r in records[s]]) for s in ("train", "val")]).astype(np.float32)
    props = np.concatenate([np.stack([r.properties for r in records[s]]) for s in ("train", "val")]).astype(np.float32)
    ids = np.array([r.material_id for s in ("train", "val") for r in records[s]])
    formulas = np.array([r.formula for s in ("train", "val") for r in records[s]])
    split = np.array(["train"] * len(records["train"]) + ["val"] * len(records["val"]))
    np.savez_compressed(os.path.join(tl, "subset.npz"), dense=dense, props=props, material_id=ids, formula=formulas, split=split,
                        columns=np.array(columns), max_sites=np.array(cfg.data.max_sites), site_order=np.array(cfg.data.site_order))
    with open(os.path.join(tl, "config.yaml"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# Train Lite's recipe. To run it at full size on your computer: point data.table and data.val_table at the\n"
                "# Perov-5 CSVs (python -m meidnet.cli download-data), set training.epochs to 200, then  meidnet train config.yaml\n")
        yaml.safe_dump(TRAINLITE_CONFIG, f, sort_keys=False)
    # the demo's default model on the same 500 validation materials: the reference a small run is compared with
    _, _, P = encode(lm, records["val"], space="projection")
    Y = np.array([r.properties for r in records["val"]], dtype=float)
    m = property_metrics(columns, Y, P)
    nz_tr = parts["train"]["dir_gap"] > 0
    reference = {"schema": "meidnet-matter/trainlite-reference/1",
                 "subset": {"train": len(records["train"]), "val": len(records["val"]), "seed": TRAINLITE["seed"],
                            "nonzero_gap_train": int(nz_tr.sum()), "nonzero_gap_val": int((parts["val"]["dir_gap"] > 0).sum()),
                            "sampling": f"{int(100 * TRAINLITE['nonzero_share'])}% of each subset has a non-zero band gap (Perov-5 itself: 4%); "
                                        "a plain sample would hold about 60 non-zero gaps in 1,500 rows. Sampled from the training and "
                                        "validation splits; the test split is untouched.",
                            "spread": {c: float(np.std(parts["train"][c])) for c in columns},
                            "spread_dir_gap_nonzero": float(np.std(parts["train"].loc[nz_tr, "dir_gap"]))},
                 "full_model": {"model_id": model_id, "training_rows": int(lm.meta.get("data_report", {}).get("rows", 0)) or None,
                                "epochs": (lm.meta.get("config") or {}).get("training", {}).get("epochs"),
                                "val_mae": {c: float(m[f"mae_{c}"]) for c in columns},
                                "val_mae_dir_gap_nonzero": float(m.get("mae_dir_gap_nonzero", float("nan"))),
                                "val_r2": {c: float(m[f"r2_{c}"]) for c in columns}},
                 "recipe": "the demo's default recipe at the subset's size (checkpoints/configs/desc_full_sp4.yaml, 200 epochs on 11,356 materials)",
                 "full_training_command": "meidnet train config.yaml    # after pointing data.table / data.val_table at the Perov-5 CSVs and setting training.epochs: 200"}
    write_json(os.path.join(tl, "reference.json"), finite(reference))
    log(f"trainlite: {len(records['train'])} + {len(records['val'])} materials featurised; reference {model_id} val MAE "
        + ", ".join(f"{c} {m[f'mae_{c}']:.3f}" for c in columns))


def _models_sentence(entries: list[dict]) -> str:
    """The end of the project description: which models the demo carries, the default first."""
    if len(entries) == 1:
        return "the published MEIDNet model trained on them." if entries[0]["model_id"] == "meidnet-2k" else \
            f"the MEIDNet model {entries[0]['model_id']} trained on them."
    words = {2: "two", 3: "three", 4: "four"}
    names = [f"{e['model_id']}{' (the default)' if i == 0 else ''}" for i, e in enumerate(entries)]
    return (f"{words.get(len(entries), len(entries))} MEIDNet models trained on them: {', '.join(names[:-1]) + ' and ' + names[-1] if len(names) > 1 else names[0]}. "
            "The readiness page shows how closely each one reads the properties of held-out materials.")


def _torch_version() -> str:
    import torch
    return torch.__version__
