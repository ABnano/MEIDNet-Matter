"""Material families as the API presents them: groups with their elements and dataset coverage, the rules with
their plain-language sentences, and the element presets."""
from __future__ import annotations

from matter.api.errors import ApiError

PRESETS = {
    "pb_free": {"title": "Pb-free", "elements": ["Pb"], "text": "Excludes lead."},
    "no_toxic": {"title": "Exclude toxic elements", "elements": ["Pb", "Cd", "Hg", "Tl", "As", "Be", "Os"],
                 "text": "Excludes Pb, Cd, Hg, Tl, As, Be and Os."},
    "no_rare_earth": {"title": "Exclude rare-earth elements",
                      "elements": ["Sc", "Y", "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu"],
                      "text": "Excludes Sc, Y and the lanthanides."},
    "no_precious": {"title": "Exclude precious metals", "elements": ["Ru", "Rh", "Pd", "Os", "Ir", "Pt", "Au", "Ag", "Re"],
                    "text": "Excludes Ru, Rh, Pd, Os, Ir, Pt, Au, Ag and Re."},
    "no_radioactive": {"title": "Exclude radioactive elements", "elements": ["Tc", "Pm", "Po", "Ra", "Ac", "Th", "Pa", "U", "Np", "Pu"],
                       "text": "Excludes Tc, Pm, Po, Ra, Ac, Th, Pa, U, Np and Pu."},
}


def list_families() -> list[dict]:
    from meidnet.family import list_families as names, load_family
    out = []
    for n in names():
        fam = load_family(n, default_variant=True)
        out.append({"name": fam.name, "title": fam.title, "description": fam.description, "variants": fam.variants,
                    "default_variant": fam.variant, "n_sites": fam.n_sites, "groups": list(fam.groups)})
    return out


def rule_entries(fam) -> list[dict]:
    from meidnet.constraints import explain, rule_key
    out = []
    for c in fam.constraints:
        params = {k: v for k, v in c.items() if k not in ("name", "id")}
        title, text = explain(c["name"], params)
        out.append({"id": rule_key(c), "rule": c["name"], "title": title, "text": text, "params": params,
                    "numeric": {k: v for k, v in params.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}})
    if fam.refine_symmetry:
        title, text = explain("symmetry_refinement", {})
        out.append({"id": "symmetry_refinement", "rule": "symmetry_refinement", "title": title, "text": text, "params": {}, "numeric": {}})
    return out


def family_payload(name: str, variant: str | None, coverage: dict | None = None, elements_in_data: dict | None = None) -> dict:
    """One family with one variant resolved."""
    from meidnet.family import FamilyError, load_family
    try:
        fam = load_family(name, variant=variant, default_variant=True)
    except (FamilyError, ValueError) as e:
        raise ApiError("engine_error", str(e), status=400) from None
    cov = ((coverage or {}).get(fam.name) or {}).get(fam.variant) or {}
    groups = {}
    for g, grp in fam.groups.items():
        c = cov.get(g) or {}
        present = c.get("present") or [e for e in grp.sample if (elements_in_data or {}).get(e)]
        groups[g] = {"description": grp.description, "slots": grp.slots, "multiplicity": grp.multiplicity,
                     "elements": grp.sample, "universe": grp.universe, "oxidation_states": grp.oxidation_states,
                     "coverage": {"present": present, "absent": [e for e in grp.sample if e not in present],
                                  "n_materials": c.get("n_materials", {})}}
    universe = {e for grp in fam.groups.values() for e in grp.sample}
    presets = {k: {**v, "elements": [e for e in v["elements"] if e in universe]} for k, v in PRESETS.items()}
    presets = {k: v for k, v in presets.items() if v["elements"]}
    return {"name": fam.name, "title": fam.title, "description": fam.description, "variant": fam.variant, "variants": fam.variants,
            "n_sites": fam.n_sites, "sites": [{"group": g, "frac": list(f)} for g, f in fam.sites], "lattice": fam.lattice,
            "lattice_rule": fam.lattice_rule, "sampling_order": fam.sampling_order, "groups": groups,
            "constraints": rule_entries(fam), "presets": presets, "n_elements": len(fam.groups)}
