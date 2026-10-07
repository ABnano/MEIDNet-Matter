"""
The design space of a family: every composition it can produce, with the value of
each rule's descriptor and the model's predicted properties.

For prototype families this space is finite (hundreds to tens of thousands of
compositions), so it can be enumerated.  MEIDNet Studio uses it to show, as the
user moves a rule's limits or a target, exactly which compositions remain allowed
and which are predicted closest - the "live" view.  ``meidnet space`` writes the
same table as a CSV for your own analysis.

Predictions here come from the *structure* encoder (prototype structure → latent
→ property decoder).  The latent search of ``meidnet generate`` goes the other way
(target properties → latent → decoded structure); its candidates are a subset of
this space, so both views can be compared composition by composition.
"""
from __future__ import annotations

import dataclasses
import itertools
import math

import numpy as np
import torch

from meidnet.constraints import build_candidate, evaluate, explain, rule_key
from meidnet.data import featurize


def _prep(family):
    """Family copy without symmetry refinement (identity on ideal prototypes; 50x faster)."""
    return dataclasses.replace(family, refine_symmetry=False)


def total_compositions(family) -> int:
    n = 1
    for g in family.groups.values():
        n *= len(g.sample)
    return n


def enumerate_space(family, loaded=None, max_compositions=60000, batch=256, progress=None) -> dict:
    """
    Returns {"groups": [...], "rules": [...], "columns": [...], "rows": [...], "total": N, "sampled": bool}.
    Each row: {"e": {group: element}, "f": formula, "a": lattice_a, "d": {rule: value}, "p": {prop: value}}.
    """
    fam = _prep(family)
    groups = list(fam.groups)
    pools = [fam.groups[g].sample for g in groups]
    total = total_compositions(fam)
    combos = itertools.product(*pools)
    sampled = False
    if total > max_compositions:
        rng = np.random.RandomState(0)
        all_combos = list(combos)
        idx = rng.choice(len(all_combos), max_compositions, replace=False)
        combos = (all_combos[i] for i in sorted(idx))
        sampled = True
    cands = []
    n_done = 0
    for combo in combos:
        n_done += 1
        if len(set(combo)) < len(combo):
            continue
        cands.append(build_candidate(fam, dict(zip(groups, combo))))
        if progress and n_done % 500 == 0:
            progress(n_done, min(total, max_compositions))
    # predictions first: rules such as property_window judge the predicted values, exactly as in generate
    preds = [{} for _ in cands]
    if loaded is not None and cands:
        model = loaded.model
        dev = next(model.parameters()).device
        model.eval()
        with torch.no_grad():
            for i in range(0, len(cands), batch):
                chunk = cands[i:i + batch]
                X = torch.from_numpy(np.stack([featurize(c.raw, model.max_sites) for c in chunk])).float().to(dev)
                zc, _ = model.encode_crystal(X)
                P = loaded.stats.denormalize_tensor(model.property_decoder(zc)).cpu().numpy()
                for j, p in enumerate(P):
                    preds[i + j] = {c: float(v) for c, v in zip(loaded.stats.columns, p)}
                if progress:
                    progress(min(i + batch, len(cands)), len(cands), "predicting")
    rows = []
    for cand, p in zip(cands, preds):
        cand.predictions = p
        evaluate(cand, fam.constraints)
        rows.append({"e": cand.elements, "f": cand.formula(), "a": round(float(cand.lattice_a), 4),
                     "d": {r.name: (None if r.value is None else round(float(r.value), 5)) for r in cand.results},
                     "ok": {r.name: bool(r.passed) for r in cand.results},
                     "p": {c: round(v, 5) for c, v in p.items()}})
    rules = []
    for c in family.constraints:
        title, text = explain(c["name"], c)
        rules.append({"name": rule_key(c), "rule": c["name"], "title": title, "text": text,
                      "params": {k: v for k, v in c.items() if k not in ("name", "id")}})
    return {"groups": groups, "rules": rules, "columns": list(loaded.stats.columns) if loaded else [],
            "rows": rows, "total": total, "sampled": sampled}


def space_to_csv(space: dict, path: str) -> None:
    import csv
    rules = [r["name"] for r in space["rules"]]
    cols = space["columns"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["formula", *[f"site_{g}" for g in space["groups"]], "lattice_a", *rules, "passes_all",
                    *[f"pred_{c}" for c in cols]])
        for r in space["rows"]:
            w.writerow([r["f"], *[r["e"][g] for g in space["groups"]], r["a"],
                        *[r["d"].get(k, "") for k in rules], all(r["ok"].values()),
                        *[r["p"].get(c, "") for c in cols]])


__all__ = ["enumerate_space", "space_to_csv", "total_compositions", "math"]
