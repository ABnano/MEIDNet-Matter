"""
Hard constraints: the rules every saved candidate must pass.

A candidate is a choice of one element per site group, placed on the family
prototype with the family's lattice rule.  Each constraint returns a
``ConstraintResult`` holding pass/fail, the measured value, the allowed window
and a plain-language sentence - this is what reports and MEIDNet Studio show
when they explain why a material was kept or rejected.

The numeric value of each constraint (its "descriptor") is computed only here,
in Python.  MEIDNet Studio receives these numbers and compares them with the
windows the user sets, so what you see in the browser is what `meidnet
generate` enforces.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from itertools import product

import numpy as np
from pymatgen.core import Lattice, Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from meidnet.chem import ionic_radius
from meidnet.registry import Registry

CONSTRAINTS = Registry("constraint")

# Plain-language explanations used by reports and the Studio.
EXPLAIN = {
    "min_distance": ("No overlapping atoms",
                     "Two atoms closer than {min} Å would overlap, which is physically impossible."),
    "charge_neutrality": ("Charge balance",
                          "The formal charges must add up to zero for at least one combination of the listed "
                          "oxidation states (e.g. Cs⁺ Pb²⁺ I⁻×3 = 0)."),
    "bond_window": ("Sensible {from}–{to} bonds",
                    "Every {from} atom needs a {to} neighbour at {low}–{high} × the sum of their ionic radii: "
                    "bonds may be neither squashed nor stretched."),
    "tolerance_factor": ("Goldschmidt tolerance factor",
                         "t = (r_A + r_X) / (√2 (r_B + r_X)) measures how well the A cation fits the cage of "
                         "B–X octahedra. Cubic perovskites form roughly for {min} ≤ t ≤ {max}."),
    "octahedral_factor": ("Octahedral factor",
                          "μ = r_B / r_X says whether the B cation is large enough to hold six X anions "
                          "around it ({min} ≤ μ ≤ {max})."),
    "property_window": ("Predicted {property} window",
                        "The model's predicted {property} must lie between {min} and {max}."),
    "symmetry_refinement": ("Symmetry analysis",
                            "The structure must survive symmetry refinement (spglib)."),
}


def explain(name: str, params: dict) -> tuple[str, str]:
    """Plain-language title and sentence of a rule. ``params`` is the rule's spec; its "name" (the registered
    rule) is used when ``name`` is a rule id such as property_window_dir_gap."""
    name = (params or {}).get("name") or name
    title, text = EXPLAIN.get(name, (name, CONSTRAINTS.doc(name) if name in CONSTRAINTS else ""))
    safe = _Blank({k: ("…" if v is None else v) for k, v in (params or {}).items()})   # an unset limit reads "…"
    try:
        return title.format_map(safe), text.format_map(safe)
    except (IndexError, ValueError):
        return title, text


class _Blank(dict):
    def __missing__(self, key):
        return "…"


@dataclass
class ConstraintResult:
    name: str
    passed: bool
    value: float | None = None
    window: tuple | None = None
    detail: str = ""

    def to_dict(self):
        return {"name": self.name, "passed": bool(self.passed), "value": self.value,
                "window": list(self.window) if self.window else None, "detail": self.detail}


@dataclass
class Candidate:
    family: object
    elements: dict[str, str]
    raw: Structure | None = None
    structure: Structure | None = None
    lattice_a: float | None = None
    predictions: dict[str, float] = field(default_factory=dict)
    results: list[ConstraintResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(r.passed for r in self.results)

    @property
    def first_failure(self) -> str | None:
        for r in self.results:
            if not r.passed:
                return r.name
        return None

    def radius(self, group: str) -> float:
        return ionic_radius(self.elements[group])

    def result(self, name, passed, value=None, window=None, detail=""):
        return ConstraintResult(name, bool(passed), None if value is None else float(value), window, detail)

    def formula(self) -> str:
        parts = []
        for g, grp in self.family.groups.items():
            n = len(grp.slots)
            parts.append(f"{self.elements[g]}{n if n > 1 else ''}")
        return "".join(parts)

    def descriptors(self) -> dict:
        return {r.name: r.value for r in self.results if r.value is not None}


# ───────────────────────── building candidates ─────────────────────────
def lattice_for(family, elements: dict[str, str], a: float | None = None) -> tuple[Lattice, float]:
    rule = family.lattice_rule
    kind = rule.get("rule", "fixed")
    spec = family.lattice
    if a is not None:        # a predicted lattice constant (the decoder's lattice head), kept inside the rule's bounds
        a = float(np.clip(a, float(rule.get("min", 0.0)), float(rule.get("max", 1e9))))
    elif kind == "bond_sum":
        a = float(np.clip(float(rule.get("factor", 2.0)) * sum(ionic_radius(elements[g]) for g in rule["groups"]),
                          float(rule.get("min", 0.0)), float(rule.get("max", 1e9))))
    elif kind == "fixed":
        a = float(spec.get("reference_a", spec.get("a", 4.0)))
    else:
        raise ValueError(f"unknown lattice rule '{kind}' (use bond_sum or fixed)")
    shape = spec.get("lattice", "cubic")
    if shape == "cubic":
        return Lattice.cubic(a), a
    if shape == "fcc_primitive":  # rhombohedral primitive cell of a face-centred cubic lattice of edge a
        e = a / math.sqrt(2)
        return Lattice.from_parameters(e, e, e, 60.0, 60.0, 60.0), a
    if shape == "bcc_primitive":
        e = a * math.sqrt(3) / 2
        return Lattice.from_parameters(e, e, e, 109.4712206, 109.4712206, 109.4712206), a
    # general prototype cell: scale the given cell so that its first edge equals a
    ref = Lattice.from_parameters(*(float(spec[k]) for k in ("a", "b", "c", "alpha", "beta", "gamma")))
    s = a / ref.a
    return Lattice.from_parameters(ref.a * s, ref.b * s, ref.c * s, *ref.angles), a


def _mean_radius(cand: "Candidate", groups) -> float:
    groups = groups if isinstance(groups, (list, tuple)) else [groups]
    return float(np.mean([cand.radius(g) for g in groups]))


def build_candidate(family, elements: dict[str, str], a: float | None = None) -> Candidate:
    lat, a = lattice_for(family, elements, a)
    species = [elements[g] for g, _ in family.sites]
    coords = family.frac_coords.tolist()
    raw = Structure(lat, species, coords, coords_are_cartesian=False)
    return Candidate(family=family, elements=dict(elements), raw=raw, lattice_a=a)


def refine(cand: Candidate) -> ConstraintResult:
    fam = cand.family
    if not fam.refine_symmetry:
        cand.structure = cand.raw
        return cand.result("symmetry_refinement", True)
    try:
        s = SpacegroupAnalyzer(cand.raw, symprec=fam.symprec).get_refined_structure()
    except Exception as e:  # spglib can fail on degenerate cells
        return cand.result("symmetry_refinement", False, detail=f"refinement failed: {e}")
    if np.isnan(s.cart_coords).any():
        return cand.result("symmetry_refinement", False, detail="refinement produced NaN coordinates")
    cand.structure = s
    return cand.result("symmetry_refinement", True)


def evaluate(cand: Candidate, constraints: list[dict], stop_at_first: bool = False) -> Candidate:
    """Run every constraint (min_distance on the unrefined cell, the rest after refinement)."""
    results = []
    pre = [c for c in constraints if c["name"] == "min_distance"]
    post = [c for c in constraints if c["name"] != "min_distance"]
    for spec in pre:
        results.append(_run(cand, spec))
        if stop_at_first and not results[-1].passed:
            cand.results = results
            return cand
    ref = refine(cand)
    if cand.family.refine_symmetry:
        results.append(ref)
    if not ref.passed:
        for spec in post:
            results.append(ConstraintResult(rule_key(spec), False, detail="not evaluated (symmetry refinement failed)"))
        cand.results = results
        return cand
    for spec in post:
        results.append(_run(cand, spec))
        if stop_at_first and not results[-1].passed:
            break
    cand.results = results
    return cand


def _run(cand, spec) -> ConstraintResult:
    params = {k: v for k, v in spec.items() if k not in ("name", "id")}
    res = CONSTRAINTS.get(spec["name"])(cand, **params)
    if spec.get("id"):
        res.name = str(spec["id"])
    return res


def rule_key(spec: dict) -> str:
    """The name a rule's results are reported under: its ``id`` when it has one, else the rule name."""
    return str(spec.get("id") or spec["name"])


def check_rule_spec(spec: dict) -> None:
    """Raise ValueError (with the fix) when a rule is unknown or its parameters do not fit the rule."""
    import inspect
    name = spec.get("name")
    if name not in CONSTRAINTS:
        raise ValueError(f"unknown rule '{name}'. Available rules: {', '.join(CONSTRAINTS.names())}"
                         " (or register your own in a plugin file)")
    params = {k: v for k, v in spec.items() if k not in ("name", "id")}
    try:
        inspect.signature(CONSTRAINTS.get(name)).bind(None, **params)
    except TypeError as e:
        raise ValueError(f"rule '{name}': {e}") from None


def _derived_key(spec: dict) -> str:
    name = spec["name"]
    part = lambda v: "+".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v)   # noqa: E731
    if name == "property_window" and spec.get("property"):
        return f"{name}_{spec['property']}"
    if name == "bond_window" and spec.get("from") and spec.get("to"):
        return f"{name}_{part(spec['from'])}_{part(spec['to'])}"
    return name


def assign_rule_ids(constraints: list[dict]) -> list[dict]:
    """
    Give rules that share a name a distinct ``id`` (property_window_dir_gap, bond_window_X_B2, ...) so their
    results, report rows, CSV columns and Studio controls do not collide.  Rules with a unique name keep it.
    """
    counts = Counter(c["name"] for c in constraints if not c.get("id"))
    out, used = [], set()
    for spec in constraints:
        spec = dict(spec)
        key = _derived_key(spec) if (not spec.get("id") and counts[spec["name"]] > 1) else rule_key(spec)
        k, n = key, 2
        while k in used:
            k, n = f"{key}_{n}", n + 1
        if k != spec["name"]:
            spec["id"] = k
        used.add(k)
        out.append(spec)
    return out


# ───────────────────────── built-in constraints ─────────────────────────
@CONSTRAINTS.register("min_distance", "No two atoms closer than `min` Å (within the cell).")
def min_distance(cand: Candidate, min=0.8):  # noqa: A002
    coords = cand.raw.cart_coords
    if np.isnan(coords).any():
        return cand.result("min_distance", False, detail="NaN coordinates")
    n = len(coords)
    pairs = [np.linalg.norm(coords[i] - coords[j]) for i in range(n) for j in range(i + 1, n)]
    d = float(np.min(pairs)) if pairs else float("inf")
    return cand.result("min_distance", d >= min, d, (min, None), f"closest pair {d:.2f} Å")


def charge_options(cand: Candidate):
    fam = cand.family
    tables = []
    for g, grp in fam.groups.items():
        el = cand.elements[g]
        qs = grp.oxidation_states.get(el)
        if not qs:
            return None, f"no oxidation states listed for {el} on site {g}"
        tables.append([(q, len(grp.slots)) for q in qs])
    return tables, ""


@CONSTRAINTS.register("charge_neutrality", "Formal charges add up to zero for some oxidation-state combination.")
def charge_neutrality(cand: Candidate):
    tables, why = charge_options(cand)
    if tables is None:
        return cand.result("charge_neutrality", False, 0.0, (1, 1), why)
    for combo in product(*tables):
        if sum(q * n for q, n in combo) == 0:
            charges = ", ".join(f"{cand.elements[g]}{'+' if q > 0 else ''}{q}"
                                for g, (q, _) in zip(cand.family.groups, combo))
            return cand.result("charge_neutrality", True, 1.0, (1, 1), f"balanced as {charges}")
    return cand.result("charge_neutrality", False, 0.0, (1, 1), "no combination of the listed charges sums to zero")


@CONSTRAINTS.register("bond_window", "Each `from` atom has a `to` neighbour at low–high × (r_from + r_to).")
def bond_window(cand: Candidate, low=0.75, high=1.35, cutoff=5.0, **kw):
    s = cand.structure
    src_g, dst_g = kw.get("from", "X"), kw.get("to", "B")
    src, dst = cand.elements[src_g], cand.elements[dst_g]
    r0 = ionic_radius(src) + ionic_radius(dst)
    ok_all = True
    nearest = []
    for site in s:
        if site.specie.symbol != src:
            continue
        ok = False
        best = None
        for ne in s.get_neighbors(site, cutoff):
            if ne.specie.symbol == dst:
                d = site.distance(ne)
                ratio = d / r0
                if best is None or d < best:
                    best = d
                if low * r0 <= d <= high * r0:
                    ok = True
        nearest.append(np.inf if best is None else best / r0)
        ok_all = ok_all and ok
    worst = max(nearest, key=lambda r: abs(r - 1.0)) if nearest else float("nan")
    return cand.result("bond_window", ok_all, worst, (low, high),
                       f"nearest {dst_g}–{src_g} distance = {worst:.2f} × (r_{dst} + r_{src})")


@CONSTRAINTS.register("tolerance_factor", "Goldschmidt tolerance factor inside [min, max].")
def tolerance_factor(cand: Candidate, A="A", B="B", X="X", min=0.78, max=1.05):  # noqa: A002
    """A, B, X name site groups; a list (e.g. B: [B1, B2]) averages the radii of several groups."""
    rA, rB, rX = _mean_radius(cand, A), _mean_radius(cand, B), _mean_radius(cand, X)
    t = (rA + rX) / (math.sqrt(2) * (rB + rX))
    return cand.result("tolerance_factor", min <= t <= max, t, (min, max), f"t = {t:.3f}")


@CONSTRAINTS.register("octahedral_factor", "Octahedral factor r_B / r_X inside [min, max].")
def octahedral_factor(cand: Candidate, B="B", X="X", min=0.414, max=0.90):  # noqa: A002
    rB, rX = _mean_radius(cand, B), _mean_radius(cand, X)
    mu = rB / rX if rX > 1e-8 else 9.9
    return cand.result("octahedral_factor", min <= mu <= max, mu, (min, max), f"μ = {mu:.3f}")


@CONSTRAINTS.register("property_window", "A predicted property must lie inside [min, max].")
def property_window(cand: Candidate, property=None, min=None, max=None):  # noqa: A002
    v = cand.predictions.get(property)
    if v is None:
        return cand.result("property_window", True, None, (min, max), "no prediction available")
    ok = (min is None or v >= min) and (max is None or v <= max)
    return cand.result("property_window", ok, v, (min, max), f"predicted {property} = {v:.3g}")
