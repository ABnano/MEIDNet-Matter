"""How much room for discovery is there, and would allowing distorted perovskites fix stability?
For every composition of the demo family (Pb-free ABO3; all 462, flagged valid/invalid by the rules), query Materials Project:
in MP?, ground-state E_hull and space group, cubic (Pm-3m) E_hull, experimental or theoretical.  Cached in results/sun_cache.
Usage: python discovery_space.py   (fairchem-env, PYTHONPATH=meidnet_fix)"""
import json, os, sys, time, urllib.parse, urllib.request
import pandas as pd
from pymatgen.core import Composition

def _mp_api_key():
    """MP_API_KEY from the environment, else the contents of ~/.mp_api_key, else None (requests then fail with a clear 401)."""
    k = os.environ.get("MP_API_KEY")
    if k:
        return k.strip()
    p = os.path.expanduser("~/.mp_api_key")
    return open(p).read().strip() if os.path.exists(p) else None
def mp_entries(formula):
    path = f"{CACHE}/mp_{formula}.json"
    if os.path.exists(path):
        return json.load(open(path))
    url = "https://api.materialsproject.org/materials/summary/?" + urllib.parse.urlencode(
        {"formula": formula, "_fields": "material_id,formula_pretty,symmetry,energy_above_hull,band_gap,theoretical,structure,nsites", "_limit": 50})
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"X-API-KEY": KEY, "accept": "application/json", "User-Agent": "meidnet-sun-validate/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())["data"]
            json.dump(d, open(path, "w")); return d
        except Exception as e:
            time.sleep(2 * (attempt + 1)); err = e
    raise RuntimeError(err)

def main():
    """The script's work; nothing runs on import."""
    HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
    from meidnet.designspace import enumerate_space
    from meidnet.pipeline import family_for
    try:
        from meidnet_eval.eval_generate import goal
    except ImportError:          # run as a plain script from eval/
        from eval_generate import goal
    try:
        from meidnet_eval.eval_analyse import MATERIALS
    except ImportError:          # run as a plain script from eval/
        from eval_analyse import MATERIALS



    KEY = _mp_api_key()
    CACHE = f"{HERE}/results/sun_cache"; os.makedirs(CACHE, exist_ok=True)




    fam = family_for(goal(2.0, 1, 6), need_variant=True)
    fam.constraints = [c for c in fam.constraints if c["name"] != "property_window"]
    space = enumerate_space(fam, None)
    perov5 = set(pd.read_csv(MATERIALS).site_key.dropna())
    rows = []
    for r in space["rows"]:
        e = r["e"]; key = f"{e['A']}|{e['B']}|{e['X']}"
        formula = Composition(f"{e['A']}{e['B']}{e['X']}3").reduced_formula
        mp = mp_entries(formula)
        gs = min(mp, key=lambda m: m["energy_above_hull"]) if mp else None
        cub = [m for m in mp if m["symmetry"]["symbol"] == "Pm-3m"]
        rows.append(dict(key=key, formula=formula, valid_rules=all(r["ok"].values()), in_perov5=key in perov5, in_mp=bool(mp),
                         mp_experimental=any(not m["theoretical"] for m in mp), gs_ehull=gs["energy_above_hull"] if gs else None,
                         gs_spacegroup=gs["symmetry"]["symbol"] if gs else None, gs_gap=gs["band_gap"] if gs else None,
                         cubic_ehull=min(m["energy_above_hull"] for m in cub) if cub else None))
    D = pd.DataFrame(rows); D.to_csv(f"{HERE}/results/discovery_space.csv", index=False)
    print(f"family: {len(D)} compositions; valid by rules {int(D.valid_rules.sum())}; in Perov-5 {int(D.in_perov5.sum())}; "
          f"in MP {int(D.in_mp.sum())} (experimental {int(D.mp_experimental.sum())})")
    for name, sel in (("valid by rules", D.valid_rules), ("all compositions", D.valid_rules | ~D.valid_rules)):
        s = D[sel]
        nov = s[~s.in_perov5]
        print(f"\n{name}: {len(s)} | new to Perov-5 {len(nov)} | of those absent from MP {int((~nov.in_mp).sum())}")
        m = nov[nov.in_mp]
        print(f"   new to Perov-5 and in MP: ground state E_hull <= 0.1 for {int((m.gs_ehull <= 0.1).sum())}/{len(m)} "
              f"(<= 0.025: {int((m.gs_ehull <= 0.025).sum())}); cubic entry present for {int(m.cubic_ehull.notna().sum())}, "
              f"cubic E_hull <= 0.1 for {int((m.cubic_ehull <= 0.1).sum())}")
        print("   ground-state space groups:", m.gs_spacegroup.value_counts().head(8).to_dict())
        print("   absent from MP:", ", ".join(nov[~nov.in_mp].formula.tolist()[:40]))


if __name__ == "__main__":
    main()
