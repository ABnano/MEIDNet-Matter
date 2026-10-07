"""Build a generation family YAML from an intake directory, so no family has to be hand-written per dataset.

Takes the dominant prototype of the intake (or --prototype), reads its structures out of train.csv, and infers the
prototype cell, one site group per crystallographically distinct site set (roles from meidnet.data.order_sites_by_role),
the elements observed at each site and their plausible charges; then verifies the file by enumerating its design space.
Usage: python auto_family.py <intake_dir> <out_yaml> [--prototype "ABC3|221|a,b,c"] [--name NAME]"""
import argparse, collections, csv, datetime, os
import numpy as np
from pymatgen.core import Element, Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from meidnet.chem import ionic_radius
from meidnet.config import config_from_dict
from meidnet.data import anion_elements, order_sites_by_role
from meidnet.designspace import enumerate_space
from meidnet.pipeline import family_for

csv.field_size_limit(10 ** 9)
FIXED_COLUMNS = ("material_id", "cif", "formula", "prototype")
CATION_NAMES = ["A", "B", "C", "D", "E"]
RADIOACTIVE = ["Tc", "Pm", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th", "Pa", "U", "Np", "Pu", "Am", "Cm"]
# non-metals that a high-throughput grid places on cation sites but that really form oxyanion groups (phosphites,
# sulfites, nitrates, carbonates, borates, silicates...): never perovskite cations.  Applied to cation groups only, so S as
# an anion in a sulfide is untouched.
OXYANION_FORMERS = ["H", "B", "C", "N", "P", "S", "Se", "Si", "As", "Te"]


def site_size(s, i):
    """Mean distance to the 6 nearest neighbours: the measure order_sites_by_role uses to rank cations."""
    d = sorted(nb[1] for nb in s.get_neighbors(s[i], 6.0))[:6]
    return float(np.mean(d)) if d else np.inf


def read_prototype_rows(intake, prototype):
    rows = [r for r in csv.DictReader(open(f"{intake}/train.csv")) if r["prototype"] == prototype]
    if not rows:
        raise SystemExit(f"no train.csv row has prototype {prototype}")
    S = [Structure.from_str(r["cif"], fmt="cif") for r in rows]
    n_sites = collections.Counter(len(s) for s in S).most_common(1)[0][0]
    kept = [s for s in S if len(s) == n_sites]   # supercells of the same prototype cannot share its site list
    return kept, len(S) - len(kept)


def equivalence_classes(s):
    """Index of the crystallographically distinct site set each site belongs to (one class per site if spglib fails)."""
    try:
        ds = SpacegroupAnalyzer(s, symprec=0.1).get_symmetry_dataset()
        eq = list(ds.equivalent_atoms if hasattr(ds, "equivalent_atoms") else ds["equivalent_atoms"])
        return eq if len(eq) == len(s) else list(range(len(s)))
    except Exception:
        return list(range(len(s)))


def census(structures, n_sites):
    """Elements seen at each role-ordered slot, how often that slot held an anion, and the oxidation states the elements
    actually take in this dataset.  The observed states matter: pymatgen's common_oxidation_states is coarse (V: [5] only,
    Mn: [2, 4, 7]), which rejects real perovskites such as LaVO3 and LaMnO3 on charge neutrality, so the states are taken
    from a charge-balanced assignment of each observed composition instead, and pymatgen is only the fallback."""
    seen = [collections.Counter() for _ in range(n_sites)]
    states = [collections.Counter() for _ in range(n_sites)]
    anion_hits = [0] * n_sites
    used = 0
    for s in structures:
        try:
            ordered = order_sites_by_role(s)
        except Exception:
            continue
        anions = anion_elements(s)
        try:
            guesses = s.composition.oxi_state_guesses(max_sites=-1)
            guess = guesses[0] if guesses else None
        except Exception:
            guess = None
        used += 1
        for i, site in enumerate(ordered):
            el = site.specie.symbol
            seen[i][el] += 1
            anion_hits[i] += el in anions
            if guess and el in guess:
                states[i][(el, int(round(guess[el])))] += 1
    return seen, anion_hits, used, states


def build_groups(rep, seen, anion_hits, used, obs_states):
    """One group per equivalence class of the representative cell, ordered A, B, ... then the anions."""
    classes = equivalence_classes(rep)
    raw = {}
    for i, c in enumerate(classes):
        g = raw.setdefault(c, {"slots": [], "elements": collections.Counter(), "anion": 0, "size": site_size(rep, i),
                               "obs_states": collections.Counter()})
        g["slots"].append(i)
        g["elements"] += seen[i]
        g["anion"] += anion_hits[i]
        g["obs_states"] += obs_states[i]
    groups = list(raw.values())
    for g in groups:
        g["is_anion"] = g["anion"] > 0.5 * used * len(g["slots"])
        g["en"] = float(np.mean([Element(e).X for e in g["elements"]]))
    groups.sort(key=lambda g: (g["is_anion"], -g["en"] if g["is_anion"] else -g["size"]))
    return merge_groups(groups)


def merge_groups(groups):
    """enumerate_space skips any composition that repeats an element, so two site sets holding the same elements must be
    one group on several sites (X1 on two sites in perovskite_ab_o2x.yaml).  Cations are merged only when their sites are
    also the same size, so that an A and a B site sharing a long element list stay apart."""
    out = []
    for g in groups:
        twin = next((h for h in out if h["is_anion"] == g["is_anion"] and set(h["elements"]) == set(g["elements"])
                     and (g["is_anion"] or abs(h["size"] - g["size"]) <= 0.2 * max(h["size"], g["size"]))), None)
        if twin:
            twin["slots"] += g["slots"]
            twin["elements"] += g["elements"]
            twin["obs_states"] += g["obs_states"]
        else:
            out.append(dict(g))
    cations = [g for g in out if not g["is_anion"]]
    anions = [g for g in out if g["is_anion"]]
    for i, g in enumerate(cations):
        g["name"] = CATION_NAMES[i] if i < len(CATION_NAMES) else f"M{i + 1}"
    for i, g in enumerate(anions):
        g["name"] = "X" if len(anions) == 1 else f"X{i + 1}"
    for g in out:
        states = {}
        observed = {}
        for (el, q), _n in g["obs_states"].items():
            observed.setdefault(el, set()).add(q)
        for el in sorted(g["elements"], key=lambda e: (-g["elements"][e], e)):
            want = (lambda q: q < 0) if g["is_anion"] else (lambda q: q > 0)
            qs = sorted(q for q in observed.get(el, ()) if want(q))
            if not qs:                                  # never charge-balanced in this dataset: fall back to pymatgen
                qs = sorted(q for q in Element(el).common_oxidation_states if want(q))
            if qs:
                states[el] = qs
        g["dropped"] = [e for e in g["elements"] if e not in states]
        g["elements"] = list(states)
        g["states"] = states
    return out


def lattice_section(rep, structures, b_group, x_group, tol=0.01):
    """The prototype cell (cubic when the representative is, else its general cell) and the bond_sum lattice rule, whose
    factor is the observed ratio of the first cell edge to r_B + r_X rather than an assumed 2.0."""
    L = rep.lattice
    cubic = max(abs(L.a - L.b), abs(L.a - L.c)) <= tol * L.a and max(abs(x - 90) for x in L.angles) <= 0.5
    ratios, edges = [], []
    bi, xi = b_group["slots"][0], x_group["slots"][0]
    for s in structures:
        try:
            ordered = order_sites_by_role(s)
        except Exception:
            continue
        r = ionic_radius(ordered[bi].specie.symbol) + ionic_radius(ordered[xi].specie.symbol)
        ratios.append(s.lattice.a / r)
        edges.append(s.lattice.a)
    cell = {"lattice": "cubic"} if cubic else dict(zip(("lattice", "a", "b", "c", "alpha", "beta", "gamma"),
                                                       ["general", L.a, L.b, L.c, *L.angles]))
    cell["reference_a"] = float(np.median(edges))
    rule = {"rule": "bond_sum", "groups": [b_group["name"], x_group["name"]], "factor": float(np.median(ratios)),
            "min": 0.85 * min(edges), "max": 1.15 * max(edges)}
    return cell, rule


def write_yaml(path, name, prototype, intake, n_used, groups, frac, cell, rule, order, constraints):
    def num(v):
        return f"{v:.4g}"
    pattern = "".join(g["name"] + (str(len(g["slots"])) if len(g["slots"]) > 1 else "") for g in groups)
    L = [f"# Generated by eval/auto_family.py on {datetime.date.today()} from the intake folder {os.path.basename(os.path.normpath(intake)) or intake}",
         f"# prototype {prototype}, inferred from {n_used} train.csv structures. Regenerate rather than hand-edit.",
         f"name: {name}",
         f"title: {pattern} prototype, detected automatically from the dataset",
         "description: >",
         f"  Prototype {prototype} as a {cell['lattice']} cell with {len(frac)} atoms; site groups, elements and charges",
         "  inferred from the structures of that prototype in the intake's train.csv.",
         "prototype:"]
    for k, v in cell.items():
        L.append(f"  {k}: {v if isinstance(v, str) else num(v)}")
    L.append("  sites:")
    for g in groups:
        for i in g["slots"]:
            f = np.round(frac[i], 4)
            L.append(f"    - {{group: {g['name']}, frac: [{f[0]}, {f[1]}, {f[2]}]}}")
    L.append("groups:")
    for g in groups:
        L.append(f"  {g['name']}:")
        L.append(f"    description: {g['description']}")
        L.append(f"    elements: [{', '.join(g['elements'])}]")
        L.append("    oxidation_states: {" + ", ".join(f"{e}: [{', '.join(map(str, q))}]" for e, q in g["states"].items()) + "}")
    L.append(f"sampling_order: [{', '.join(order)}]")
    L.append("lattice:")
    for k, v in rule.items():
        L.append(f"  {k}: {v if isinstance(v, str) else ('[' + ', '.join(v) + ']' if isinstance(v, list) else num(v))}")
    L.append("constraints:")
    for c in constraints:
        inner = ", ".join(f"{k}: {v if not isinstance(v, list) else '[' + ', '.join(v) + ']'}" for k, v in c.items())
        L.append(f"  - {{{inner}}}")
    L.append("refine_symmetry: true")
    open(path, "w").write("\n".join(L) + "\n")


def goal(family_path, intake, props):
    """Minimal generation config, built the way eval_generate.goal() builds its own, to get a Family object."""
    g = dict(family=family_path, seed=0, per_target=1,
             objectives=[dict(property=props[0], loss="l2", weight=1.0)], targets=[{props[0]: 0.0}])
    return config_from_dict({"name": "auto_family", "output_dir": "unused",
                             "data": {"table": f"{intake}/train.csv", "properties": [{"column": p} for p in props]},
                             "generation": g}, base_dir=".")


def verify(out_yaml, intake, props):
    fam = family_for(goal(os.path.abspath(out_yaml), intake, props), need_variant=True)
    print(fam.describe())
    space = enumerate_space(fam)
    rows = space["rows"]
    ok = [r for r in rows if all(r["ok"].values())]
    print(f"{space['total']} compositions in the space, {len(rows)} enumerated (the rest repeat an element across "
          f"groups), {len(ok)} pass all rules")
    rejected = collections.Counter(k for r in rows for k, v in r["ok"].items() if not v)
    for k, n in rejected.most_common():
        print(f"  rejected by {k}: {n}")
    if ok:
        print("  examples: " + ", ".join(r["f"] for r in ok[:8]))
    else:
        raise SystemExit("FAILED: no composition of the generated family passes its rules (see the counts above)")
    return len(rows), len(ok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("intake"); ap.add_argument("out_yaml")
    ap.add_argument("--prototype", help="default: the most common prototype of prototypes.csv")
    ap.add_argument("--name", help="family name (default: the stem of out_yaml)")
    ap.add_argument("--exclude-elements", nargs="*", default=RADIOACTIVE + OXYANION_FORMERS,
                    help="elements never placed on a cation site (default: radioactive elements and oxyanion formers)")
    ap.add_argument("--rules", choices=["perovskite", "minimal"], default="perovskite",
                    help="perovskite = charge, distances, tolerance and octahedral factors; minimal = charge and distances "
                         "only, for polymorph templates whose ground state is decided by the model (an ilmenite template "
                         "must not be filtered by a perovskite tolerance factor)")
    a = ap.parse_args()
    protos = list(csv.DictReader(open(f"{a.intake}/prototypes.csv")))
    proto = a.prototype or protos[0]["prototype"]
    count = next((p["count"] for p in protos if p["prototype"] == proto), "?")
    structures, dropped = read_prototype_rows(a.intake, proto)
    print(f"prototype {proto}: {count} structures in the intake, {len(structures)} of them in train.csv with the "
          f"prototype's own cell ({dropped} supercells dropped)")
    rep = order_sites_by_role(sorted(structures, key=lambda s: s.volume)[len(structures) // 2])
    frac = rep.frac_coords % 1.0
    seen, anion_hits, used, obs_states = census(structures, len(rep))
    groups = build_groups(rep, seen, anion_hits, used, obs_states)
    excluded = set(a.exclude_elements or [])
    for g in groups:
        if not g["is_anion"]:
            gone = [e for e in g["elements"] if e in excluded]
            g["elements"] = [e for e in g["elements"] if e not in excluded]
            g["states"] = {e: q for e, q in g["states"].items() if e not in excluded}
            g["dropped"] = list(g.get("dropped", [])) + [f"{e} (excluded)" for e in gone]
    cations = [g for g in groups if not g["is_anion"]]
    anions = [g for g in groups if g["is_anion"]]
    if not cations or not anions:
        raise SystemExit(f"{proto}: inferred {len(cations)} cation and {len(anions)} anion groups; need at least one of each")
    b_group = cations[-1]                      # smallest cation: the octahedral B site of a perovskite-like prototype
    x_group = max(anions, key=lambda g: len(g["slots"]))
    for g in groups:
        role = "anion" if g["is_anion"] else "smallest cation (octahedral in a perovskite)" if g is b_group \
            else "largest cation" if g is cations[0] else "cation"
        n = len(g["slots"])
        g["description"] = f"{role} on {n} site{'s' if n > 1 else ''}; mean distance to its 6 nearest neighbours is " \
                           f"{g['size']:.2f} A in the representative cell"
    cell, rule = lattice_section(rep, structures, b_group, x_group)
    # the cation with the most charge options balances the rest, so it is sampled last
    balancer = max(cations, key=lambda g: (np.mean([len(q) for q in g["states"].values()]), -g["size"]))
    order = [g["name"] for g in anions] + [g["name"] for g in cations if g is not balancer] + [balancer["name"]]
    constraints = [{"name": "min_distance", "min": 0.8}, {"name": "charge_neutrality"},
                   {"name": "bond_window", "from": x_group["name"], "to": b_group["name"],
                    "low": 0.75, "high": 1.35, "cutoff": 5.0}]
    others = [g["name"] for g in cations if g is not b_group]
    if a.rules == "minimal":
        constraints = constraints[:2]                  # charge neutrality and minimum distance only
    elif others:
        constraints.append({"name": "tolerance_factor", "A": others if len(others) > 1 else others[0],
                            "B": b_group["name"], "X": x_group["name"], "min": 0.78, "max": 1.08})
    if a.rules == "perovskite":
        constraints.append({"name": "octahedral_factor", "B": b_group["name"], "X": x_group["name"],
                            "min": 0.414, "max": 0.90})
    name = a.name or os.path.splitext(os.path.basename(a.out_yaml))[0]   # name == file stem, so --family <name> works
    write_yaml(a.out_yaml, name, proto, a.intake, used, groups, frac, cell, rule, order, constraints)
    for g in groups:
        print(f"group {g['name']}: {len(g['slots'])} site(s), {len(g['elements'])} elements "
              f"[{', '.join(g['elements'])}]" + (f"; no usable charge: {', '.join(g['dropped'])}" if g["dropped"] else ""))
    print(f"cell {cell['lattice']}, reference_a {cell['reference_a']:.3f} A, bond_sum factor {rule['factor']:.3f} "
          f"on [{', '.join(rule['groups'])}], a in [{rule['min']:.2f}, {rule['max']:.2f}] A")
    print(f"wrote {a.out_yaml}")
    verify(a.out_yaml, a.intake, [c for c in next(csv.reader(open(f"{a.intake}/train.csv"))) if c not in FIXED_COLUMNS])


if __name__ == "__main__":
    main()
