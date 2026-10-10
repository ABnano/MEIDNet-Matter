"""Acceptance-test generation for the grounded-generation study.

Runs the MEIDNet engine (or a pure screening baseline) for band-gap targets 0..6 eV with the same goal as the
MEIDNet Matter demo (Pb-free ABO3 oxide, dHf <= 1 eV/atom, gap window target +/- 0.3 eV, 6 candidates per target,
population 24, up to 5 rounds of 300 steps) and writes one CSV row and one CIF per returned candidate.

  python eval_generate.py --tag G5 --ckpt model.pt --label-source structure --latent-space sphere --manifold-weight 1
  python eval_generate.py --tag S2 --ckpt model.pt --mode screen

Engine switches (each can be ablated on its own)
  --label-source latent|structure   latent = property decoder at the search latent (v1); structure = decode ->
                                    re-encode the returned structure -> predict (grounded labels)
  --latent-space clip|sphere        clip = v1 (latents grow to length 3-5); sphere = unit length like structure latents
  --manifold-weight w               pull towards training structure latents (0 = off)
Screen mode: no generation; enumerate every composition of the family, predict from the structure, keep the
per_target x len(seeds) compositions closest to the target that satisfy the windows.
"""
import argparse, csv, json, os, sys, time
import pandas as pd
import numpy as np
import torch
from pymatgen.core import Structure
from pymatgen.io.cif import CifWriter

from meidnet.checkpoint import load_checkpoint, property_ranges
from meidnet.config import config_from_dict
from meidnet.data import featurize
from meidnet.designspace import enumerate_space
from meidnet.generate import Designer
from meidnet.pipeline import family_for
from meidnet.constraints import build_candidate

DATA = os.environ.get("EVAL_DATA")   # the dataset folder; required (no built-in path)
csv.field_size_limit(10 ** 9)
# Which columns of the dataset are the target property and the secondary (stability-like) property.  Perov-5 names them
# dir_gap / heat_all; an intake directory from another dataset names them differently, so both are overridable and the
# whole harness follows the dataset instead of the Perov-5 column names.
GAP = os.environ.get("EVAL_GAP", "dir_gap")
COST = os.environ.get("EVAL_COST", "heat_all")
COST_MAX = float(os.environ.get("EVAL_COST_MAX", "1.0"))


def goal(target, seed, per_target, family="perovskite_abx3", variant="oxide", **switches):
    g = dict(family=family, variant=variant, exclude_elements=["Pb"], seed=seed,
             per_target=per_target, population=24, rounds=5, steps=300, min_cosine_sep=0.98, amp=False,
             objectives=[dict(property=GAP, loss="l2", weight=10000, select_weight=1.0),
                         dict(property=COST, loss="at_most", weight=6000, select_weight=0.4)],
             targets=[{GAP: float(target), COST: COST_MAX}],
             extra_constraints=[dict(name="property_window", property=GAP, min=max(0.0, target - 0.3), max=target + 0.3),
                                dict(name="property_window", property=COST, max=COST_MAX)])
    g.update(switches)
    return config_from_dict({"name": "eval", "output_dir": "unused",
                             "data": {"table": f"{DATA}/train.csv", "properties": [{"column": COST}, {"column": GAP}]},
                             "generation": g}, base_dir=".")


def reference_latents(lm, ckpt):
    cache = os.path.splitext(ckpt)[0] + ".train_latents.npy"
    if os.path.exists(cache):
        return np.load(cache)
    rows = list(csv.DictReader(open(f"{DATA}/train.csv")))
    X = np.stack([featurize(Structure.from_str(r["cif"], fmt="cif"), lm.model.max_sites) for r in rows])
    out = []
    with torch.no_grad():
        for i in range(0, len(X), 512):
            zc, _ = lm.model.encode_crystal(torch.tensor(X[i:i + 512], dtype=torch.float32))
            out.append(zc.numpy())
    Z = np.concatenate(out)
    tmp = f"{cache}.{os.getpid()}.tmp.npy"      # several processes may build the same cache at once: write atomically
    np.save(tmp, Z)
    os.replace(tmp, cache)
    return Z



def _value(v):
    """--set values: true/false, int, float, else the string itself (e.g. label_source=structure)."""
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v


def reference_pool(lm, ckpt, pool="all"):
    """Training structure latents to aim at / sample around. pool="family": only training compositions that are valid
    members of the demo family (Pb-free ABO3 oxides passing the rules)."""
    Z = reference_latents(lm, ckpt)
    if pool != "family":
        return Z
    import pandas as pd
    try:
        from meidnet_eval.eval_analyse import valid_compositions, MATERIALS
    except ImportError:          # run as a plain script from eval/
        from eval_analyse import valid_compositions, MATERIALS
    V, _ = valid_compositions()
    keys = {f"{v['site_A']}|{v['site_B']}|{v['site_X']}" for v in V}
    ids = [int(r["material_id"]) for r in csv.DictReader(open(f"{DATA}/train.csv"))]
    site = pd.read_csv(MATERIALS).set_index("material_id").site_key
    mask = np.array([site.get(i) in keys for i in ids])
    return Z[mask]


def known_compositions(data=None):
    """Reduced formulas present in the dataset splits.

    Novelty has to be judged on the COMPOSITION rather than on a site key: a site key encodes the family's group layout,
    so an ABX3-shaped key matches nothing for an A2BB'X6 family and the novelty rule then reports removing zero rows while
    compositions already in the data pass straight through (observed on the user's 246-structure upload: 5 of 60
    "novel" candidates were already there).
    """
    from pymatgen.core import Composition
    out = set()
    for split in ("train", "val", "test"):
        path = f"{data or DATA}/{split}.csv"
        if os.path.exists(path):
            for f in pd.read_csv(path, usecols=["formula"]).formula:
                try:
                    out.add(Composition(str(f)).reduced_formula)
                except Exception:
                    continue
    return out


def training_family_keys(fam):
    """Every composition of the TRAINING dataset expressed as a site key of `fam` ('A|B|...' in group order), for the
    novelty rule.  Perov-5 writes A first in its formula strings, but other datasets do not (Materials Project puts the
    B cation first for 177 of its 1073 perovskites), so both cation orders are recorded: over-excluding a composition is
    the safe error for a novelty rule, letting a known one through is not.
    """
    import re
    from collections import Counter
    keys = set()
    for split in ("train", "val", "test"):
        path = f"{DATA}/{split}.csv"
        if not os.path.exists(path):
            continue
        for r in csv.DictReader(open(path)):
            toks = re.findall(r"([A-Z][a-z]?)(\d*)", r["formula"])
            if len(toks) < 3:
                continue
            anions = Counter()
            for el, n in toks[2:]:
                anions[el] += int(n or 1)
            for A, B in ((toks[0][0], toks[1][0]), (toks[1][0], toks[0][0])):
                chosen, ok = {"A": A, "B": B}, True
                rest = Counter(anions)
                for g, grp in fam.groups.items():
                    if g in ("A", "B"):
                        continue
                    hit = [el for el in grp.elements if rest.get(el, 0) == len(grp.slots)]
                    if not hit:
                        ok = False; break
                    chosen[g] = hit[0]; rest[hit[0]] -= len(grp.slots)
                if ok and sum(v for v in rest.values() if v > 0) == 0 and set(chosen) == set(fam.groups):
                    keys.add("|".join(chosen[g] for g in fam.groups))
    return sorted(keys)


perov5_family_keys = training_family_keys          # the name other eval scripts already import


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True); ap.add_argument("--ckpt", required=True)
    ap.add_argument("--mode", choices=["engine", "screen"], default="engine")
    ap.add_argument("--label-source", choices=["latent", "structure"], default="latent")
    ap.add_argument("--latent-space", choices=["clip", "sphere"], default="clip")
    ap.add_argument("--manifold-weight", type=float, default=0.0)
    ap.add_argument("--targets", type=float, nargs="+", default=[0, 1, 2, 3, 4, 5, 6])
    ap.add_argument("--seeds", type=int, nargs="+", default=[101, 202, 303])
    ap.add_argument("--per-target", type=int, default=6)
    ap.add_argument("--query", action="append", default=[], metavar="PROP=VALUE",
                    help="property value for the property-latent query, e.g. --query heat_all=0 (repeatable)")
    ap.add_argument("--pool", choices=["all", "family"], default="all", help="reference latents to aim at / sample around")
    ap.add_argument("--novel-only", action="store_true", help="reject every composition present in Perov-5 (novelty rule)")
    ap.add_argument("--family", default="perovskite_abx3")
    ap.add_argument("--variant", default="oxide")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="extra generation setting, e.g. --set init_sigma=0.05 --set property_first=true (repeatable)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"))
    a = ap.parse_args()
    out = os.path.join(a.out, a.tag); os.makedirs(f"{out}/cifs", exist_ok=True)
    try:
        from meidnet_eval.stages import announce_dataset
    except ImportError:          # run as a plain script from eval/
        from stages import announce_dataset
    announce_dataset("eval_generate", DATA, target=GAP, second=COST, family=a.family, variant=a.variant)
    lm = load_checkpoint(a.ckpt, device="cpu")
    ranges = property_ranges(lm)
    rows, funnel = [], []
    t0 = time.time()
    if a.mode == "screen":
        # screen mode must honour --family / --variant too (it silently used the default family before)
        fam = family_for(goal(a.targets[0], a.seeds[0], a.per_target, family=a.family, variant=a.variant),
                         need_variant=bool(a.variant))
        fam.constraints = [c for c in fam.constraints if c["name"] != "property_window"]
        space = enumerate_space(fam, lm)
        ok = [r for r in space["rows"] if all(r["ok"].values())]
        print(f"screen: {len(space['rows'])} compositions enumerated, {len(ok)} pass the chemistry rules", flush=True)
        if a.novel_only:          # screening must be able to discover too: drop everything the dataset already contains
            from pymatgen.core import Composition
            known = known_compositions()
            before = len(ok)
            ok = [r for r in ok if Composition(r["f"]).reduced_formula not in known]
            try:
                from meidnet_eval.stages import warn_if_noop
            except ImportError:          # run as a plain script from eval/
                from stages import warn_if_noop
            warn_if_noop("screen: novelty rule", before, len(ok), reference_size=len(known))
        for t in a.targets:
            sel = [r for r in ok if r["p"][COST] <= COST_MAX and abs(r["p"][GAP] - t) <= 0.3]
            sel.sort(key=lambda r: abs(r["p"][GAP] - t))
            for k, r in enumerate(sel[:a.per_target * len(a.seeds)]):
                cand = build_candidate(fam, r["e"])
                path = f"{out}/cifs/T{t:g}_{k + 1}.cif"
                CifWriter(cand.raw).write_file(path)
                rows.append(dict(tag=a.tag, mode=a.mode, target=t, seed=0, formula=cand.formula(), **{f"site_{g}": e for g, e in r["e"].items()},
                                 label_gap=r["p"][GAP], label_dhf=r["p"][COST], latent_norm=np.nan, round=0,
                                 file=os.path.relpath(path, out)))
            funnel.append(dict(target=t, seed=0, in_window=len(sel), returned=min(len(sel), a.per_target * len(a.seeds))))
            print(f"target {t:g}: {len(sel)} compositions predicted in window", flush=True)
    else:
        switches = dict(label_source=a.label_source, latent_space=a.latent_space, manifold_weight=a.manifold_weight)
        for kv in a.set:
            k, v = kv.split("=", 1)
            switches[k] = _value(v)
        if a.query:
            switches["query_values"] = {kv.split("=")[0]: float(kv.split("=")[1]) for kv in a.query}
        if a.family != "perovskite_abx3":
            switches["family"], switches["variant"] = a.family, a.variant
        if a.novel_only:          # every composition of Perov-5 is excluded: candidates are novel w.r.t. the training data
            fam0 = family_for(goal(a.targets[0], a.seeds[0], a.per_target, **switches), need_variant=True)
            switches["exclude_compositions"] = perov5_family_keys(fam0)
        need_ref = a.manifold_weight > 0 or switches.get("search_mode") == "neighbours"
        ref = reference_pool(lm, a.ckpt, a.pool) if need_ref else None
        for t in a.targets:
            for seed in a.seeds:
                cfg = goal(t, seed, a.per_target, **switches)
                fam = family_for(cfg, need_variant=True)
                d = f"{out}/runs/T{t:g}_s{seed}"
                res = Designer(lm, fam, cfg.generation, device=torch.device("cpu"), log=lambda *x: None,
                               reference_latents=ref).run(d, ranges=ranges)
                for c in res.saved:
                    rows.append(dict(tag=a.tag, mode=f"{a.label_source}/{a.latent_space}/m{a.manifold_weight:g}", target=t, seed=seed, formula=c.formula,
                                     **{f"site_{g}": e for g, e in c.elements.items()},
                                     label_gap=c.predictions[GAP], label_dhf=c.predictions[COST],
                                     latent_norm=c.latent_norm, round=c.round, file=os.path.relpath(os.path.join(d, c.file), out)))
                tl = res.targets[0]
                funnel.append(dict(target=t, seed=seed, returned=len(res.saved), rounds_used=tl.rounds_used, attempts=tl.attempts,
                                   latents_decoded=tl.latents_decoded, latents_passing=tl.latents_passing,
                                   first_failure=dict(tl.first_failure)))
                print(f"{a.tag} target {t:g} seed {seed}: {len(res.saved)} candidates "
                      f"({', '.join(c.formula for c in res.saved)}) after {tl.rounds_used} round(s), {time.time() - t0:.0f}s", flush=True)
    with open(f"{out}/candidates.csv", "w", newline="") as f:
        keys = list(rows[0]) if rows else ["tag"]
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    json.dump(dict(tag=a.tag, mode=a.mode, ckpt=a.ckpt, label_source=a.label_source, latent_space=a.latent_space,
                   manifold_weight=a.manifold_weight, extra_settings=a.set, targets=a.targets, seeds=a.seeds,
                   seconds=time.time() - t0, funnel=funnel), open(f"{out}/run_info.json", "w"), indent=1)
    print(f"{a.tag}: {len(rows)} candidates in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
