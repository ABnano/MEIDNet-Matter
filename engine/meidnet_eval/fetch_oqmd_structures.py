"""Stage 0 of discover.py: give a structure-less OQMD table its crystal structures, provably the ones its labels belong to.

A user table such as oqmd_data.csv has an OQMD entry id, a formula and property labels, but no CIF, and MEIDNet needs
structures.  For every distinct formula the OQMD REST API returns all of its polymorphs (unit cell + sites); rows are matched
by entry_id, rebuilt as pymatgen structures and VERIFIED against the table before they are kept:
  cell volume (relative 1e-3), and every label OQMD reports too: Eg vs band_gap, Ef vs delta_e, Es vs max(stability, 0)
  (the table clips the hull distance at 0) -- all within 1e-3.
A row that cannot be matched or fails a check is dropped and listed, never silently repaired.

  fetch   <table.csv> <out_dir> [--anion O] [--props Ef Eg Es] [--max-atoms 20] [--workers 4]
          -> out_dir/table.csv (material_id, cif, formula, spacegroup, natoms, icsd_id, experimental, props),
             out_dir/fetch_report.json, out_dir/oqmd_cache/<formula>.json (resumable cache)
  lookup  <candidates.csv|formulas.txt> <out.csv> [--cache DIR]
          -> for each formula: present in OQMD?, and if so its OQMD ground state (lowest stability): space group, band gap,
             formation energy, hull distance -- a free DFT check of a predicted candidate
Login node only (needs internet); polite: at most --workers concurrent requests, retries with back-off.
"""
import argparse, ast, csv, json, os, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

API = "https://oqmd.org/oqmdapi/formationenergy"
FIELDS = "name,entry_id,icsd_id,spacegroup,natoms,volume,band_gap,delta_e,stability,unit_cell,sites"
csv.field_size_limit(10 ** 9)


class Polite:
    """One request rate for all workers, adapted to what the server tolerates: OQMD answers '429 Too Many Requests' (no
    Retry-After) when pushed, so every 429 doubles the spacing and pauses everyone, and the spacing only shrinks again after
    a long run of successes (additive increase, multiplicative decrease)."""

    def __init__(self, interval=2.0, floor=1.0, ceiling=60.0):
        import threading
        self.lock, self.interval, self.floor, self.ceiling = threading.Lock(), interval, floor, ceiling
        self.next_slot, self.ok_streak, self.n429 = 0.0, 0, 0

    def wait(self):
        with self.lock:
            now = time.time()
            slot = max(now, self.next_slot)
            self.next_slot = slot + self.interval
        time.sleep(max(0.0, slot - time.time()))

    def success(self):
        with self.lock:
            self.ok_streak += 1
            if self.ok_streak >= 50:
                self.interval, self.ok_streak = max(self.floor, self.interval * 0.9), 0

    def throttled(self):
        with self.lock:
            self.n429 += 1
            self.ok_streak = 0
            self.interval = min(self.ceiling, self.interval * 2)
            self.next_slot = time.time() + 60.0          # everyone pauses for a minute before the next request


POLITE = Polite()


def query(formula, cache_dir, retries=5, timeout=240):
    """All OQMD entries of one formula, cached as JSON (an empty list is a valid, cached answer)."""
    import urllib.error
    path = os.path.join(cache_dir, f"{formula}.json")
    if os.path.exists(path):
        return json.load(open(path))
    url = f"{API}?{urllib.parse.urlencode({'composition': formula, 'fields': FIELDS, 'format': 'json', 'limit': 200})}"
    err, attempt = None, 0
    while attempt < retries:
        POLITE.wait()
        try:
            req = urllib.request.Request(url, headers={"accept": "application/json", "User-Agent": "meidnet-fetch/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read()).get("data", []) or []
            tmp = path + ".tmp"
            json.dump(data, open(tmp, "w"))
            os.replace(tmp, path)                       # atomic: a killed run never leaves a half-written cache file
            POLITE.success()
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429:                           # rate limited: not this formula's fault, so it costs no attempt
                POLITE.throttled()
                continue
            err = e
        except Exception as e:                          # timeout or network hiccup: back off and retry
            err = e
        attempt += 1
        time.sleep(3 * attempt)
    raise RuntimeError(f"{formula}: {err}")


def as_list(v):
    return ast.literal_eval(v) if isinstance(v, str) else v


def to_structure(entry):
    """pymatgen Structure from OQMD's unit_cell (3 lattice vectors) and sites ('El @ x y z', fractional)."""
    from pymatgen.core import Lattice, Structure
    species, coords = [], []
    for s in as_list(entry["sites"]):
        el, xyz = s.split("@")
        species.append(el.strip())
        coords.append([float(x) for x in xyz.split()])
    return Structure(Lattice(as_list(entry["unit_cell"])), species, coords)


def abx3(formula, anion):
    """(A, B) if the formula is A1 B1 X3 with two different cations and X == anion, else None."""
    toks = re.findall(r"([A-Z][a-z]?)(\d*)", formula)
    if len(toks) != 3 or [n or "1" for _, n in toks] != ["1", "1", "3"] or toks[2][0] != anion or toks[0][0] == toks[1][0]:
        return None
    return toks[0][0], toks[1][0]


def fetch(a):
    os.makedirs(os.path.join(a.out, "oqmd_cache"), exist_ok=True)
    t0 = time.time()
    d = pd.read_csv(a.table)
    n_rows = len(d)
    keep = d[a.formula_col].map(lambda f: abx3(str(f), a.anion) is not None) if a.anion else pd.Series(True, index=d.index)
    d = d[keep].copy()
    formulas = sorted(d[a.formula_col].unique())
    print(f"{n_rows} rows -> {len(d)} {a.anion or 'all'}-anion ABX3 rows, {len(formulas)} formulas to fetch", flush=True)
    cache = os.path.join(a.out, "oqmd_cache")
    entries, failed = {}, []

    def run_pass(todo, workers, timeout, retries, label):
        """Query `todo`; a slow formula only costs its own worker, and what times out is returned for the next pass."""
        left = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(query, f, cache, retries, timeout): f for f in todo}
            for k, fut in enumerate(as_completed(futs), 1):
                f = futs[fut]
                try:
                    for e in fut.result():
                        entries[int(e["entry_id"])] = e
                except Exception as e:
                    left.append((f, str(e)))
                if k % 200 == 0 or k == len(todo):
                    print(f"  [{label}] {k}/{len(todo)} formulas, {len(entries)} entries, {len(left)} deferred, "
                          f"{time.time() - t0:.0f}s | spacing {POLITE.interval:.1f}s, 429s so far {POLITE.n429}", flush=True)
        return left

    cached = [f for f in formulas if os.path.exists(os.path.join(cache, f"{f}.json"))]
    todo = [] if a.offline else [f for f in formulas if f not in set(cached)]
    for f in cached:
        for e in query(f, cache):
            entries[int(e["entry_id"])] = e
    print(f"{len(cached)} formulas already cached, {len(todo)} to query"
          + (" (offline: building the table from the cache only)" if a.offline else ""), flush=True)
    if todo:
        # most OQMD answers take < 2 s but a few take minutes: a short first pass with many workers, then the slow ones
        slow = run_pass(todo, a.workers, 45, 1, "pass 1, 45 s timeout")
        if slow:
            slow = run_pass([f for f, _ in slow], max(2, a.workers // 3), 300, 3, "pass 2, 300 s timeout")
        failed = [f"{f}: {e}" for f, e in slow]
    if a.offline:
        d = d[d[a.formula_col].isin(set(cached))]
    rows, dropped = [], {"not returned by OQMD": [], "volume mismatch": [], "label mismatch": [], "too many atoms": [],
                         "structure error": []}
    for r in d.itertuples(index=False):
        rd = r._asdict()
        eid = int(rd[a.id_col])
        e = entries.get(eid)
        if e is None:
            dropped["not returned by OQMD"].append(eid); continue
        try:
            s = to_structure(e)
        except Exception:
            dropped["structure error"].append(eid); continue
        if len(s) > a.max_atoms:
            dropped["too many atoms"].append(eid); continue
        if abs(s.volume - float(rd[a.vol_col])) > 1e-3 * float(rd[a.vol_col]):
            dropped["volume mismatch"].append(eid); continue
        checks = {"Eg": e.get("band_gap"), "Ef": e.get("delta_e"),
                  "Es": None if e.get("stability") is None else max(float(e["stability"]), 0.0)}
        if any(v is not None and c in rd and abs(float(v) - float(rd[c])) > 1e-3 for c, v in checks.items()):
            dropped["label mismatch"].append(eid); continue
        icsd = rd.get("icsd_id", 0)
        icsd = 0 if pd.isna(icsd) else int(icsd)
        rows.append(dict(material_id=eid, cif=s.to(fmt="cif"), formula=rd[a.formula_col], spacegroup=rd.get(a.sg_col, ""),
                         natoms=len(s), icsd_id=icsd, experimental=int(icsd != 0),
                         **{p: float(rd[p]) for p in a.props}))
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(a.out, "table.csv"), index=False)
    rep = dict(input_rows=n_rows, selected_rows=len(d), formulas=len(formulas), formulas_failed=failed,
               kept=len(out), kept_fraction=len(out) / max(len(d), 1),
               dropped={k: len(v) for k, v in dropped.items()}, dropped_examples={k: v[:20] for k, v in dropped.items()},
               natoms=out.natoms.value_counts().sort_index().to_dict() if len(out) else {},
               spacegroups=out.spacegroup.value_counts().head(12).to_dict() if len(out) else {},
               experimental=int(out.experimental.sum()) if len(out) else 0, seconds=round(time.time() - t0, 1),
               anion=a.anion, props=a.props, max_atoms=a.max_atoms)
    json.dump(rep, open(os.path.join(a.out, "fetch_report.json"), "w"), indent=1)
    print(f"kept {len(out)} of {len(d)} rows ({100 * rep['kept_fraction']:.1f}%), dropped {rep['dropped']}, "
          f"{len(failed)} formulas failed, {rep['seconds']:.0f}s -> {a.out}/table.csv", flush=True)


def lookup(a):
    """OQMD presence and ground state for candidate formulas (novelty check + free DFT values where present)."""
    src = a.source
    if src.endswith(".csv"):
        formulas = sorted(set(pd.read_csv(src).formula.astype(str)))
    else:
        formulas = sorted({l.strip() for l in open(src) if l.strip()})
    os.makedirs(a.cache, exist_ok=True)
    rows = []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futs = {pool.submit(query, f, a.cache): f for f in formulas}
        for fut in as_completed(futs):
            f = futs[fut]
            try:
                data = fut.result()
            except Exception as e:
                rows.append(dict(formula=f, oqmd_status=f"lookup failed: {e}")); continue
            data = [e for e in data if e.get("stability") is not None]
            if not data:
                rows.append(dict(formula=f, oqmd_status="absent from OQMD", oqmd_entries=0)); continue
            gs = min(data, key=lambda e: float(e["stability"]))
            rows.append(dict(formula=f, oqmd_status="in OQMD", oqmd_entries=len(data), oqmd_gs_entry=gs["entry_id"],
                             oqmd_gs_spacegroup=gs.get("spacegroup"), oqmd_gs_band_gap=gs.get("band_gap"),
                             oqmd_gs_delta_e=gs.get("delta_e"), oqmd_gs_stability=float(gs["stability"]),
                             oqmd_icsd=any((e.get("icsd_id") or 0) for e in data)))
    out = pd.DataFrame(rows).sort_values("formula")
    out.to_csv(a.out, index=False)
    print(f"{len(out)} formulas: {int((out.oqmd_status == 'in OQMD').sum())} in OQMD, "
          f"{int((out.oqmd_status == 'absent from OQMD').sum())} absent -> {a.out}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("table"); f.add_argument("out")
    f.add_argument("--anion", default="O", help="keep A B X3 rows with this anion ('' = keep all)")
    f.add_argument("--props", nargs="+", default=["Ef", "Eg", "Es"])
    f.add_argument("--id-col", default="entry_id"); f.add_argument("--formula-col", default="name")
    f.add_argument("--vol-col", default="vol"); f.add_argument("--sg-col", default="sg")
    f.add_argument("--max-atoms", type=int, default=20)
    f.add_argument("--workers", type=int, default=12)
    f.add_argument("--offline", action="store_true", help="no network: build the table from the formulas already cached")
    l = sub.add_parser("lookup")
    l.add_argument("source"); l.add_argument("out")
    l.add_argument("--cache", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "oqmd_lookup_cache"))
    l.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    fetch(a) if a.cmd == "fetch" else lookup(a)


if __name__ == "__main__":
    main()
