"""Build a second, realistic perovskite dataset from Materials Project (a stand-in for "a user uploads their own data"):
ternary oxides with ABO3 stoichiometry, <= 40 sites, E_hull <= 0.3 eV/atom, kept only if the structure is geometrically a
perovskite (any distortion): one cation B with 6 O neighbours (octahedron), every O bridging 2 B (corner sharing), the other
cation A with >= 8 O neighbours.  Properties: PBE band gap, formation energy per atom, E_hull.
Output: $MP_PEROVSKITES_OUT/{raw.jsonl, perovskites.csv, rejected.csv}  (default: ./mp_perovskites)
Usage: python mp_perovskite_dataset.py   (login node: needs internet; MP key in ~/.mp_api_key)"""
import csv, json, os, time, urllib.parse, urllib.request
import numpy as np
from pymatgen.core import Structure

def _mp_api_key():
    """MP_API_KEY from the environment, else the contents of ~/.mp_api_key, else None (requests then fail with a clear 401)."""
    k = os.environ.get("MP_API_KEY")
    if k:
        return k.strip()
    p = os.path.expanduser("~/.mp_api_key")
    return open(p).read().strip() if os.path.exists(p) else None


def get(params):
    url = "https://api.materialsproject.org/materials/summary/?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"X-API-KEY": KEY, "accept": "application/json", "User-Agent": "meidnet-dataset/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except Exception as e:
            err = e; time.sleep(3 * (attempt + 1))
    raise RuntimeError(err)
def perovskite_roles(s):
    """(A, B) element symbols if s is a corner-sharing BO6 perovskite with an A cation of >= 8 O neighbours, else None."""
    cats = sorted({sp.symbol for sp in s.species if sp.symbol != "O"})
    if len(cats) != 2:
        return None
    o_idx = [i for i, site in enumerate(s) if site.specie.symbol == "O"]
    stats = {}
    for el in cats:
        idx = [i for i, site in enumerate(s) if site.specie.symbol == el]
        counts, dmins = [], []
        for i in idx:
            nb = [n for n in s.get_neighbors(s[i], 4.0) if n.specie.symbol == "O"]
            if not nb:
                return None
            dmin = min(n.nn_distance for n in nb)
            counts.append(sum(1 for n in nb if n.nn_distance <= 1.25 * dmin)); dmins.append(dmin)
        stats[el] = (np.mean(counts), np.mean(dmins), idx)
    B = min(cats, key=lambda e: stats[e][1]); A = [e for e in cats if e != B][0]
    if not (abs(stats[B][0] - 6) < 0.01):
        return None
    dB = stats[B][1] * 1.25
    for i in o_idx:                                        # every O bridges exactly two B
        nB = sum(1 for n in s.get_neighbors(s[i], dB) if n.specie.symbol == B)
        if nB != 2:
            return None
    for i in stats[B][2]:                                  # corner sharing only: each pair of B shares at most one O
        shared = {}                                        # (ilmenite / LiNbO3-type cells share edges and faces: excluded)
        for o in s.get_neighbors(s[i], dB):
            if o.specie.symbol != "O":
                continue
            for b in s.get_neighbors(o, dB):
                if b.specie.symbol == B and not (b.index == i and np.allclose(b.image, 0)):
                    k = (b.index, tuple(np.round(b.image, 0)))          # image is relative to the cell site, i.e. absolute
                    shared[k] = shared.get(k, 0) + 1
        if not shared or max(shared.values()) > 1:
            return None
    nA = [sum(1 for n in s.get_neighbors(s[i], 3.6) if n.specie.symbol == "O") for i in stats[A][2]]
    if np.mean(nA) < 8:
        return None
    return A, B

def main():
    """The script's work; nothing runs on import."""
    KEY = _mp_api_key()
    OUT = os.environ.get("MP_PEROVSKITES_OUT", "mp_perovskites"); os.makedirs(OUT, exist_ok=True)
    FIELDS = "material_id,formula_pretty,formula_anonymous,nsites,symmetry,band_gap,formation_energy_per_atom,energy_above_hull,theoretical,structure"




    raw_path = f"{OUT}/raw.jsonl"
    if not os.path.exists(raw_path):
        skip, n = 0, 0
        with open(raw_path, "w") as f:
            while True:
                d = get({"elements": "O", "nelements_min": 3, "nelements_max": 3, "nsites_max": 40, "energy_above_hull_max": 0.3,
                         "_fields": FIELDS, "_limit": 500, "_skip": skip})
                data = d.get("data", [])
                for m in data:
                    if m.get("formula_anonymous") == "ABC3":
                        f.write(json.dumps(m) + "\n"); n += 1
                print(f"skip {skip}: {len(data)} entries, {n} ABO3 so far", flush=True)
                if len(data) < 500:
                    break
                skip += 500




    rows, rej = [], []
    for line in open(raw_path):
        m = json.loads(line)
        s = Structure.from_dict(m["structure"])
        try:
            roles = perovskite_roles(s)
        except Exception:
            roles = None
        rec = dict(material_id=m["material_id"], formula=m["formula_pretty"], nsites=m["nsites"], spacegroup=m["symmetry"]["symbol"],
                   band_gap=m["band_gap"], formation_energy_per_atom=m["formation_energy_per_atom"], e_hull=m["energy_above_hull"],
                   theoretical=m["theoretical"])
        if roles:
            rec.update(A=roles[0], B=roles[1], cif=s.to(fmt="cif")); rows.append(rec)
        else:
            rej.append(rec)
    for name, data in (("perovskites.csv", rows), ("rejected.csv", rej)):
        if data:
            with open(f"{OUT}/{name}", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(data[0].keys())); w.writeheader(); w.writerows(data)
    sg = {}
    for r in rows:
        sg[r["spacegroup"]] = sg.get(r["spacegroup"], 0) + 1
    print(f"ABO3 entries {len(rows) + len(rej)}: perovskites {len(rows)}, rejected {len(rej)}; space groups {dict(sorted(sg.items(), key=lambda kv: -kv[1])[:10])}")


if __name__ == "__main__":
    main()
