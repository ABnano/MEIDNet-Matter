"""
Material families: what kind of crystal MEIDNet builds when it generates.

A family is a YAML file (see ``meidnet/families/perovskite_abx3.yaml``) with a
prototype (fixed site positions), site groups (which elements may sit where,
and with which charges), a lattice rule, optional variants, search terms and
constraints.  ``load_family`` turns that file into a ``Family`` object with every
variant and user filter already applied, so the rest of the code never has to
know where a setting came from.
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from meidnet.chem import ELEMENT_INDEX
from meidnet.constraints import assign_rule_ids, rule_key

FAMILY_DIR = Path(__file__).parent / "families"


class FamilyError(ValueError):
    """Raised when a family file is inconsistent; the message says how to fix it."""


@dataclass
class Group:
    name: str
    description: str
    slots: list[int]                       # decoder slots (prototype sites) of this group
    elements: list[str]                    # allowed while searching the latent space
    sample: list[str]                      # allowed when the final element is chosen
    oxidation_states: dict[str, list[int]]          # charges used for decoding and checks
    oxidation_states_all: dict[str, list[int]]      # family-wide table (all variants)
    universe: list[str]                    # every element the family lists for this group

    @property
    def multiplicity(self) -> int:
        return len(self.slots)


@dataclass
class Family:
    name: str
    title: str
    description: str
    sites: list[tuple[str, tuple[float, float, float]]]
    lattice: dict
    groups: dict[str, Group]
    sampling_order: list[str]
    lattice_rule: dict
    search_terms: list[dict]
    logit_transforms: list[dict]
    constraints: list[dict]
    refine_symmetry: bool = True
    symprec: float = 0.05
    variant: str | None = None
    variants: dict = field(default_factory=dict)
    source: str = ""

    # ── convenience ──────────────────────────────────────────────────────────
    @property
    def n_sites(self) -> int:
        return len(self.sites)

    @property
    def frac_coords(self) -> np.ndarray:
        return np.array([f for _, f in self.sites], dtype=np.float64)

    def group_of_slot(self, slot: int) -> str:
        return self.sites[slot][0]

    def constraint_params(self, name: str) -> dict | None:
        """The spec of a rule, found by its id (see ``constraints.rule_key``) or, failing that, its name."""
        for c in self.constraints:
            if rule_key(c) == name:
                return c
        for c in self.constraints:
            if c["name"] == name:
                return c
        return None

    def describe(self) -> str:
        """Plain-language summary used in reports and the CLI."""
        lines = [f"{self.title}" + (f"  [variant: {self.variant}]" if self.variant else "")]
        formula = "".join(
            f"{g}{len(self.groups[g].slots) if len(self.groups[g].slots) > 1 else ''}" for g in self.groups
        )
        lines.append(f"  formula pattern: {formula}   ({self.n_sites} atoms per cell)")
        for g in self.groups.values():
            lines.append(f"  {g.name}: {len(g.sample)} candidate elements - {g.description}")
        return "\n".join(lines)


def list_families() -> list[str]:
    return sorted(p.stem for p in FAMILY_DIR.glob("*.yaml"))


def _resolve_path(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.suffix in (".yaml", ".yml") and p.exists():
        return p
    builtin = FAMILY_DIR / f"{name_or_path}.yaml"
    if builtin.exists():
        return builtin
    raise FamilyError(
        f"Unknown family '{name_or_path}'. Built-in families: {', '.join(list_families())}. "
        "You can also pass the path to your own family .yaml file."
    )


def _check_elements(where: str, elements) -> None:
    bad = [e for e in elements if e not in ELEMENT_INDEX]
    if bad:
        raise FamilyError(f"{where}: unknown element symbol(s) {bad}")


def load_family(name_or_path: str, variant: str | None = None, exclude: list[str] | None = None,
                only: dict[str, list[str]] | None = None, overrides: dict | None = None,
                default_variant: bool = False) -> Family:
    """
    Load a family file and apply, in this order: the chosen variant, the user's
    element filters (``exclude`` removes elements everywhere; ``only`` restricts
    named groups), then ``overrides`` (``{term_or_constraint_name: {param: value}}``).
    With ``default_variant=True`` the first variant is used when none is named
    (enough for tasks that only need the prototype, such as aligning training data).
    """
    path = _resolve_path(name_or_path)
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    raw = copy.deepcopy(raw)
    name = raw.get("name", path.stem)

    # ── prototype ────────────────────────────────────────────────────────────
    proto = raw.get("prototype") or {}
    sites = []
    for i, s in enumerate(proto.get("sites", [])):
        if "group" not in s or "frac" not in s or len(s["frac"]) != 3:
            raise FamilyError(f"{path.name}: prototype site {i} needs 'group' and a 3-number 'frac'")
        sites.append((str(s["group"]), tuple(float(x) for x in s["frac"])))
    if not sites:
        raise FamilyError(f"{path.name}: the prototype has no sites")
    lattice = {k: v for k, v in proto.items() if k != "sites"}

    raw_groups = raw.get("groups") or {}
    used = []
    for g, _ in sites:
        if g not in used:
            used.append(g)
    missing = [g for g in used if g not in raw_groups]
    if missing:
        raise FamilyError(f"{path.name}: prototype uses group(s) {missing} that are not defined under 'groups'")

    variants = raw.get("variants") or {}
    vspec = {}
    if not variant and default_variant and variants:
        variant = next(iter(variants))
    if variant:
        if variant not in variants:
            raise FamilyError(f"{name} has no variant '{variant}'. Available: {', '.join(variants) or 'none'}")
        vspec = variants[variant] or {}
    elif variants and raw.get("require_variant", True):
        raise FamilyError(f"{name} needs a variant; choose one of: {', '.join(variants)}")

    exclude = set(exclude or [])
    only = only or {}
    groups: dict[str, Group] = {}
    for g in used:
        rg = raw_groups[g] or {}
        universe = list(rg.get("elements", []))
        _check_elements(f"{path.name} group {g}", universe)
        ox_all = {str(k): [int(q) for q in v] for k, v in (rg.get("oxidation_states") or {}).items()}
        vg = (vspec.get("groups") or {}).get(g, {}) or {}
        elements = list(vg.get("elements", universe))
        sample = list(vg.get("sample", vg.get("elements", rg.get("sample", elements))))
        ox = {str(k): [int(q) for q in v] for k, v in (vg.get("oxidation_states") or ox_all).items()}
        _check_elements(f"{path.name} variant {variant} group {g}", elements + sample)
        if g in only:
            keep = set(only[g])
            elements = [e for e in elements if e in keep]
            sample = [e for e in sample if e in keep]
        elements = [e for e in elements if e not in exclude]
        sample = [e for e in sample if e not in exclude and e in elements]
        if not sample:
            raise FamilyError(
                f"After applying the variant and your element filters, group {g} has no elements left to choose from."
            )
        groups[g] = Group(
            name=g, description=str(rg.get("description", "")),
            slots=[i for i, (gg, _) in enumerate(sites) if gg == g],
            elements=elements, sample=sample, oxidation_states=ox,
            oxidation_states_all=ox_all, universe=universe,
        )

    order = list(raw.get("sampling_order") or used)
    if sorted(order) != sorted(used):
        raise FamilyError(f"{path.name}: sampling_order {order} must list each group exactly once ({used})")

    search_terms = [dict(t) for t in raw.get("search_terms") or []]
    logit_transforms = [dict(t) for t in raw.get("logit_transforms") or []]
    constraints = assign_rule_ids([dict(c) for c in raw.get("constraints") or []])

    def apply_params(params: dict):
        for key, upd in (params or {}).items():
            # a rule id (e.g. bond_window_X_B2) selects one rule; a plain name every rule of that name
            rules = [c for c in constraints if rule_key(c) == key] or [c for c in constraints if c["name"] == key]
            hits = [t for t in search_terms + logit_transforms if t["name"] == key] + rules
            for item in hits:
                item.update({k: v for k, v in (upd or {}).items() if k not in ("name", "id")})
            if not hits:
                raise FamilyError(f"Override for '{key}' does not match any search term, transform or constraint of {name}")

    apply_params(vspec.get("params"))
    apply_params(overrides)

    return Family(
        name=name, title=str(raw.get("title", name)), description=str(raw.get("description", "")).strip(),
        sites=sites, lattice=lattice, groups=groups, sampling_order=order,
        lattice_rule=dict(raw.get("lattice") or {"rule": "fixed"}),
        search_terms=search_terms, logit_transforms=logit_transforms, constraints=constraints,
        refine_symmetry=bool(raw.get("refine_symmetry", True)), symprec=float(raw.get("symprec", 0.05)),
        variant=variant, variants={k: (v or {}).get("description", "") for k, v in variants.items()},
        source=os.fspath(path),
    )
