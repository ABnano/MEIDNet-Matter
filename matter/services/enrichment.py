"""Every candidate carries its evidence: predictions against the target with their domain status, the chemistry
rules with their values and windows, what the encoder says about the decoded composition, the nearest training
materials, how much training data lies around it, whether the dataset already contains it, and the stability
stage. The "why" sentence only repeats these facts."""
from __future__ import annotations

import dataclasses
import datetime
import os
from dataclasses import dataclass

import numpy as np

from matter.services.support import DOMAIN_WORDS, box_mask, domain_status, fmt, quality, tolerance

VALIDATION_STAGES = ["Generated", "Chemistry checked", "MLIP screened", "DFT relaxed", "DFT property confirmed", "Experimentally tested"]
STABILITY_STAGES = VALIDATION_STAGES          # the earlier name
SCHEMA_ID = "meidnet-matter/candidate-record/1"
CLUSTER_COSINE = 0.9                          # candidates whose encoder latents are at least this close form one cluster
AGREEMENT = {"good": "agree", "fair": "partly agree", "weak": "disagree", "not judged": "not judged"}


def validation_block(n_pass: int, n_total: int) -> dict:
    """Where a candidate stands on the validation ladder. This version reaches stage 1 (the family's chemistry rules)
    for a candidate that passed every rule; MLIP, DFT and experiment are later records."""
    stage = 1 if (n_total and n_pass == n_total) else 0
    records = [{"stage": 0, "label": VALIDATION_STAGES[0], "method": "latent-space search and decoding (meidnet)", "outcome": "decoded to a structure", "passed": True}]
    if n_total:
        records.append({"stage": 1, "label": VALIDATION_STAGES[1], "method": "the family's chemistry rules (deterministic)",
                        "outcome": f"{n_pass} of {n_total} rules passed", "passed": n_pass == n_total})
    return {"status": VALIDATION_STAGES[stage], "stage": stage, "label": f"Stage {stage} · {VALIDATION_STAGES[stage]}", "stages": VALIDATION_STAGES,
            "next": VALIDATION_STAGES[stage + 1] if stage + 1 < len(VALIDATION_STAGES) else None, "records": records}


def assign_clusters(candidates: list[dict], cosine: float = CLUSTER_COSINE) -> list[dict]:
    """Leader clustering of the candidates' encoder latents: a candidate joins the first leader it is at least `cosine`
    close to. Writes each candidate's `cluster` block and returns the run-level list (one entry per cluster)."""
    leaders: list[tuple[np.ndarray, dict]] = []
    for c in candidates:
        z = (c.get("model_evidence") or {}).get("latent")
        if not z:
            c["cluster"] = None
            continue
        v = np.asarray(z, dtype=float)
        v = v / (np.linalg.norm(v) or 1.0)
        best, best_cos = None, -1.0
        for k, (lz, entry) in enumerate(leaders):
            cs = float(lz @ v)
            if cs >= cosine and cs > best_cos:
                best, best_cos = k, cs
        if best is None:
            leaders.append((v, {"id": len(leaders) + 1, "leader": c["candidate_id"], "leader_formula": c["identity"]["formula"], "members": [], "formulas": []}))
            best, best_cos = len(leaders) - 1, 1.0
        entry = leaders[best][1]
        entry["members"].append(c["candidate_id"])
        entry["formulas"].append(c["identity"]["formula"])
        c["cluster"] = {"id": entry["id"], "leader": entry["leader"], "rank": len(entry["members"]), "cosine_to_leader": round(best_cos, 4)}
    out = []
    for _, entry in leaders:
        entry["size"] = len(entry["members"])
        out.append(entry)
    for c in candidates:
        if c.get("cluster"):
            c["cluster"]["size"] = out[c["cluster"]["id"] - 1]["size"]
    return out


@dataclass
class EvidenceContext:
    lm: object                       # meidnet LoadedModel
    family: object                   # meidnet Family (filters applied)
    artefacts: object
    latents: object                  # LatentIndex or None
    dataset_index: object
    backend: object
    goal: object                     # Goal
    model_id: str
    mode: str                        # "standard" | "exploratory"
    windows: dict                    # property -> (lo, hi) from the readiness report
    run_id: str
    run_dir: str
    rules: dict                      # rule id -> entry (title, text, params)
    ranges: dict                     # property -> (min, max) of the model
    provenance: dict = dataclasses.field(default_factory=dict)   # versions, model sha256, dataset fingerprint, goal hash


def rule_map(family) -> dict:
    from matter.services.families import rule_entries
    return {r["id"]: r for r in rule_entries(family)}


def enrich(raw: dict, ctx: EvidenceContext, index: int) -> dict:
    from meidnet.benchmark import formula_key, site_key
    from meidnet.studio.chemiscope import structure_to_chemiscope
    art, lm = ctx.artefacts, ctx.lm
    columns = list(lm.stats.columns)
    elements = dict(raw["elements"])
    formula = raw["formula"]
    reduced = formula_key(formula)
    skey = site_key(elements)
    cid = f"{ctx.run_id}-{index:03d}"
    targets = raw.get("target_values") or {}
    objectives = {o.property: o for o in ctx.goal.objectives}

    # encoder-side latent and prediction of the decoded composition; the saved structure for the 3D view
    zc, enc_pred, raw_structure = ctx.backend.encode_composition(lm, ctx.family, elements)
    structure = raw_structure
    cif_path = os.path.join(ctx.run_dir, "generation", raw["file"].replace("/", os.sep))
    if os.path.exists(cif_path):
        try:
            from pymatgen.core import Structure
            structure = Structure.from_file(cif_path)
        except Exception:
            structure = raw_structure

    # properties: two values per property, kept apart.  `predicted` is the search value: the property head read at the
    # search point, which is what kept the candidate (it tends to repeat the request).  `structure_predicted` is the
    # structure-based prediction: the decoded structure encoded again and read there.  Only the second one can support
    # a target; the domain status shown first belongs to it.
    def in_win(v, window):
        return bool((window[0] is None or v >= window[0]) and (window[1] is None or v <= window[1])) if window else None

    props = {}
    worst = "in_distribution"
    for c in columns:
        p = art.property(c)
        pred = float(raw["predictions"][c])
        struct = float(enc_pred[c]) if enc_pred.get(c) is not None else None
        status, reason = domain_status(pred, p)
        s_status, s_reason = domain_status(struct, p) if struct is not None else (None, None)
        shown = s_status or status
        worst = shown if ("in_distribution", "near_boundary", "extrapolating", "far_outside").index(shown) > \
            ("in_distribution", "near_boundary", "extrapolating", "far_outside").index(worst) else worst
        target = targets.get(c)
        o = objectives.get(c)
        window = ctx.windows.get(c)
        props[c] = {"label": p["label"], "unit": p["unit"], "objective": (o.kind if o else None), "target": target,
                    "predicted": pred, "difference": (pred - float(target)) if target is not None else None,
                    "structure_predicted": struct,
                    "structure_difference": (struct - float(target)) if (target is not None and struct is not None) else None,
                    "uncertainty": None, "uncertainty_note": "not available for this model",
                    "training_range": list(ctx.ranges.get(c, (p["min"], p["max"]))),
                    "domain": {"status": status, "word": DOMAIN_WORDS[status], "reason": reason},
                    "structure_domain": ({"status": s_status, "word": DOMAIN_WORDS[s_status], "reason": s_reason} if s_status else None),
                    "in_window": in_win(pred, window),
                    "structure_in_window": (in_win(struct, window) if struct is not None else None),
                    "window": list(window) if window else None,
                    "evidence_label": "Search value", "search_label": "Search value (the filter that kept this candidate)",
                    "structure_label": "Structure-based prediction (the decoded structure, encoded again)"}

    # rules
    constraints = []
    for r in raw.get("constraint_results", []):
        entry = ctx.rules.get(r["name"], {})
        constraints.append({"id": r["name"], "rule": entry.get("rule", r["name"]), "title": entry.get("title", r["name"]),
                            "text": entry.get("text", ""), "passed": bool(r["passed"]), "value": r.get("value"),
                            "window": r.get("window"), "detail": r.get("detail", ""),
                            "evidence_label": "Rule passed" if r["passed"] else "Rule failed"})
    n_pass = sum(1 for c in constraints if c["passed"])

    # model evidence
    agreement = {}
    for c in columns:
        p = art.property(c)
        diff = enc_pred[c] - float(raw["predictions"][c])
        word, ratio = quality(abs(diff), p["std"])
        agreement[c] = {"decoder": float(raw["predictions"][c]), "encoder": enc_pred[c], "difference": diff, "in_std": ratio,
                        "word": word, "label": AGREEMENT.get(word, word)}
    nearest = ctx.latents.nearest(zc, 3) if ctx.latents is not None else []
    for n in nearest:
        n["evidence_label"] = f"DFT-computed ({art.dataset.get('title', 'dataset')})"
    m = art.materials
    half = {c: tolerance(art.property(c), (objectives[c].tolerance if c in objectives else None)) for c in columns}
    local_windows = {c: (float(raw["predictions"][c]) - half[c], float(raw["predictions"][c]) + half[c]) for c in columns}
    local_mask = box_mask(m.Y, m.columns, local_windows) & m.train_mask
    n_within = int(local_mask.sum())
    model_evidence = {"encoder_prediction": enc_pred, "agreement": agreement, "latent_norm": raw.get("latent_norm"),
                      "latent_hit_clip": any("search limit" in f for f in raw.get("flags", [])), "score": raw.get("score"),
                      "nearest_training": nearest, "latent_distance": (1.0 - nearest[0]["cosine"]) if nearest else None,
                      "local_density": {"n_within": n_within, "fraction": n_within / max(1, int(m.train_mask.sum())),
                                        "windows": {c: list(w) for c, w in local_windows.items()}},
                      "latent": [round(float(v), 5) for v in zc]}

    # novelty and the dataset's own values
    novelty = ctx.dataset_index.lookup(reduced, skey)
    match = novelty["dataset"]["match"]
    if match:
        for c in columns:
            props[c]["dft_value"] = match["properties"].get(c)
            props[c]["dft_label"] = f"DFT-computed ({art.dataset.get('title', 'dataset')})"
    support = support_block(props, n_pass, len(constraints))

    candidate = {
        "candidate_id": cid, "run_id": ctx.run_id, "index": index, "target_index": raw.get("target_index"), "round": raw.get("round"),
        "identity": {"formula": formula, "reduced_formula": reduced, "site_key": skey, "elements": elements, "family": ctx.family.name,
                     "variant": ctx.family.variant, "backend": ctx.backend.name, "model_id": ctx.model_id},
        "structure": {"file": "generation/" + raw["file"].replace(os.sep, "/"), "lattice_a": raw.get("lattice_a"), "n_sites": len(structure),
                      "chemiscope": structure_to_chemiscope(structure),
                      "sites": [{"element": str(s.specie.symbol), "frac": [round(float(x), 5) for x in s.frac_coords]} for s in structure],
                      "lattice": [[round(float(x), 5) for x in row] for row in structure.lattice.matrix]},
        "properties": props, "domain": {"status": worst, "word": DOMAIN_WORDS[worst]}, "support": support,
        "constraints": constraints, "rules_passed": n_pass, "rules_total": len(constraints),
        "model_evidence": model_evidence, "novelty": novelty,
        "stability": validation_block(n_pass, len(constraints)),
        "cluster": None,                                   # assigned when the search has finished (assign_clusters)
        "flags": list(raw.get("flags", [])), "mode": ctx.mode, "engine": raw,
        "schema": SCHEMA_ID,
        "provenance": {**ctx.provenance, "run_id": ctx.run_id, "model_id": ctx.model_id, "backend": ctx.backend.name, "mode": ctx.mode,
                       "family": ctx.family.name, "variant": ctx.family.variant,
                       "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")},
    }
    candidate["why"] = why_sentence(candidate, ctx)
    return candidate


def support_block(props: dict, n_pass: int, n_total: int) -> dict:
    """What the candidate's evidence supports, kept apart: it passed the search filters (that is why it exists); the
    structure-based prediction supports the target or not; the dataset's DFT value supports it or not (when known)."""
    targeted = {k: p for k, p in props.items() if p.get("target") is not None and p.get("window")}
    def all_in(key):
        vals = [p.get(key) for p in targeted.values()]
        if not targeted or any(v is None for v in vals):
            return None
        return all(vals)
    structure = all_in("structure_in_window")
    dft = None
    if targeted and all(p.get("dft_value") is not None for p in targeted.values()):
        dft = all(p["window"][0] is None or p["dft_value"] >= p["window"][0] for p in targeted.values()) and \
            all(p["window"][1] is None or p["dft_value"] <= p["window"][1] for p in targeted.values())
    rules = bool(n_total) and n_pass == n_total
    if structure is None:
        label = "Passed the search filters"
    elif structure:
        label = "Passed the search filters · supported by the structure-based prediction"
    else:
        label = "Passed the search filters · not supported by the structure-based prediction"
    if dft is True:
        label += " · the dataset's DFT value is inside the window"
    elif dft is False:
        label += " · the dataset's DFT value is outside the window"
    return {"search_filters_passed": True, "rules_passed": rules, "structure_supported": structure, "dft_supported": dft,
            "n_targeted": len(targeted), "label": label}


def why_sentence(c: dict, ctx: EvidenceContext) -> str:
    parts = []
    props = c["properties"]
    targeted = [p for p in props.values() if p["target"] is not None]
    desc = []
    for p in targeted:
        unit, target = p["unit"], p["target"]
        sv = f"the search valued its {p['label'].lower()} at {fmt(p['predicted'], unit)}"
        if p.get("structure_predicted") is not None:
            d = f" ({p['structure_difference']:+.3g} from the target {fmt(target, unit)})" if p.get("structure_difference") is not None else ""
            verdict = "inside" if p.get("structure_in_window") else "outside"
            sv += f"; read from the decoded structure it is {fmt(p['structure_predicted'], unit)}{d}, {verdict} the window"
        desc.append(sv)
    head = f"{c['identity']['formula']} was kept in round {c['round']}"
    parts.append(head + (": " + "; ".join(desc) if desc else "") + ".")
    sup = c.get("support") or {}
    if sup.get("structure_supported") is False:
        parts.append("The search value is not confirmed by the structure-based prediction: treat the target as unsupported for this candidate.")
    elif sup.get("structure_supported"):
        parts.append("The structure-based prediction confirms the search value.")
    titles = [k["title"] for k in c["constraints"] if k["passed"]]
    parts.append(f"{c['rules_passed']} of {c['rules_total']} chemistry rules passed" + (f" ({', '.join(titles[:4])}{', …' if len(titles) > 4 else ''})." if titles else "."))
    worst = max(props.values(), key=lambda p: ("in_distribution", "near_boundary", "extrapolating", "far_outside").index((p.get("structure_domain") or p["domain"])["status"]))
    parts.append(f"{worst['label']}: {(worst.get('structure_domain') or worst['domain'])['reason']}")
    nn = c["model_evidence"]["nearest_training"]
    if nn:
        n0 = nn[0]
        vals = ", ".join(f"{props[k]['label'].lower()} {fmt(v, props[k]['unit'])}" for k, v in n0["properties"].items() if k in props)
        parts.append(f"Nearest training material: {n0['formula']} (cosine {n0['cosine']:.2f}; {vals}).")
    parts.append(c["novelty"]["dataset"]["label"] + ".")
    match = c["novelty"]["dataset"]["match"]
    if match:
        vals = ", ".join(f"{props[k]['label'].lower()} {fmt(v, props[k]['unit'])}" for k, v in match["properties"].items() if k in props)
        parts.append(f"The dataset's DFT values for it: {vals}.")
    v = c["stability"]
    parts.append(f"Validation: stage {v['stage']} of {len(v['stages']) - 1}, {v['status'].lower()}" + (f"; next: {v['next'].lower()}." if v.get("next") else "."))
    text = " ".join(parts)
    return ("Exploratory run: " + text) if ctx.mode == "exploratory" else text


def funnel_for(tlog, family, objectives: list[dict], population: int | None = None) -> dict:
    """The search funnel of one target, at the latent level and at the attempt level."""
    from meidnet.constraints import explain, rule_key
    from meidnet.report import PRE_STAGES
    window_ids = [rule_key(c) for c in family.constraints if c["name"] == "property_window"]
    order = PRE_STAGES + [rule_key(c) for c in family.constraints if c["name"] == "min_distance"] + \
        (["symmetry_refinement"] if family.refine_symmetry else []) + \
        [rule_key(c) for c in family.constraints if c["name"] not in ("min_distance", "property_window")] + window_ids
    tried = int(tlog.attempts)
    left = tried
    stages = []
    for name in order:
        lost = int(tlog.first_failure.get(name, 0))
        if name in PRE_STAGES:
            title = name
        else:
            title = explain(name, family.constraint_params(name) or {})[0]
        left -= lost
        stages.append({"id": name, "title": title, "lost": lost, "left": left, "is_window": name in window_ids})
    chemistry_valid = tried - sum(int(tlog.first_failure.get(n, 0)) for n in order if n not in window_ids)
    target_compatible = chemistry_valid - sum(int(tlog.first_failure.get(n, 0)) for n in window_ids)
    return {"target_index": tlog.index, "target": dict(tlog.values), "rounds_used": tlog.rounds_used,
            "latents": {"proposed": (int(population) * int(tlog.rounds_used) if population else None), "decoded": int(tlog.latents_decoded), "passing": int(tlog.latents_passing), "retained": len(tlog.saved),
                        "skipped_duplicate": int(tlog.skipped_duplicate), "skipped_similar": int(tlog.skipped_similar)},
            "attempts": {"tried": tried, "chemistry_valid": chemistry_valid, "target_compatible": target_compatible, "stages": stages},
            "rejections": {"first_failure": {k: int(v) for k, v in tlog.first_failure.items()},
                           "failures_any": {k: int(v) for k, v in tlog.failures_any.items()},
                           "examples": [{"formula": e.get("formula"), "first_failure": e.get("first_failure"),
                                         "title": (explain(e["first_failure"], family.constraint_params(e["first_failure"]) or {})[0]
                                                   if e.get("first_failure") not in PRE_STAGES and e.get("first_failure") else e.get("first_failure")),
                                         "results": e.get("results")} for e in list(tlog.rejected_examples)[:20]]}}
