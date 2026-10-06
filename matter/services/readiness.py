"""Design Readiness: can this dataset and model support this inverse-design goal?

Six indicators, each with its numbers and the sentences that state them, and one verdict:

    fidelity        A  how well the model predicts each targeted property on held-out data
    alignment       B  whether structures and property profiles meet in the shared space, in both directions
    recoverability  C  what the decoder recovers of held-out structures
    target_support  D  where each target sits in the training distribution, and how much data lies near it
    ambiguity       E  how many distinct structures share the target window (one-to-many)
    family_support  F  whether the chosen family and its elements occur in the data, and how big the design space is

    SUPPORTED        nothing weak, every target inside the distribution with data around it
    CAUTION          something fair, a target near the edge, little data around it, or an indicator not computed
    NOT_RECOMMENDED  a weak prediction of a targeted property, a target far outside, no data in the window,
                     or a family the data cannot support; the search may still run, in exploratory mode

E never changes the verdict; it changes how the search is run (a diverse set). The rule lives in `verdict_of`.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time

import numpy as np

from matter.services.goals import ValidatedGoal
from matter.services.support import (DOMAIN_WORDS, box_mask, domain_status, effective_stats, fmt, quality, share_below,
                                     tolerance, worse)

STATUS_ORDER = ("ok", "info", "caution", "not_computed", "not_ok")
VERDICTS = ("SUPPORTED", "CAUTION", "NOT_RECOMMENDED")
_space_cache: dict[str, dict] = {}
_space_locks: dict[str, threading.Lock] = {}
_space_guard = threading.Lock()


def _worst(*statuses: str) -> str:
    return max(statuses, key=STATUS_ORDER.index)


def goal_hash(goal) -> str:
    return hashlib.sha256(json.dumps(goal.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()[:16]


# ───────────────────────── A: forward fidelity ─────────────────────────
def indicator_fidelity(targeted: list[str], record: dict, artefacts) -> dict:
    pp, rep = record["evaluation"]["property_prediction"], record["evaluation"]["representation"]
    per, sentences, statuses = {}, [], []
    for c in targeted:
        p = artefacts.property(c)
        label, unit = p["label"], p["unit"]
        basis, s = effective_stats(p)
        mae, std = pp[f"mae_{c}"], p["std"]
        if basis == "nonzero":
            mae, std = pp.get(f"mae_{c}_nonzero", mae), s["std"]
        word, ratio = quality(mae, std)
        knn = rep.get(f"knn_mae_{c}_nonzero" if basis == "nonzero" else f"knn_mae_{c}", rep.get(f"knn_mae_{c}"))
        knn_word, knn_ratio = quality(knn, std) if knn is not None else ("not computed", None)
        status = {"good": "ok", "fair": "caution", "weak": "not_ok"}.get(word, "not_computed")
        statuses.append(status)
        basis_text = f" (on the {s['n']:,} materials with a non-zero {label.lower()})" if basis == "nonzero" else ""
        if word == "weak":
            sentences.append(f"The model does not reliably predict {label.lower()} on held-out data (MAE {fmt(mae, unit)} against a spread of "
                             f"{fmt(std, unit)}{basis_text}); target-conditioned design is not recommended.")
        elif word == "fair":
            sentences.append(f"The model predicts {label.lower()} on held-out data with an error of {fmt(mae, unit)} against a spread of "
                             f"{fmt(std, unit)}{basis_text}: fair, about a third of the spread.")
        elif word == "good":
            sentences.append(f"The model predicts {label.lower()} on held-out data with an error of {fmt(mae, unit)} against a spread of "
                             f"{fmt(std, unit)}{basis_text}: good.")
        else:
            sentences.append(f"The error of {label.lower()} cannot be judged: the held-out values have no spread.")
        if knn is not None:
            sentences.append(f"The latent neighbourhood (mean of the 5 nearest training structures) predicts {label.lower()} with an error of "
                             f"{fmt(knn, unit)} ({knn_word}): the shared space places similar materials together even where the decoder is off.")
        per[c] = {"label": label, "unit": unit, "mae": mae, "std": std, "ratio": ratio, "word": word, "status": status,
                  "rmse": pp.get(f"rmse_{c}"), "r2": pp.get(f"r2_{c}"), "basis": basis, "knn_mae": knn, "knn_word": knn_word,
                  "knn_ratio": knn_ratio, "zero_share": p.get("zero_share", 0.0)}
    caveat = None
    if record.get("caveats"):
        caveat = "The held-out test split was part of this model's training data, so these errors are optimistic estimates."
        sentences.append(caveat)
    return {"id": "fidelity", "title": "Property prediction", "status": _worst(*statuses), "per_property": per, "sentences": sentences,
            "measured": f"Mean absolute error on the {record.get('n', 0):,}-material test split; good < 0.25, fair < 0.5 of the spread "
                        f"(the engine's own thresholds).", "caveat": caveat,
            "numbers": {c: {"mae": per[c]["mae"], "knn_mae": per[c]["knn_mae"]} for c in per}}


# ───────────────────────── B: alignment ─────────────────────────
def indicator_alignment(rep: dict, n: int) -> dict:
    top1, rev, chance = rep["retrieval_top1"], rep.get("reverse_top1", 0.0), rep.get("chance_top1", 1.0 / max(1.0, rep.get("n_profiles", 1.0)))
    forward_ok, reverse_ok = top1 >= 5 * chance, rev >= 5 * chance
    status = "ok" if forward_ok and reverse_ok else ("caution" if forward_ok else "not_ok")
    sentences = [f"A structure retrieves its own property profile first in {top1:.0%} of the {n:,} held-out materials "
                 f"(chance {chance:.1%} over {int(rep.get('n_profiles', 0)):,} distinct profiles); a property profile retrieves one of its "
                 f"structures first in {rev:.0%} of cases.",
                 f"Mean cosine between a material's structure and property latents: {rep['cosine_projection']:.2f} after the projection heads "
                 f"(where the search runs) and {rep.get('cosine_encoder', float('nan')):.2f} before them."]
    if not reverse_ok:
        sentences.append("The property-to-structure direction, the one a design query runs in, is close to chance: many structures share a property profile.")
    return {"id": "alignment", "title": "Cross-modal alignment", "status": status, "sentences": sentences,
            "numbers": {"retrieval_top1": top1, "retrieval_top5": rep.get("retrieval_top5"), "reverse_top1": rev, "reverse_top5": rep.get("reverse_top5"),
                        "chance_top1": chance, "cosine_projection": rep.get("cosine_projection"), "cosine_encoder": rep.get("cosine_encoder"),
                        "n_profiles": rep.get("n_profiles")},
            "measured": "Retrieval among the distinct property profiles of the test split, in both directions.", "caveat": None, "per_property": None}


# ───────────────────────── C: recoverability ─────────────────────────
def indicator_recoverability(rec: dict | None) -> dict:
    if not rec or rec.get("status") == "not_computed" or "from_joint" not in rec:
        return {"id": "recoverability", "title": "Held-out reconstruction", "status": "not_computed",
                "sentences": ["Structural recoverability was not computed for this model."], "numbers": {}, "measured": "", "caveat": None, "per_property": None}
    j, p = rec["from_joint"], rec.get("from_property", {})
    exact = j["composition_exact_pct"]
    status = "ok" if exact >= 80 else ("caution" if exact >= 50 else "not_ok")
    sentences = [f"From the joint latent, the decoder recovers the exact composition of {exact:.0f} % of held-out structures "
                 f"({j['site_accuracy_pct']:.0f} % of sites; {j['structure_match_pct']:.0f} % match the input structure; lattice error "
                 f"{j['lattice_mae_angstrom']:.2f} Å)."]
    if p:
        sentences.append(f"From the property latent alone it recovers {p['composition_exact_pct']:.0f} % of compositions: the property values "
                         f"by themselves do not identify one structure.")
    return {"id": "recoverability", "title": "Held-out reconstruction", "status": status, "sentences": sentences,
            "numbers": {"from_joint": j, "from_property": p}, "measured": "Decoded on the test split; StructureMatcher stol 0.5, angle_tol 10, ltol 0.3.",
            "caveat": None, "per_property": None}


# ───────────────────────── D: target support ─────────────────────────
def target_windows(goal, artefacts) -> tuple[dict, dict]:
    """Per property: the status of the target and the window used for the joint box (first target of a list)."""
    per, windows = {}, {}
    for o in goal.objectives:
        p = artefacts.property(o.property)
        unit = p["unit"]
        basis, s = effective_stats(p)
        train_vals = artefacts.materials.Y[artefacts.materials.train_mask, artefacts.columns.index(o.property)]
        base_vals = train_vals[train_vals != 0] if basis == "nonzero" else train_vals
        tol = tolerance(p, o.tolerance)
        entry = {"label": p["label"], "unit": unit, "kind": o.kind, "basis": basis, "tolerance": tol}
        if o.kind in ("value", "values"):
            vals = [o.value] if o.kind == "value" else list(o.values)
            statuses = [domain_status(v, p) for v in vals]
            st, reason = max(statuses, key=lambda sr: ("in_distribution", "near_boundary", "extrapolating", "far_outside").index(sr[0]))
            entry.update(status=st, reason=reason, values=vals, percentile=share_below(base_vals, vals[0]))
            windows[o.property] = (vals[0] - tol, vals[0] + tol)
        elif o.kind == "range":
            s1, r1 = domain_status(o.low, p)
            s2, r2 = domain_status(o.high, p)
            st = worse(s1, s2)
            entry.update(status=st, reason=r1 if s1 == st else r2, values=[o.low, o.high], percentile=share_below(base_vals, (o.low + o.high) / 2))
            windows[o.property] = (o.low - tol, o.high + tol)
        else:
            if o.kind in ("maximize", "minimize"):
                v = s["percentiles"]["p99"] if o.kind == "maximize" else s["percentiles"]["p1"]
            else:
                v = o.value
            st, reason = domain_status(v, p)
            at_least = o.kind in ("at_least", "maximize")
            support = 1.0 - share_below(base_vals, v) if at_least else share_below(base_vals, v)
            entry.update(status=st, reason=reason, values=[v], percentile=share_below(base_vals, v), support_fraction=support,
                         bound="at_least" if at_least else "at_most")
            windows[o.property] = (v, None) if at_least else (None, v)
        entry["word"] = DOMAIN_WORDS[entry["status"]]
        per[o.property] = entry
    return per, windows


def indicator_target_support(goal, artefacts) -> tuple[dict, dict, np.ndarray]:
    per, windows = target_windows(goal, artefacts)
    m = artefacts.materials
    box_all = box_mask(m.Y, m.columns, windows) & m.train_mask
    n_box, n_train = int(box_all.sum()), int(m.train_mask.sum())
    fraction = n_box / max(1, n_train)
    statuses = [e["status"] for e in per.values()]
    if any(s == "far_outside" for s in statuses) or n_box == 0:
        status = "not_ok"
    elif any(s in ("near_boundary", "extrapolating") for s in statuses) or fraction < 0.01:
        status = "caution"
    else:
        status = "ok"
    sentences = [f"{e['label']}: {e['reason']}" for e in per.values()]
    for e in per.values():
        if "support_fraction" in e:
            sentences.append(f"{e['support_fraction']:.0%} of the training materials satisfy '{e['label'].lower()} "
                             f"{'at least' if e['bound'] == 'at_least' else 'at most'} {fmt(e['values'][0], e['unit'])}'.")
    sentences.append(f"{n_box:,} training materials ({fraction:.1%} of {n_train:,}) lie inside the target window"
                     + (": there is no training data around this target." if n_box == 0 else "."))
    return ({"id": "target_support", "title": "Target coverage", "status": status, "per_property": per, "sentences": sentences,
             "numbers": {"n_box": n_box, "n_train": n_train, "fraction": fraction, "windows": {k: list(v) for k, v in windows.items()}},
             "measured": "Percentiles of the training split; the window is the target ± 5 % of the property's span (or the stated tolerance).",
             "caveat": None}, windows, box_all)


# ───────────────────────── E: one-to-many ambiguity ─────────────────────────
def indicator_ambiguity(goal, artefacts, latents, lm, box_all: np.ndarray, windows: dict) -> dict:
    m = artefacts.materials
    idx = np.where(box_all)[0]
    n_box = len(idx)
    formulas = {m.reduced[i] for i in idx}
    site_keys = {m.site_keys[i] for i in idx if m.site_keys[i]}
    n_clusters = latents.clusters(box_all, 0.9) if (latents is not None and n_box) else None
    # the materials nearest the target in property space (normalised by the window half-widths)
    centre = np.array([(lo if hi is None else hi if lo is None else (lo + hi) / 2) for lo, hi in (windows[c] for c in m.columns if c in windows)])
    cols = [j for j, c in enumerate(m.columns) if c in windows]
    scale = np.array([max(1e-9, (windows[m.columns[j]][1] or windows[m.columns[j]][0]) - (windows[m.columns[j]][0] or windows[m.columns[j]][1]) or 1.0) for j in cols])
    examples = []
    if n_box:
        d = np.abs((m.Y[idx][:, cols] - centre) / scale).sum(1)
        for i in idx[np.argsort(d)[:10]]:
            examples.append(m.row(int(i)))
    tied = None
    if lm is not None and latents is not None:
        try:
            import torch
            vec = np.zeros(len(m.columns))
            for o in goal.objectives:
                j = m.columns.index(o.property)
                target = (o.value if o.kind in ("value", "at_least", "at_most") else o.values[0] if o.kind == "values" else
                          (o.low + o.high) / 2 if o.kind == "range" else centre[cols.index(j)])
                vec[j] = (target - lm.stats.mean[j]) / lm.stats.std[j]
            with torch.no_grad():
                zq = lm.model.encode_properties(torch.tensor([vec], dtype=torch.float32)).numpy()[0]
            tied = latents.tied_to(zq, 0.02)
        except Exception:
            tied = None
    n_formulas = len(formulas)
    word = "low" if n_formulas < 3 else ("moderate" if n_formulas < 10 else "high")
    one_to_many = n_box >= 10
    sentences = []
    if n_box:
        sentences.append(f"{n_box:,} training materials lie inside the target window; they have {n_formulas:,} distinct compositions"
                         + (f" and {len(site_keys):,} distinct A|B|X assignments" if site_keys else "")
                         + (f", forming {n_clusters:,} groups in the model's latent space (cosine ≥ 0.9)" if n_clusters is not None else "") + ".")
    else:
        sentences.append("No training material lies inside the target window, so the ambiguity of this target cannot be measured from the data.")
    if one_to_many:
        sentences.append("One property target, many possible structures: a single target value does not identify one structure, so the "
                         "candidates of a search are alternatives, not a ranking of one answer.")
    if tied is not None:
        sentences.append(f"The target's own property latent is within 0.02 of its best match for {tied:,} training structures.")
    return {"id": "ambiguity", "title": "One-to-many ambiguity", "status": "info", "sentences": sentences, "word": word, "one_to_many": one_to_many,
            "numbers": {"n_box": n_box, "n_formulas": n_formulas, "n_site_keys": len(site_keys), "n_clusters": n_clusters, "tied_structures": tied},
            "examples": examples, "search_advice": ({"diverse_set": True, "per_target_min": 3, "min_cosine_sep_max": 0.98} if one_to_many else None),
            "measured": "Materials of the training split inside the target window; compositions by reduced formula; clusters by greedy leader "
                        "clustering of the structure latents.", "caveat": None, "per_property": None}


# ───────────────────────── F: family support ─────────────────────────
def _space_stats(fam, dataset_index, max_compositions: int = 1500) -> dict:
    """How many compositions the family offers, how many pass its rules, how many are in the dataset (cached per family key)."""
    key = json.dumps([fam.name, fam.variant, {g: grp.sample for g, grp in fam.groups.items()}, fam.constraints], sort_keys=True, default=str)
    key = hashlib.sha256(key.encode()).hexdigest()
    with _space_guard:
        lock = _space_locks.setdefault(key, threading.Lock())
    with lock:
        if key in _space_cache:
            return _space_cache[key]
        from meidnet.designspace import enumerate_space, total_compositions
        total = total_compositions(fam)
        space = enumerate_space(fam, None, max_compositions=max_compositions)
        rows = space["rows"]
        passing = [r for r in rows if all(r["ok"].values())]
        in_data = sum(1 for r in passing if "|".join(r["e"].get(g, "") for g in ("A", "B", "X")) in dataset_index.by_site)
        out = {"total": total, "enumerated": len(rows), "sampled": bool(space.get("sampled")), "rule_passing": len(passing),
               "rule_passing_fraction": len(passing) / max(1, len(rows)), "in_dataset": in_data}
        _space_cache[key] = out
        return out


def indicator_family_support(v: ValidatedGoal, artefacts, dataset_index, model_entry: dict) -> dict:
    fam = v.family
    d = artefacts.dataset
    elements = d.get("elements", {})
    groups, sentences, statuses = {}, [], []
    excluded = set(v.generation.get("exclude_elements", []))
    for g, grp in fam.groups.items():
        allowed = list(grp.sample)
        present = [e for e in allowed if elements.get(e, 0) > 0]
        absent = [e for e in allowed if e not in present]
        cov = len(present) / max(1, len(allowed))
        groups[g] = {"allowed": allowed, "present": present, "absent": absent, "excluded_by_user": sorted(excluded & set(grp.universe)),
                     "coverage": cov, "n_materials": {e: int(elements.get(e, 0)) for e in allowed}}
        if cov == 0:
            statuses.append("not_ok")
        elif absent:
            statuses.append("caution")
        if absent:
            sentences.append(f"Of the {len(allowed)} elements allowed on the {g} site of the {fam.title}"
                             f"{' (' + fam.variant + ' variant)' if fam.variant else ''}, {len(present)} occur in the dataset; "
                             f"{', '.join(absent)} {'does' if len(absent) == 1 else 'do'} not occur in any of the {d['rows']['all']:,} materials.")
    like_train, n_train = d["family_like_rows"]["train"], d["rows"]["train"]
    if fam.name == "perovskite_abx3":
        sentences.append(f"{like_train:,} of the {n_train:,} training materials are single-anion ABX3 cells like this family's prototype; "
                         f"the rest have mixed anions.")
        if like_train / max(1, n_train) < 0.5:
            statuses.append("caution")
    space = _space_stats(fam, dataset_index)
    if space["rule_passing"] == 0:
        statuses.append("not_ok")
    sentences.append(f"The design space has {space['total']:,} compositions" + (f" (a sample of {space['enumerated']:,} was checked)" if space["sampled"] else "")
                     + f"; {space['rule_passing']:,} pass every rule as set, {space['in_dataset']:,} of those are in the dataset.")
    caveat = None
    if model_entry.get("family") and fam.name != model_entry["family"]:
        caveat = f"This model was trained on {model_entry['family']} structures, not on this family."
        sentences.append(caveat)
        statuses.append("caution")
    status = _worst("ok", *statuses)
    return {"id": "family_support", "title": "Chemical-family support", "status": status, "groups": groups, "space": space, "sentences": sentences,
            "numbers": {"family_like_rows": like_train, "n_train": n_train, **space}, "measured": "Element occurrence over the whole dataset; "
            "the design space enumerated with the family's rules.", "caveat": caveat, "per_property": None}


# ───────────────────────── verdict ─────────────────────────
def verdict_of(ind: dict) -> tuple[str, list[str], bool]:
    """The rule. Returns (verdict, reasons, exploratory_required)."""
    reasons = []
    fid, tgt, fam = ind["fidelity"], ind["target_support"], ind["family_support"]
    for c, e in (fid.get("per_property") or {}).items():
        if e["word"] == "weak":
            reasons.append(f"held-out prediction of {e['label'].lower()} is weak (MAE {fmt(e['mae'], e['unit'])} against a spread of {fmt(e['std'], e['unit'])})")
    for c, e in (tgt.get("per_property") or {}).items():
        if e["status"] == "far_outside":
            reasons.append(f"the target for {e['label'].lower()} is far outside the training range")
    if tgt["numbers"]["n_box"] == 0:
        reasons.append("no training material lies inside the target window")
    if fam["status"] == "not_ok":
        reasons.append("the data cannot support the chosen family as set")
    if reasons:
        return "NOT_RECOMMENDED", reasons, True
    for c, e in (fid.get("per_property") or {}).items():
        if e["word"] == "fair":
            reasons.append(f"held-out prediction of {e['label'].lower()} is fair (MAE {fmt(e['mae'], e['unit'])})")
        if e["word"] == "not judged":
            reasons.append(f"the error of {e['label'].lower()} could not be judged")
    for c, e in (tgt.get("per_property") or {}).items():
        if e["status"] in ("near_boundary", "extrapolating"):
            reasons.append(f"the target for {e['label'].lower()} lies {'near the edge of' if e['status'] == 'near_boundary' else 'outside'} the training distribution")
    if 0 < tgt["numbers"]["fraction"] < 0.01:
        reasons.append(f"only {tgt['numbers']['n_box']:,} training materials lie inside the target window")
    for key, text in (("alignment", "the shared space is weakly aligned"), ("recoverability", "the decoder recovers held-out structures poorly"),
                      ("family_support", "the data cover the chosen family only in part")):
        if ind[key]["status"] in ("caution", "not_ok"):
            reasons.append(text)
        elif ind[key]["status"] == "not_computed":
            reasons.append(f"{ind[key]['title'].lower()} was not computed")
    if reasons:
        return "CAUTION", reasons, False
    return "SUPPORTED", [], False


def summary_of(verdict: str, ind: dict, goal, artefacts) -> list[str]:
    out = []
    fid = ind["fidelity"]["per_property"] or {}
    if fid:
        parts = [f"of the {e['label'].lower()} is {e['word']} (MAE {fmt(e['mae'], e['unit'])})" for e in fid.values() if e["word"] != "not judged"]
        out.append("On held-out data the model's prediction " + " and its prediction ".join(parts) + ".")
    tgt = ind["target_support"]
    out.append(" ".join(f"{e['label']}: {e['word'].lower()} — {e['reason']}" for e in (tgt["per_property"] or {}).values()))
    if ind["ambiguity"]["one_to_many"]:
        out.append(f"{ind['ambiguity']['numbers']['n_box']:,} training materials with {ind['ambiguity']['numbers']['n_formulas']:,} distinct "
                   f"compositions lie inside the target window, so the search returns a diverse set of alternatives rather than one inverse.")
    if ind["family_support"]["status"] != "ok":
        out.append(ind["family_support"]["sentences"][0])
    if verdict == "NOT_RECOMMENDED":
        out.append("A search can still run in exploratory mode: the chemistry rules apply as usual, but the predicted values of the candidates "
                   "are not reliable for this target and need confirmation by DFT or experiment.")
    elif verdict == "CAUTION":
        out.append("A search can run; read the candidates' predicted values with the errors above and confirm them by DFT or experiment.")
    else:
        out.append("The data and the model support a search for this target.")
    return [s for s in out if s.strip()]


def assess(v: ValidatedGoal, services) -> dict:
    t0 = time.time()
    art, reg = services.artefacts, services.registry
    model_id = v.goal.model_id or art.project["default_model"]
    entry, record = reg.entry(model_id), art.readiness[model_id]
    targeted = [o.property for o in v.goal.objectives]
    lm = reg.load(model_id) if reg.available(model_id) else None
    latents = art.latents(model_id)
    ind = {}
    ind["fidelity"] = indicator_fidelity(targeted, record, art)
    ind["alignment"] = indicator_alignment(record["evaluation"]["representation"], record.get("n", 0))
    ind["recoverability"] = indicator_recoverability(record.get("recoverability"))
    ind["target_support"], windows, box = indicator_target_support(v.goal, art)
    ind["ambiguity"] = indicator_ambiguity(v.goal, art, latents, lm, box, windows)
    ind["family_support"] = indicator_family_support(v, art, services.dataset_index, entry)
    verdict, reasons, exploratory = verdict_of(ind)
    return {"verdict": verdict, "exploratory_required": exploratory, "reasons": reasons, "summary": summary_of(verdict, ind, v.goal, art),
            "indicators": ind, "model_id": model_id, "caveats": record.get("caveats", []), "goal_hash": goal_hash(v.goal),
            "search_advice": ind["ambiguity"]["search_advice"], "ambiguity": ind["ambiguity"]["word"],
            "windows": {k: list(w) for k, w in windows.items()}, "notes": v.notes, "estimated_seconds": v.estimated_seconds,
            "computed_in_ms": round(1000 * (time.time() - t0))}
