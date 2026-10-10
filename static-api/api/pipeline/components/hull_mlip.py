"""Block S7 stability: energy above the convex hull, with ONE machine-learning potential for every phase.

Nothing is mixed: each candidate and every competing phase of its chemical system are relaxed by the same potential
(TensorNet-PES-MatPES-PBE by default, the one that relaxed the candidates) and the hull is built from those energies alone.
The competing phases come from a reference set of known crystals:

  jarvis:PATH   the JARVIS-DFT 3D dump, e.g. jdft_3d-12-12-2022.json (public, no account; doi:10.6084/m9.figshare.6815699)
  mp            the Materials Project (an API key in MP_API_KEY or ~/.mp_api_key)

Only phases that can shape the hull are relaxed: per sub-system, those within --near eV/atom of the reference's own DFT
hull and with at most --max-atoms atoms (two polymorphs per formula at most), plus every element's lowest phase.  Relaxed
energies are cached by reference id, so a second candidate in the same system, or a second run, costs nothing.

The estimate is calibrated, not assumed: --validate INTAKE --stability-col COL computes the same quantity for known
materials of your own dataset whose DFT hull energy is in COL, and reports the error, the rank correlation and how often
the two agree on "within 0.1 eV/atom of the hull".

A value is not read as a stability statement, and the stable share leaves it out, when the cell collapsed during the
relaxation (closest atoms nearer than 0.6 of their radii) or when it lies more than 0.1 eV/atom below every known phase of
its system: a new ground state rarely lies that deep, while a competing phase missing from the reference set (JARVIS-DFT
has few cesium compounds, for one) or a potential misled by an unusual cell produce exactly that.  Each such value keeps a
note with the reason; so does a relaxation stopped by the step limit (its e_hull is an upper estimate).

Usage: python hull_mlip.py RESULTS_DIR --reference jarvis:PATH|mp [--candidates FILE] [--cifs-dir DIR] [--workers 4]
       [--cache DIR] [--near 0.05] [--max-atoms 40] [--steps 200] [--potential tensornet]
       [--validate INTAKE --stability-col COL --validate-n 12]
Writes RESULTS_DIR/hull.json, e_hull (eV/atom), e_hull_note and e_hull_assessed columns in the candidates table (and in
candidates_consensus.csv when it is there), and RESULTS_DIR/hull_validation.json + .csv when --validate is given.
"""
import argparse
import itertools
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

STABLE_EV = 0.1          # within this distance of the hull a material counts as (meta)stable, the common screening line


def _relax_module():
    try:
        from meidnet_eval import d1_mlip_check as m
    except ImportError:
        import d1_mlip_check as m
    return m


# ───────────────────────── reference sets ─────────────────────────
class Reference:
    """Known crystals indexed by their element set.  phases_for(elements) returns the pruned competing phases of the
    chemical system: every sub-system's near-hull entries, each with an id, its structure and the reference's DFT hull."""

    def __init__(self, spec, near, max_atoms, cache, log=print):
        self.spec, self.near, self.max_atoms, self.cache, self.log = spec, near, max_atoms, cache, log
        self.by_elements = {}
        if spec.startswith("jarvis:"):
            self.kind = "jarvis"
            self._load_jarvis(spec.split(":", 1)[1])
        elif spec == "mp":
            self.kind = "mp"
            self.key = os.environ.get("MP_API_KEY") or (open(os.path.expanduser("~/.mp_api_key")).read().strip()
                                                       if os.path.exists(os.path.expanduser("~/.mp_api_key")) else None)
            if not self.key:
                raise SystemExit("--reference mp needs an API key in MP_API_KEY or ~/.mp_api_key")
        else:
            raise SystemExit("--reference must be jarvis:PATH or mp")

    def _load_jarvis(self, path):
        if not os.path.exists(path):
            raise SystemExit(f"{path} not found: the JARVIS-DFT 3D dump (jdft_3d-*.json) is public, see doi:10.6084/m9.figshare.6815699")
        t0 = time.time()
        data = json.load(open(path))
        for d in data:
            els = frozenset(d["atoms"]["elements"])
            eh = d.get("ehull")
            gap = d.get("optb88vdw_bandgap")
            self.by_elements.setdefault(els, []).append(dict(
                id=d["jid"], formula=d.get("formula"), nsites=len(d["atoms"]["elements"]),
                e_hull_ref=float(eh) if isinstance(eh, (int, float)) else np.nan, atoms=d["atoms"],
                gap_ref=float(gap) if isinstance(gap, (int, float)) else None))
        self.log(f"reference: JARVIS-DFT 3D, {len(data)} entries in {len(self.by_elements)} element sets ({time.time() - t0:.0f} s)")

    def _mp_entries(self, els):
        """All MP entries of one exact element set, cached on disk (the key is sent only to api.materialsproject.org)."""
        chemsys = "-".join(sorted(els))
        path = os.path.join(self.cache, "mp", f"{chemsys}.json")
        if os.path.exists(path):
            return json.load(open(path))
        params = {"chemsys": chemsys, "_fields": "material_id,formula_pretty,energy_above_hull,band_gap,structure,nsites", "_limit": 500}
        url = "https://api.materialsproject.org/materials/summary/?" + urllib.parse.urlencode(params)
        # the API's front end refuses Python's default user agent (Cloudflare error 1010), so name the client
        req = urllib.request.Request(url, headers={"X-API-KEY": self.key, "accept": "application/json",
                                                   "User-Agent": "meidnet (+https://github.com/ABnano/MEIDNet-Matter)"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    rows = json.load(r).get("data", [])
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
        out = [dict(id=m["material_id"], formula=m.get("formula_pretty"), nsites=m.get("nsites"),
                    e_hull_ref=float(m["energy_above_hull"]) if m.get("energy_above_hull") is not None else np.nan,
                    gap_ref=float(m["band_gap"]) if m.get("band_gap") is not None else None,
                    structure=m["structure"]) for m in rows]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(out, open(path, "w"))
        return out

    def _entries(self, els):
        return self._mp_entries(els) if self.kind == "mp" else self.by_elements.get(frozenset(els), [])

    def phases_for(self, elements, exclude_ids=()):
        keep = []
        elements = sorted(set(elements))
        for k in range(1, len(elements) + 1):
            for sub in itertools.combinations(elements, k):
                ents = [e for e in self._entries(sub) if e["id"] not in exclude_ids]
                if not ents:
                    continue
                if k == 1:                          # the element's lowest phase is always needed (a terminal of the hull)
                    small = [e for e in ents if e["nsites"] <= self.max_atoms] or ents
                    keep.append(min(small, key=lambda e: (np.nan_to_num(e["e_hull_ref"], nan=9.0), e["nsites"])))
                    continue
                near = [e for e in ents if e["e_hull_ref"] == e["e_hull_ref"] and e["e_hull_ref"] <= self.near
                        and e["nsites"] <= self.max_atoms]
                by_formula = {}
                for e in sorted(near, key=lambda e: e["e_hull_ref"]):
                    f = e["formula"]
                    if len(by_formula.setdefault(f, [])) < 2:     # two polymorphs per formula: the potential may reorder them
                        by_formula[f].append(e)
                keep += [e for v in by_formula.values() for e in v]
        return keep

    def match(self, formula):
        """The reference's entries of this exact composition, lowest hull energy first: is the candidate already known?"""
        from pymatgen.core import Composition
        comp = Composition(formula)
        key = comp.reduced_formula
        els = tuple(sorted(str(e) for e in comp.elements))
        hits = [e for e in self._entries(els) if Composition(e["formula"]).reduced_formula == key]
        return sorted(hits, key=lambda e: np.nan_to_num(e["e_hull_ref"], nan=9.0))

    def structure(self, e):
        from pymatgen.core import Lattice, Structure
        if "atoms" in e:
            a = e["atoms"]
            return Structure(Lattice(a["lattice_mat"]), a["elements"], a["coords"], coords_are_cartesian=bool(a.get("cartesian")))
        return Structure.from_dict(e["structure"])


# ───────────────────────── relaxation (one potential, a process pool) ─────────────────────────
def _init_worker(threads, potential):
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    import torch
    torch.set_num_threads(threads)
    _relax_module().relaxer(potential, quiet=True)


def _relax_task(task):
    rid, sdict, potential, steps, fmax = task
    from pymatgen.core import Structure
    try:
        s0 = Structure.from_dict(sdict)
        s1, rec = _relax_module().relax_one(s0, potential, steps, fmax)
        return rid, dict(ok=True, e_per_atom=float(rec[f"{potential}_energy_per_atom"]), natoms=len(s1),
                         composition=s1.composition.as_dict(), drop=rec.get(f"{potential}_drop_per_atom"),
                         converged=rec.get(f"{potential}_converged"), contact_ratio=rec.get(f"{potential}_contact_ratio"))
    except Exception as ex:
        return rid, dict(ok=False, error=f"{type(ex).__name__}: {str(ex)[:120]}")


def relax_all(tasks, potential, steps, fmax, workers, cache_file, log=print):
    """Relax every (id, structure) not yet in the cache; the cache is rewritten after each result, so a killed job keeps
    everything it finished."""
    cache = json.load(open(cache_file)) if os.path.exists(cache_file) else {}
    todo = [(rid, s.as_dict(), potential, steps, fmax) for rid, s in tasks if rid not in cache]
    log(f"relaxations: {len(tasks)} needed, {len(tasks) - len(todo)} in the cache, {len(todo)} to run with {workers} worker(s)")
    if not todo:
        return cache
    t0 = time.time()
    threads = max(1, min(4, (os.cpu_count() or 4) // max(1, workers)))
    if workers <= 1:
        _init_worker(threads, potential)
        results = map(_relax_task, todo)
    else:
        import multiprocessing as mp
        pool = mp.get_context("spawn").Pool(workers, initializer=_init_worker, initargs=(threads, potential))
        results = pool.imap_unordered(_relax_task, todo, chunksize=1)
    for i, (rid, res) in enumerate(results, 1):
        cache[rid] = res
        if i % 10 == 0 or i == len(todo):
            log(f"  {i}/{len(todo)} relaxed ({time.time() - t0:.0f} s)")
            json.dump(cache, open(cache_file, "w"))
    json.dump(cache, open(cache_file, "w"))
    if workers > 1:
        pool.close(); pool.join()
    return cache


# ───────────────────────── the hull ─────────────────────────
def hull_energy(comp_dict, e_per_atom, phases, cache, depth=False):
    """Energy above the hull of one structure against cached competing phases; (e_hull, decomposition, n_used, missing).
    With depth=True a fifth value: the energy relative to the hull of the known phases alone, the same composition's
    known entries included (negative when the structure lies below all of them: how much more stable than every known
    phase or combination it is predicted to be; a known compound found again sits near 0; above the hull, e_hull)."""
    from pymatgen.analysis.phase_diagram import PDEntry, PhaseDiagram
    from pymatgen.core import Composition
    comp = Composition(comp_dict)
    entries, names = [], {}
    for p in phases:
        r = cache.get(p["id"])
        if not r or not r.get("ok"):
            continue
        c = Composition(r["composition"])
        ent = PDEntry(c, r["e_per_atom"] * c.num_atoms, name=p["id"])
        entries.append(ent); names[p["id"]] = p.get("formula") or c.reduced_formula
    have = {str(e.composition.elements[0]) for e in entries if len(e.composition.elements) == 1}
    missing = sorted(str(el) for el in comp.elements if str(el) not in have)
    if missing:
        return (float("nan"), [], len(entries), missing) + ((float("nan"),) if depth else ())
    cand = PDEntry(comp, e_per_atom * comp.num_atoms, name="candidate")
    pd_ = PhaseDiagram(entries + [cand])
    e = float(pd_.get_e_above_hull(cand))
    decomp = sorted({names.get(d.name, d.composition.reduced_formula) for d in pd_.get_decomposition(comp).keys()})
    if not depth:
        return e, decomp, len(entries), []
    # not pymatgen's phase-separation energy, which leaves out every entry of the same composition and so measures a
    # rediscovered compound against the other compositions instead of against itself
    return e, decomp, len(entries), [], float(e_per_atom - PhaseDiagram(entries).get_hull_energy_per_atom(comp))


def struct_key(prefix, s):
    """Cache key of a structure by its content (rounded lattice, species and fractional coordinates)."""
    import hashlib
    txt = repr((np.round(s.lattice.matrix, 3).tolist(), [str(x.specie) for x in s], np.round(s.frac_coords % 1.0, 3).tolist()))
    return prefix + hashlib.sha1(txt.encode()).hexdigest()[:16]


def known_materials(intake, col):
    rows = []
    for split in ("train", "val", "test"):
        p = os.path.join(intake, f"{split}.csv")
        if os.path.exists(p):
            t = pd.read_csv(p)
            if col not in t.columns:
                raise SystemExit(f"{col} is not a column of {p}")
            rows.append(t[["material_id", "formula", "cif", col]].dropna(subset=[col]))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results_dir", help="folder whose candidates table names relaxed structures (check_candidates writes OUT/relaxed)")
    ap.add_argument("--reference", required=True, help="jarvis:PATH (the JARVIS-DFT 3D dump) or mp (Materials Project, needs an API key)")
    ap.add_argument("--candidates", default=None, help="table with a `file` column (default RESULTS_DIR/candidates.csv)")
    ap.add_argument("--cifs-dir", default=None, help="folder the `file` column is relative to (default RESULTS_DIR)")
    ap.add_argument("--potential", default="tensornet", choices=["tensornet", "chgnet"])
    ap.add_argument("--near", type=float, default=0.05, help="competing phases within this many eV/atom of the reference hull")
    ap.add_argument("--max-atoms", type=int, default=40)
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--fmax", type=float, default=0.05)
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    ap.add_argument("--cache", default=None, help="folder of cached relaxed energies (default RESULTS_DIR/hull_cache); share it across runs")
    ap.add_argument("--validate", default=None, metavar="INTAKE", help="also compute the hull for known materials of this intake ...")
    ap.add_argument("--stability-col", default=None, help="... whose DFT hull energy (eV/atom) is in this column")
    ap.add_argument("--validate-n", type=int, default=12)
    ap.add_argument("--reference-outlier", type=float, default=1.0,
                    help="a known material this far above its reference hull (eV/atom) is flagged as a reference problem")
    a = ap.parse_args(argv)
    from pymatgen.core import Composition, Structure

    cands_file = a.candidates or os.path.join(a.results_dir, "candidates.csv")
    cifs_dir = a.cifs_dir or a.results_dir
    cache_dir = a.cache or os.path.join(a.results_dir, "hull_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{a.potential}_relaxed.json")
    df = pd.read_csv(cands_file)
    print(f"{len(df)} candidate structure(s) in {cands_file}", flush=True)
    _relax_module().load_potential(a.potential)          # downloaded once here, before any worker starts
    ref = Reference(a.reference, a.near, a.max_atoms, cache_dir)

    # what has to be relaxed: the candidates, their competing phases, and the validation materials with theirs
    tasks, phases_of = [], {}
    structs, keys = {}, {}
    for _, r in df.iterrows():
        s = Structure.from_file(os.path.join(cifs_dir, r["file"]))
        cid = struct_key("cand:", s)
        keys[str(r["file"])] = cid
        structs[cid] = s; tasks.append((cid, s))
        els = tuple(sorted(str(e) for e in s.composition.elements))
        if els not in phases_of:
            phases_of[els] = ref.phases_for(els)
    val = None
    if a.validate:
        if not a.stability_col:
            raise SystemExit("--validate needs --stability-col (the column with the dataset's own DFT hull energy)")
        kn = known_materials(a.validate, a.stability_col)
        kn = kn[kn["cif"].map(lambda c: isinstance(c, str))]
        kn["nsites"] = [len(Structure.from_str(c, fmt="cif")) for c in kn["cif"]]
        kn["nel"] = kn["formula"].map(lambda f: len(Composition(f).elements))
        kn = kn[(kn["nsites"] <= a.max_atoms) & (kn["nel"] <= 5)].sort_values(a.stability_col).reset_index(drop=True)
        if len(kn) > a.validate_n:                       # spread over the whole stability range, deterministic
            kn = kn.iloc[np.unique(np.linspace(0, len(kn) - 1, a.validate_n).round().astype(int))].reset_index(drop=True)
        val = kn
        for _, r in kn.iterrows():
            s = Structure.from_str(r["cif"], fmt="cif")
            vid = struct_key("val:", s)
            keys["val:" + str(r["material_id"])] = vid
            structs[vid] = s; tasks.append((vid, s))
            els = tuple(sorted(str(e) for e in s.composition.elements))
            key = ("val", str(r["material_id"]), els)
            phases_of[key] = ref.phases_for(els, exclude_ids={str(r["material_id"])})
        print(f"validation: {len(kn)} known materials of {a.validate}, DFT hull {kn[a.stability_col].min():.3f}-{kn[a.stability_col].max():.3f} eV/atom", flush=True)
    seen = set()
    for phs in phases_of.values():
        for p in phs:
            if p["id"] not in seen:
                seen.add(p["id"]); tasks.append((p["id"], ref.structure(p)))
    print(f"chemical systems: {len([k for k in phases_of if not (isinstance(k, tuple) and k and k[0] == 'val')])} for the candidates; "
          f"competing phases to relax: {len(seen)}", flush=True)
    cache = relax_all(tasks, a.potential, a.steps, a.fmax, a.workers, cache_file)

    # candidates
    out = []
    for _, r in df.iterrows():
        cid = keys[str(r["file"])]
        res = cache.get(cid, {})
        els = tuple(sorted(str(e) for e in structs[cid].composition.elements))
        if not res.get("ok"):
            out.append(dict(file=r["file"], formula=r.get("formula"), e_hull=None, note=res.get("error", "not relaxed"))); continue
        e, decomp, n_used, missing, sep = hull_energy(res["composition"], res["e_per_atom"], phases_of[els], cache, depth=True)
        hits = ref.match(str(structs[cid].composition.reduced_formula))
        m0 = dict(id=hits[0]["id"], gap=hits[0].get("gap_ref"), e_hull=None if hits[0]["e_hull_ref"] != hits[0]["e_hull_ref"] else hits[0]["e_hull_ref"],
                  entries=len(hits)) if hits else None
        notes = [("no elemental reference for " + ", ".join(missing))] if missing else []
        # an e_hull that cannot be read as a stability statement: the cell collapsed during this relaxation, or it lies further
        # below every known phase than a new ground state plausibly does (a competing phase missing from the reference set
        # lowers the hull it is measured against; a potential can also be wrong on an unusual cell)
        doubtful = []
        cr = res.get("contact_ratio")
        if cr is not None and cr < _relax_module().COLLAPSED:
            doubtful.append(f"the cell collapsed on relaxation (closest atoms at {cr:.2f} of their radii)")
        if sep == sep and sep < -STABLE_EV:
            empty = ["-".join(p) for p in itertools.combinations(els, 2) if not ref._entries(p)]
            doubtful.append(f"{-sep:.2f} eV/atom below every known phase of its system, deeper than a new ground state plausibly lies"
                            + (f"; the reference set has no {', '.join(empty)} compound (try --reference mp)" if empty else ""))
        notes += doubtful
        if res.get("converged") is False:
            # the optimiser only goes downhill: the minimum it was heading for lies lower, so this e_hull is an upper estimate
            notes.append(f"relaxation stopped at the step limit ({a.steps}): an upper estimate")
        stuck = [p["id"] for p in phases_of[els] if cache.get(p["id"], {}).get("converged") is False]
        if stuck:
            notes.append(f"{len(stuck)} competing phase(s) stopped at the step limit")
        out.append(dict(file=r["file"], formula=r.get("formula"), e_hull=None if e != e else round(e, 4), decomposition=decomp,
                        competing_phases=n_used, reference_match=m0, relaxation_converged=res.get("converged"),
                        below_known_eV=round(-sep, 4) if sep == sep and sep < 0 else 0.0 if sep == sep else None,
                        assessed=not doubtful, note="; ".join(notes)))
    hull = dict(reference=a.reference if a.reference == "mp" else "jarvis:" + os.path.basename(a.reference.split(":", 1)[1]),
                potential=a.potential, near_eV=a.near, max_atoms=a.max_atoms, stable_line_eV=STABLE_EV, candidates=out)
    print(f"\n{'formula':22s} {'e_hull (eV/atom)':>17s}  phases  {'in the reference':28s} decomposes to")
    for o in out:
        eh = "-" if o["e_hull"] is None else f"{o['e_hull']:.3f}"
        rm = o.get("reference_match")
        known = (f"{rm['id']} (gap {rm['gap']:.2f} eV)" if rm and rm.get("gap") is not None else rm["id"]) if rm else "absent"
        print(f"{str(o['formula']):22s} {eh:>17s}  {o.get('competing_phases', 0):6d}  {known:28s} "
              + "; ".join(x for x in (", ".join(o.get("decomposition", [])), o.get("note", "")) if x))
    # the stable share counts only values that are stability statements; the others are reported, with their reason
    ok = [o["e_hull"] for o in out if o["e_hull"] is not None and o.get("assessed", True)]
    hull["not_assessed"] = int(sum(1 for o in out if o["e_hull"] is not None and not o.get("assessed", True)))
    if ok:
        hull["stable_share"] = float(np.mean([v <= STABLE_EV for v in ok]))
        print(f"within {STABLE_EV} eV/atom of the hull: {sum(v <= STABLE_EV for v in ok)} of {len(ok)}"
              + (f" ({hull['not_assessed']} more not assessed, see the notes)" if hull["not_assessed"] else ""), flush=True)

    # validation against the dataset's own DFT hull
    if val is not None and len(val):
        rows = []
        for _, r in val.iterrows():
            vid = keys["val:" + str(r["material_id"])]
            res = cache.get(vid, {})
            els = tuple(sorted(str(e) for e in structs[vid].composition.elements))
            if not res.get("ok"):
                continue
            e, decomp, n_used, missing = hull_energy(res["composition"], res["e_per_atom"],
                                                     phases_of[("val", str(r["material_id"]), els)], cache)
            if e == e:
                rows.append(dict(material_id=r["material_id"], formula=r["formula"], e_hull_dft=float(r[a.stability_col]),
                                 e_hull_mlip=round(e, 4), competing_phases=n_used, decomposition=", ".join(decomp)))
        v = pd.DataFrame(rows)
        if len(v):
            from scipy.stats import spearmanr
            err = np.abs(v.e_hull_dft - v.e_hull_mlip)
            # a known compound more than REFERENCE_OUTLIER eV/atom above its reference hull is a reference problem (f electrons
            # without +U, a failed calculation), not a stability fact: it is listed, and the statistics are given without it too
            out_mask = v.e_hull_dft > a.reference_outlier
            v["reference_outlier"] = out_mask
            clean = v[~out_mask]
            agree = float(np.mean((v.e_hull_dft <= STABLE_EV) == (v.e_hull_mlip <= STABLE_EV)))
            rho = float(spearmanr(v.e_hull_dft, v.e_hull_mlip).statistic) if len(v) > 2 else float("nan")
            rho_c = float(spearmanr(clean.e_hull_dft, clean.e_hull_mlip).statistic) if len(clean) > 2 else float("nan")
            hull["validation"] = dict(
                n=int(len(v)), mae_eV=float(err.mean()), median_abs_error_eV=float(err.median()), spearman=rho,
                agreement_within_stable_line=agree,
                reference_outliers=[f"{r.formula} (reference {r.e_hull_dft:.2f} eV/atom)" for r in v[out_mask].itertuples()],
                n_without_outliers=int(len(clean)),
                mae_eV_without_outliers=float(np.abs(clean.e_hull_dft - clean.e_hull_mlip).mean()) if len(clean) else None,
                spearman_without_outliers=rho_c,
                agreement_without_outliers=float(np.mean((clean.e_hull_dft <= STABLE_EV) == (clean.e_hull_mlip <= STABLE_EV))) if len(clean) else None,
                reference_column=a.stability_col, intake=os.path.basename(os.path.normpath(a.validate)))
            v.to_csv(os.path.join(a.results_dir, "hull_validation.csv"), index=False)
            json.dump(hull["validation"], open(os.path.join(a.results_dir, "hull_validation.json"), "w"), indent=1)
            hv = hull["validation"]
            print(f"\nvalidation on {len(v)} known materials against the dataset's DFT hull: MAE {hv['mae_eV']:.3f} eV/atom "
                  f"(median {hv['median_abs_error_eV']:.3f}), Spearman {rho:.2f}, agreement on 'within {STABLE_EV} eV/atom' {100 * agree:.0f}%", flush=True)
            if hv["reference_outliers"]:
                print(f"  reference values above {a.reference_outlier} eV/atom, implausible for a known compound: {', '.join(hv['reference_outliers'])}; "
                      f"without them (n = {hv['n_without_outliers']}): MAE {hv['mae_eV_without_outliers']:.3f} eV/atom, "
                      f"Spearman {rho_c:.2f}, agreement {100 * hv['agreement_without_outliers']:.0f}%", flush=True)

    json.dump(hull, open(os.path.join(a.results_dir, "hull.json"), "w"), indent=1, default=float)
    by_file = {o["file"]: o["e_hull"] for o in out}
    ref_gap = {o["file"]: (o["reference_match"] or {}).get("gap") for o in out}
    ref_id = {o["file"]: (o["reference_match"] or {}).get("id") for o in out}
    hull_note = {o["file"]: o.get("note", "") for o in out}
    assessed = {o["file"]: bool(o.get("assessed", False)) and o["e_hull"] is not None for o in out}
    df["e_hull"] = df["file"].map(by_file)
    df["e_hull_note"] = df["file"].map(hull_note)
    df["e_hull_assessed"] = df["file"].map(assessed)
    df["reference_id"] = df["file"].map(ref_id)
    df["reference_gap"] = df["file"].map(ref_gap)
    df.to_csv(cands_file, index=False)
    cons = os.path.join(a.results_dir, "candidates_consensus.csv")
    if os.path.exists(cons) and os.path.abspath(cons) != os.path.abspath(cands_file):
        c = pd.read_csv(cons)
        if "file" in c.columns:
            c["e_hull"] = c["file"].map(by_file)
            c["e_hull_note"] = c["file"].map(hull_note)
            c["e_hull_assessed"] = c["file"].map(assessed)
            c["reference_id"] = c["file"].map(ref_id)
            c["reference_gap"] = c["file"].map(ref_gap)
            c.to_csv(cons, index=False)
    print(f"\nwrote {a.results_dir}/hull.json and the e_hull column", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
