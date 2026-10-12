"""S.U.N. validation of generated perovskites (Stable, Unique, Novel) + independent band-gap check.  Run in megnet-env.

For every distinct generated composition (results/<tag>/candidates.csv):
  structure   relax the generated cubic cell with TensorNet-PES-MatPES-PBE (MLIP)
  novelty     not in Perov-5 (the training data; guaranteed by the novelty rule) and its status in Materials Project:
              absent / theoretical only / experimental (ICSD-matched)
  stability   energy above the convex hull of the CUBIC perovskite:
                (a) MP DFT value of MP's cubic (Pm-3m) entry when MP has one;
                (b) else MP's ground-state E_hull + MLIP energy difference (relaxed cubic - relaxed MP ground state);
                (c) else (composition absent from MP) MLIP hull against MP's competing phases relaxed with the same MLIP.
              stable := E_hull <= 0.1 eV/atom (common threshold for generative-model evaluation)
  formability Bartel et al. (Sci. Adv. 2019) tau = rX/rB - nA (nA - (rA/rB)/ln(rA/rB)) < 4.18 with Shannon radii
              (A: CN XII, B: CN VI, O: CN VI), oxidation states from charge balance
  band gap    MEGNet multi-fidelity @ GLLB-SC (Perov-5's functional) on the relaxed cell; MP PBE gap of the cubic/GS entry
Usage: python sun_validate.py TAG [TAG ...]     (MP API key read from ~/.mp_api_key)
"""
import json, math, os, sys, time, urllib.parse, urllib.request, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, torch
from pymatgen.core import Structure, Composition, Species
from pymatgen.analysis.phase_diagram import PhaseDiagram, PDEntry

HERE = os.path.dirname(os.path.abspath(__file__))
RES = f"{HERE}/results"
def _mp_api_key():
    """MP_API_KEY from the environment, else the contents of ~/.mp_api_key, else None (requests then fail with a clear 401)."""
    k = os.environ.get("MP_API_KEY")
    if k:
        return k.strip()
    p = os.path.expanduser("~/.mp_api_key")
    return open(p).read().strip() if os.path.exists(p) else None


KEY = _mp_api_key()
CACHE = f"{RES}/sun_cache"; os.makedirs(CACHE, exist_ok=True)


def mp_get(params):
    url = "https://api.materialsproject.org/materials/summary/?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"X-API-KEY": KEY, "accept": "application/json", "User-Agent": "meidnet-sun-validate/1.0 (pymatgen)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())["data"]
        except Exception as e:
            time.sleep(3 * (attempt + 1)); err = e
    raise RuntimeError(f"MP query failed: {err}")


def mp_entries(formula):
    path = f"{CACHE}/mp_{formula}.json"
    if os.path.exists(path):
        return json.load(open(path))
    d = mp_get({"formula": formula, "_fields": "material_id,formula_pretty,symmetry,energy_above_hull,band_gap,theoretical,structure,nsites", "_limit": 50})
    json.dump(d, open(path, "w")); return d


def mp_chemsys_entries(elements):
    from itertools import combinations
    out = []
    for n in range(1, len(elements) + 1):
        for sub in combinations(sorted(elements), n):
            path = f"{CACHE}/mpcs_{'-'.join(sub)}.json"
            if os.path.exists(path):
                out += json.load(open(path)); continue
            d = mp_get({"chemsys": "-".join(sub), "_fields": "material_id,formula_pretty,energy_above_hull,structure,nsites", "_limit": 200})
            json.dump(d, open(path, "w")); out += d
    return out


_relaxer = None
def relax(s, steps=400):
    global _relaxer
    if _relaxer is None:
        import matgl
        from matgl.ext.ase import Relaxer
        _relaxer = Relaxer(potential=matgl.load_model("TensorNet-PES-MatPES-PBE-2025.2"), relax_cell=True)
    r = _relaxer.relax(s, fmax=0.02, steps=steps)
    return r["final_structure"], float(r["trajectory"].energies[-1]) / len(s)


def relaxed_energy_mp(m):
    """MLIP energy per atom of a relaxed Materials Project phase, cached on disk by material_id (shared by all shards/jobs)."""
    path = f"{CACHE}/mlip_{m['material_id']}.json"
    if os.path.exists(path):
        try:
            return json.load(open(path))["e_per_atom"]
        except Exception:
            pass
    _, e = relax(Structure.from_dict(m["structure"]))
    tmp = f"{path}.{os.getpid()}.tmp"
    json.dump({"e_per_atom": e}, open(tmp, "w")); os.replace(tmp, path)
    return e


_megnet = None
def megnet_gap(s):
    global _megnet
    if _megnet is None:
        import matgl
        _megnet = matgl.load_model("MEGNet-BandGap-mfi-MP-2019.4.1")
    return max(0.0, float(_megnet.predict_structure(s, state_attr=torch.tensor([1]))))


def bartel_tau(A, B, comp=None):
    comp = comp or Composition(f"{A}{B}O3")
    for guess in comp.oxi_state_guesses(max_sites=-1):
        nA, nB = guess.get(A), guess.get(B)
        if nA is None or nB is None or nA <= 0 or nB <= 0:
            continue
        try:
            rA = None
            for cn in ("XII", "XI", "X", "IX", "VIII"):
                try:
                    rA = Species(A, int(nA)).get_shannon_radius(cn); break
                except Exception:
                    continue
            rB = None
            for spin in ("", "High Spin", "Low Spin"):
                try:
                    rB = Species(B, int(nB)).get_shannon_radius("VI", spin=spin); break
                except Exception:
                    continue
            radii, counts = [], []
            for el, amt in comp.items():
                if el.symbol in (A, B):
                    continue
                ox = guess.get(el.symbol)
                r = None
                for cn in ("VI", "IV", "II"):
                    try:
                        r = Species(el.symbol, int(ox)).get_shannon_radius(cn); break
                    except Exception:
                        continue
                radii.append(r); counts.append(amt)
            if rB is None or any(r is None for r in radii):
                continue
            rX = sum(r * c for r, c in zip(radii, counts)) / sum(counts)
        except Exception:
            continue
        if rA is None or rA <= rB:
            continue
        tau = rX / rB - nA * (nA - (rA / rB) / math.log(rA / rB))
        t = (rA + rX) / (math.sqrt(2) * (rB + rX))
        return tau, t, int(nA), int(nB)
    return float("nan"), float("nan"), None, None


def main():
    tags = sys.argv[1:]
    rows = []
    for tag in tags:
        d = pd.read_csv(f"{RES}/{tag}/candidates.csv")
        sites = [c for c in ("site_A", "site_B", "site_X", "site_X1", "site_X2") if c in d.columns]
        for r in d.to_dict("records"):
            rows.append(dict(tag=tag, target=r["target"], seed=r["seed"], key="|".join(str(r[c]) for c in sites),
                             label_gap=r["label_gap"], label_dhf=r["label_dhf"], file=f"{RES}/{tag}/{r['file']}"))
    C = pd.DataFrame(rows)
    out = []
    shard, nshards = int(os.environ.get("SHARD", "0")), int(os.environ.get("NSHARDS", "1"))
    distort = os.environ.get("DISTORT", "0") == "1"
    part = f"{RES}/sun_partial_{'_'.join(tags)[:60]}_shard{shard}.csv"
    done = set(pd.read_csv(part).key) if os.path.exists(part) else set()      # resume: skip compositions already saved
    for i_key, (key, g) in enumerate(C.groupby("key")):
        if i_key % nshards != shard or key in done:
            continue
        s0 = Structure.from_file(g.file.iloc[0])
        A, B = key.split("|")[:2]
        formula = s0.composition.reduced_formula
        elements = sorted({el.symbol for el in s0.composition.elements})
        s, e_cubic = relax(s0)
        kind = "cubic" if len(s0) == 5 else "template"
        if distort and len(s0) == 5:   # tilted-octahedra polymorphs: sqrt2 x sqrt2 x 2 supercell from two rattled starts
            for seed, amp in ((0, 0.08), (1, 0.15)):
                sup = s0.copy(); sup.make_supercell([[1, 1, 0], [-1, 1, 0], [0, 0, 2]])
                rng = np.random.RandomState(seed)
                sup = Structure(sup.lattice, sup.species, sup.cart_coords + rng.normal(0, amp, (len(sup), 3)), coords_are_cartesian=True)
                s_d, e_d = relax(sup, steps=800)
                if e_d < e_cubic - 1e-4:
                    s, e_cubic, kind = s_d, e_d, "distorted"
        elif distort:    # a polymorph template already carries its tilts: one rattled restart of the same cell is enough
            rng = np.random.RandomState(0)
            s_r = Structure(s0.lattice, s0.species, s0.cart_coords + rng.normal(0, 0.08, (len(s0), 3)), coords_are_cartesian=True)
            s_d, e_d = relax(s_r, steps=800)
            if e_d < e_cubic - 1e-4:
                s, e_cubic, kind = s_d, e_d, "distorted"
        try:
            from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
            sg = SpacegroupAnalyzer(s, symprec=0.1).get_space_group_symbol()
        except Exception:
            sg = "?"
        mp = mp_entries(formula)
        cubic = [m for m in mp if m["symmetry"]["symbol"] == "Pm-3m"]
        mp = [m for m in mp if m.get("energy_above_hull") is not None]
        gs = min(mp, key=lambda m: m["energy_above_hull"]) if mp else None
        if cubic and kind == "cubic":
            c = min(cubic, key=lambda m: m["energy_above_hull"])
            ehull, source, mp_gap = c["energy_above_hull"], "MP DFT (cubic entry " + c["material_id"] + ")", c["band_gap"]
        elif gs:
            e_gs = relaxed_energy_mp(gs)
            ehull, source, mp_gap = gs["energy_above_hull"] + (e_cubic - e_gs), "MP ground state " + gs["material_id"] + " + MLIP polymorph energy", gs["band_gap"]
        else:
            ents = [PDEntry(s.composition, e_cubic * len(s), name="candidate")]
            allm = mp_chemsys_entries(elements)
            elemental = {}                                  # every element's terminal entry is always needed by the hull
            for m in allm:
                st_el = Composition(m["formula_pretty"]).elements
                if len(st_el) == 1:
                    elemental.setdefault(st_el[0].symbol, []).append(m)
            keep_ids = set()
            for el, ms in elemental.items():
                known = [m for m in ms if m.get("energy_above_hull") is not None]
                if known:
                    keep_ids.add(min(known, key=lambda m: m["energy_above_hull"])["material_id"])
                else:                                       # MP gives no E_hull (Yb): keep every small polymorph, the MLIP hull picks
                    keep_ids |= {m["material_id"] for m in ms if (m.get("nsites") or 99) <= 40}
            for m in allm:
                st = Structure.from_dict(m["structure"])
                near = m.get("energy_above_hull") is not None and m["energy_above_hull"] <= 0.05
                if m["material_id"] not in keep_ids and (len(st) > 40 or not near):     # phases that can define the hull
                    continue
                e = relaxed_energy_mp(m)
                ents.append(PDEntry(st.composition, e * len(st), name=m["material_id"]))
            mp_gap = float("nan")
            try:
                ehull, source = PhaseDiagram(ents).get_e_above_hull(ents[0]), "absent from MP: MLIP hull vs MP competing phases"
            except ValueError as e:                         # e.g. an element without any terminal entry: record it, keep the shard alive
                ehull, source = float("nan"), f"hull failed ({e})"
        if not mp:
            mp_status = "absent from MP"
        elif all(m["theoretical"] for m in mp):
            mp_status = "in MP (theoretical only)"
        else:
            mp_status = "in MP (experimental/ICSD)"
        tau, t, nA, nB = bartel_tau(A, B, s0.composition)
        gap_mg = megnet_gap(s)
        out.append(dict(key=key, formula=formula, targets=sorted(set(g.target)), n_returned=len(g), label_gap=g.label_gap.mean(),
                        megnet_gllbsc_gap=gap_mg, mp_pbe_gap=mp_gap, e_hull=ehull, stability_source=source,
                        a_relaxed=s0.lattice.a if kind != "cubic" else s.lattice.a, structure_kind=kind, spacegroup=sg, tau=tau, goldschmidt_t=t, oxidation=f"{A}{nA}+ {B}{nB}+", mp_status=mp_status))
        pd.DataFrame([out[-1]]).to_csv(part, mode="a", header=not os.path.exists(part), index=False)
        print(f"{formula:9s} targets {sorted(set(g.target))} label {g.label_gap.mean():.2f} | MEGNet {gap_mg:.2f} | MP PBE {mp_gap} | "
              f"E_hull {ehull:.3f} ({source.split(' (')[0].split(' + ')[0]}) | tau {tau:.2f} | {mp_status}", flush=True)
    V = pd.read_csv(part) if os.path.exists(part) else pd.DataFrame(out)      # the partial file holds the resumed rows too
    V["stable"] = V.e_hull <= 0.1
    V["formable"] = V.tau < 4.18
    ref_dir = os.environ.get("SUN_REFERENCE")          # the user's own intake directory: novelty against THEIR data
    if ref_dir:
        splits = os.environ.get("SUN_REFERENCE_SPLITS", "train,val,test").split(",")
        ref = set()
        for sp in splits:
            p = f"{ref_dir}/{sp}.csv"
            if os.path.exists(p):
                ref |= {Composition(f).reduced_formula for f in pd.read_csv(p, usecols=["formula"]).formula}
        V["novel_reference"] = ~V.formula.map(lambda f: Composition(f).reduced_formula).isin(ref)
        V["sun"] = V.stable & V.formable & V.novel_reference
    else:                                              # Perov-5 runs, unchanged
        perov5 = set(pd.read_csv(os.environ["EVAL_MATERIALS"]).site_key.dropna())
        V["novel_perov5"] = ~V.key.isin(perov5)        # checked explicitly (the novelty rule should make this always True)
        V["sun"] = V.stable & V.formable & V.novel_perov5
    tag = "_".join(tags)
    if nshards > 1:
        tag = f"{tag}_shard{shard}"
    V.to_csv(f"{RES}/sun_{tag}.csv", index=False)
    print(f"\n{len(V)} distinct novel compositions | stable (E_hull <= 0.1) {int(V.stable.sum())} | formable (tau < 4.18) "
          f"{int(V.formable.sum())} | S.U.N. {int(V.sun.sum())} | absent from MP {int((V.mp_status == 'absent from MP').sum())}")


if __name__ == "__main__":
    main()
