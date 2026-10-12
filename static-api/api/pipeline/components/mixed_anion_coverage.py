"""MP coverage of charge-balanced lanthanide mixed-anion perovskites (Ln3+ with O2N / ON2 / O2F anion sets of Perov-5)."""
import itertools, json, os, time, urllib.parse, urllib.request
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
    req = urllib.request.Request(url, headers={"X-API-KEY": KEY, "accept": "application/json", "User-Agent": "meidnet-sun-validate/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())["data"]
    json.dump(d, open(path, "w")); return d

def main():
    """The script's work; nothing runs on import."""
    KEY = _mp_api_key()
    CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "sun_cache")


    Ln = ["Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Yb"]
    combos = [(b, "O2N") for b in ("Ti", "Zr", "Hf", "Sn")] + [(b, "ON2") for b in ("Nb", "Ta")] + [(b, "O2F") for b in ("Mn", "Fe", "Co", "Ni")]
    tot = absent = 0; ex = []; present = []
    for ln, (b, x) in itertools.product(Ln, combos):
        red = Composition(f"{ln}{b}{x}").reduced_formula
        d = mp_entries(red); tot += 1
        if d: present.append((red, min(m["energy_above_hull"] for m in d)))
        else: absent += 1; ex.append(red)
    print(f"charge-balanced lanthanide mixed-anion perovskites: {tot}; absent from Materials Project: {absent} ({100*absent/tot:.0f}%)")
    print("present (min E_hull):", ", ".join(f"{f}({e:.2f})" for f, e in present[:15]))
    print("examples absent:", ", ".join(ex[:20]))


if __name__ == "__main__":
    main()
