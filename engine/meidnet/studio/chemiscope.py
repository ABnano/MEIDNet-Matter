"""
Datasets for chemiscope (https://chemiscope.org): a property map linked to a 3D structure viewer.

Chemiscope is a third-party library (G. Fraux, R. K. Cersonsky, M. Ceriotti, JOSS 5, 2117, 2020).
These functions only produce its JSON dataset format from MEIDNet objects:

    {"meta": {...}, "structures": [{size, names, x, y, z, cell[9]}],
     "properties": {name: {"target": "structure", "values": [...], "units": "", "description": ""}},
     "settings": {...}}

so the Studio page (and the Colab notebooks through `chemiscope.show`) can display the
design space of a family, the candidates of a search, or a training set.
"""
from __future__ import annotations

import dataclasses
import json
import os

import numpy as np

from meidnet.constraints import build_candidate

CHEMISCOPE_MAX = 2000
PAPER = "A. Babu et al., npj Comput. Mater. (2026), doi:10.1038/s41524-026-02153-3"
CHEMISCOPE_REF = ("G. Fraux, R. K. Cersonsky, M. Ceriotti, 'Chemiscope: interactive structure-property explorer', "
                  "JOSS 5, 2117 (2020)")


def structure_to_chemiscope(s) -> dict:
    """pymatgen Structure -> chemiscope structure (Cartesian A, cell as 9 row-major numbers)."""
    cart = np.asarray(s.cart_coords, dtype=float)
    return {"size": len(s), "names": [sp.symbol for sp in s.species],
            "x": cart[:, 0].round(5).tolist(), "y": cart[:, 1].round(5).tolist(), "z": cart[:, 2].round(5).tolist(),
            "cell": np.asarray(s.lattice.matrix, dtype=float).round(6).flatten().tolist()}


def _num(v) -> float:
    """Chemiscope needs every value of a property to be a finite number of one type."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return f if np.isfinite(f) else 0.0


def _prop(values, units="", description="", target="structure") -> dict:
    if values and not isinstance(values[0], str):
        values = [_num(v) for v in values]
    return {"target": target, "values": values, "units": units, "description": description}


def _meta(name, description):
    return {"name": name, "description": description, "authors": ["Anand Babu"], "references": [PAPER, CHEMISCOPE_REF]}


def select_rows(rows, max_structures: int) -> list[int]:
    """Indices of rows to show: compositions that pass every rule first, then a seeded sample of the rest."""
    ok = [i for i, r in enumerate(rows) if all(r["ok"].values())]
    rest = [i for i, r in enumerate(rows) if not all(r["ok"].values())]
    if len(ok) >= max_structures:
        return ok[:max_structures]
    room = max_structures - len(ok)
    if len(rest) > room:
        rng = np.random.RandomState(0)
        rest = sorted(rng.choice(rest, room, replace=False).tolist())
    return ok + rest


def space_dataset(fam, space: dict, lm=None, max_structures: int = CHEMISCOPE_MAX) -> dict:
    """Every composition of a family on its prototype, with rule descriptors and predicted properties."""
    rows = space["rows"]
    idx = select_rows(rows, max_structures)
    fam_raw = dataclasses.replace(fam, refine_symmetry=False)
    groups = list(fam.groups)
    cols = list(space.get("columns") or (lm.stats.columns if lm else []))
    units = {c: u for c, u in zip(lm.stats.columns, lm.stats.units)} if lm else {}
    labels = {c: lab for c, lab in zip(lm.stats.columns, lm.stats.labels)} if lm else {}
    rule_names = [r["name"] for r in space["rules"]]
    P = {"formula": [], "lattice_a": [], "rules_passed": [], "passes_all": [], "verdict": []}
    for g in groups:
        P[f"site_{g}"] = []
    for c in cols:
        P[f"pred_{c}"] = []
    for rn in rule_names:
        P[f"rule_{rn}"] = []
    structures = []
    for i in idx:
        r = rows[i]
        structures.append(structure_to_chemiscope(build_candidate(fam_raw, r["e"]).raw))
        P["formula"].append(r["f"])
        P["lattice_a"].append(float(r["a"]))
        P["rules_passed"].append(sum(1 for v in r["ok"].values() if v))
        P["passes_all"].append(1 if all(r["ok"].values()) else 0)
        P["verdict"].append("pass" if all(r["ok"].values()) else "rejected")
        for g in groups:
            P[f"site_{g}"].append(r["e"][g])
        for c in cols:
            P[f"pred_{c}"].append(float(r["p"].get(c, float("nan"))))
        for rn in rule_names:
            v = r["d"].get(rn)
            P[f"rule_{rn}"].append(float(v) if v is not None else 0.0)
    props = {"formula": _prop(P["formula"], description="composition")}
    for g in groups:
        props[f"site_{g}"] = _prop(P[f"site_{g}"], description=f"element on site group {g}")
    props["lattice_a"] = _prop(P["lattice_a"], "A", "cubic cell edge from ionic radii")
    for c in cols:
        props[f"pred_{c}"] = _prop(P[f"pred_{c}"], units.get(c, ""), f"predicted {labels.get(c, c)} (structure encoder)")
    for rn, rule in zip(rule_names, space["rules"]):
        props[f"rule_{rn}"] = _prop(P[f"rule_{rn}"], "", rule.get("title", rn))
    props["rules_passed"] = _prop(P["rules_passed"], "", "number of rules passed")
    props["passes_all"] = _prop(P["passes_all"], "", "1 if every rule passes")
    props["verdict"] = _prop(P["verdict"], "", "pass / rejected")
    x = f"pred_{cols[0]}" if cols else "lattice_a"
    y = f"pred_{cols[1]}" if len(cols) > 1 else "lattice_a"
    settings = {"map": {"x": {"property": x}, "y": {"property": y},
                        "color": {"property": "passes_all", "palette": "viridis"}, "symbol": "verdict"},
                "structure": [{"bonds": True, "unitCell": True, "supercell": [1, 1, 1], "atomLabels": False,
                               "spaceFilling": False, "keepOrientation": True}]}
    title = f"{fam.title}{' / ' + fam.variant if fam.variant else ''} - design space"
    desc = (f"{len(structures)} of {len(rows)} compositions on the ideal prototype (compositions passing every rule "
            f"first). Predicted properties come from the MEIDNet structure encoder.")
    return {"meta": _meta(title, desc), "structures": structures, "properties": props, "settings": settings}


def candidates_dataset(cands: list[dict], fam, run_dir: str | None = None, lm=None) -> dict:
    """Candidates saved by a search (CIF files when available, else rebuilt on the prototype).
    With the model (``lm``) the predicted and target values carry their units and property names."""
    from pymatgen.core import Structure
    structures = []
    P = {"formula": [], "score": [], "round": [], "target_index": []}
    pred_keys, rule_keys = [], []
    for c in cands:
        s = None
        if run_dir:
            path = os.path.join(run_dir, "generation", c["file"])
            if os.path.exists(path):
                try:
                    s = Structure.from_file(path)
                except Exception:
                    s = None
        if s is None:
            s = build_candidate(dataclasses.replace(fam, refine_symmetry=False), c["elements"]).raw
        structures.append(structure_to_chemiscope(s))
        P["formula"].append(c["formula"])
        P["score"].append(float(c.get("score", 0.0)))
        P["round"].append(int(c.get("round", 0)))
        P["target_index"].append(int(c.get("target_index", 1)))
        for k, v in (c.get("predictions") or {}).items():
            P.setdefault(f"pred_{k}", []).append(float(v))
            if f"pred_{k}" not in pred_keys:
                pred_keys.append(f"pred_{k}")
        for k, v in (c.get("target_values") or {}).items():
            P.setdefault(f"target_{k}", []).append(float(v))
        for r in c.get("constraint_results") or []:
            if r.get("value") is not None:
                P.setdefault(f"rule_{r['name']}", []).append(float(r["value"]))
                if f"rule_{r['name']}" not in rule_keys:
                    rule_keys.append(f"rule_{r['name']}")
    n = len(structures)
    units = dict(zip(lm.stats.columns, lm.stats.units)) if lm else {}
    labels = dict(zip(lm.stats.columns, lm.stats.labels)) if lm else {}
    words = {"formula": "composition", "score": "distance to the target (lower is closer)", "round": "search round",
             "target_index": "target number"}

    def describe(k):
        for pre, word in (("pred_", "predicted"), ("target_", "target")):
            if k.startswith(pre):
                c = k[len(pre):]
                return units.get(c, ""), f"{word} {labels.get(c, c)}"
        return "", words.get(k, k)

    props = {k: _prop(v, *describe(k)) for k, v in P.items() if len(v) == n}
    x = pred_keys[0] if pred_keys else "score"
    y = pred_keys[1] if len(pred_keys) > 1 else "score"
    settings = {"map": {"x": {"property": x}, "y": {"property": y}, "color": {"property": "score", "palette": "viridis"}},
                "structure": [{"bonds": True, "unitCell": True, "supercell": [1, 1, 1], "keepOrientation": True}]}
    return {"meta": _meta("Candidates found by the search", f"{n} candidate(s) that passed every rule"),
            "structures": structures, "properties": props, "settings": settings}


def records_dataset(records, props_cfg, source: str, max_structures: int = CHEMISCOPE_MAX) -> dict:
    """A training set (records loaded with keep_structures=True) with its true property values."""
    recs = [r for r in records if getattr(r, "structure", None) is not None][:max_structures]
    structures = [structure_to_chemiscope(r.structure) for r in recs]
    props = {"formula": _prop([r.formula for r in recs], description="composition"),
             "material_id": _prop([r.material_id for r in recs]),
             "n_atoms": _prop([len(r.structure) for r in recs], "", "atoms per cell")}
    cols = [p.column for p in props_cfg]
    for j, p in enumerate(props_cfg):
        props[p.column] = _prop([float(r.properties[j]) for r in recs], p.unit, p.display)
    x = cols[0] if cols else "n_atoms"
    y = cols[1] if len(cols) > 1 else "n_atoms"
    settings = {"map": {"x": {"property": x}, "y": {"property": y}, "color": {"property": x, "palette": "viridis"}},
                "structure": [{"bonds": True, "unitCell": True, "supercell": [1, 1, 1], "keepOrientation": True}]}
    return {"meta": _meta(f"Training data: {source}", f"{len(recs)} structures with their measured/computed properties"),
            "structures": structures, "properties": props, "settings": settings}


def published_data_dataset(csv_path: str, cache_path: str | None = None, max_structures: int = 1500) -> dict:
    """The Perov-5 training split (first `max_structures` rows), cached as JSON."""
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    import pandas as pd
    from meidnet.data import parse_structure
    df = pd.read_csv(csv_path).head(max_structures)
    structures, heat, gap, formulas, ids = [], [], [], [], []
    for _, row in df.iterrows():
        try:
            s = parse_structure(cif_text=row["cif"])
        except Exception:
            continue
        structures.append(structure_to_chemiscope(s))
        heat.append(float(row["heat_all"]))
        gap.append(float(row["dir_gap"]))
        formulas.append(s.composition.reduced_formula)
        ids.append(str(row["material_id"]))
    props = {"formula": _prop(formulas, description="composition"), "material_id": _prop(ids),
             "heat_all": _prop(heat, "eV/atom", "Formation enthalpy (DFT)"),
             "dir_gap": _prop(gap, "eV", "Direct band gap (DFT)")}
    settings = {"map": {"x": {"property": "heat_all"}, "y": {"property": "dir_gap"},
                        "color": {"property": "dir_gap", "palette": "viridis"}},
                "structure": [{"bonds": True, "unitCell": True, "supercell": [1, 1, 1], "keepOrientation": True}]}
    out = {"meta": _meta("Perov-5 training data (first %d of 11,356)" % len(structures),
                         "The data behind the published MEIDNet model (CDVAE split of Castelli et al.)"),
           "structures": structures, "properties": props, "settings": settings}
    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(out, f)
    return out
