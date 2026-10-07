"""Stage 00, upload adapter: turn what a user actually has into the one table the pipeline reads.

Users do not arrive with a tidy CSV.  They arrive with a folder of VASP POSCARs or CIFs and a spreadsheet of properties, and
the two are joined by a file name.  This reads both, matches them, and writes the standard table
(material_id, cif, formula, natoms, <property columns>) that `intake.py` consumes — reporting every structure it could not
match and every property it could not parse, instead of quietly dropping rows.

  python ingest_upload.py <structure_dir> <table.csv|.xlsx> <out_dir> --props "Band gap DSH" dielectric [--header-rows 2]
      --id-col NAME       column holding the material name (default: the first column)
      --prefix POSCAR_    file-name prefix to strip when matching (default: strip 'POSCAR_' and any extension)
      --sheet NAME        spreadsheet sheet (default: the first)
Writes <out_dir>/table.csv and <out_dir>/ingest_report.json
"""
import argparse, json, os, re, unicodedata

import pandas as pd
from pymatgen.core import Structure


PHASE = re.compile(r"^(alpha|beta|gamma|delta|epsilon|H|M|T|O|C|R)[-_]", re.I)


def split_name(n: str):
    """(phase, chemistry, tag) from a name such as 'POSCAR_alpha-Ba2BiYO6' or 'Sr2MgMoO6-87'.

    Names cannot be compared as strings: a real upload writes the same material as 'Ba2YBiO6' in the spreadsheet and
    'POSCAR_alpha-Ba2BiYO6' as a file (different element order, phase prefix on one side only), and appends a space-group
    tag to some rows ('Sr2MgMoO6-87').  So the phase label is separated from the chemistry, and the chemistry is compared
    as a composition, which does not depend on the order the elements were written in.
    """
    n = re.sub(r"^POSCAR[_\-.]?", "", str(n).strip())
    n = re.sub(r"\.(cif|vasp|poscar|txt)$", "", n, flags=re.I)
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
    n = n.replace("–", "-").replace("—", "-").replace("_", "-")
    m = PHASE.match(n)
    phase = m.group(1).lower() if m else ""
    rest = n[m.end():] if m else n
    tag = ""
    mt = re.search(r"-(\d+)$", rest)                  # trailing space-group number used as a polymorph tag
    if mt:
        tag, rest = mt.group(1), rest[:mt.start()]
    return phase, rest.strip("-"), tag


def composition_of(text):
    from pymatgen.core import Composition
    try:
        return Composition(text).reduced_composition
    except Exception:
        return None


def read_table(path, sheet, header_rows):
    if path.lower().endswith((".xlsx", ".xls")):
        raw = pd.ExcelFile(path).parse(sheet or 0, header=None)
    else:
        raw = pd.read_csv(path, header=None)
    # a spreadsheet written for humans often has several header rows: join them into one name per column
    head = raw.iloc[:header_rows].fillna("")
    names = []
    for j in range(raw.shape[1]):
        parts = [str(head.iloc[i, j]).strip() for i in range(header_rows)]
        parts = [p for p in parts if p and not p.lower().startswith("unnamed")]
        names.append(" ".join(parts) if parts else f"col{j}")
    d = raw.iloc[header_rows:].copy()
    d.columns = names
    return d.reset_index(drop=True), names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("structures"); ap.add_argument("table"); ap.add_argument("out")
    ap.add_argument("--props", nargs="+", required=True, help="property columns to carry through (substring match)")
    ap.add_argument("--id-col", default=None); ap.add_argument("--sheet", default=None)
    ap.add_argument("--header-rows", type=int, default=1)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    d, names = read_table(a.table, a.sheet, a.header_rows)
    id_col = a.id_col or names[0]
    def resolve(want):
        exact = [c for c in names if c.strip().lower() == want.strip().lower()]
        if exact:
            return exact[0]
        hits = [c for c in names if want.strip().lower() in c.strip().lower()]
        if len(hits) != 1:
            raise SystemExit(f"property '{want}' matches {hits or 'nothing'} among {names}; name it exactly")
        return hits[0]
    prop_cols = [resolve(p) for p in a.props]
    print(f"table: {len(d)} rows; id column '{id_col}'; properties {prop_cols}", flush=True)

    # index the structure files by (phase, composition) using the composition of the STRUCTURE, which is authoritative
    import collections
    by_comp = collections.defaultdict(list)
    n_files = 0
    for fn in sorted(os.listdir(a.structures)):
        fp = os.path.join(a.structures, fn)
        if not os.path.isfile(fp) or fn.startswith("."):
            continue
        try:
            st = Structure.from_file(fp)
        except Exception:
            continue
        phase, _rest, _tag = split_name(fn)
        by_comp[st.composition.reduced_composition].append(dict(phase=phase, path=fp, file=fn, struct=st))
        n_files += 1
    print(f"structures: {n_files} files, {len(by_comp)} distinct compositions in {a.structures}", flush=True)
    used = set()

    rows, skipped = [], {"no structure file": [], "ambiguous: several structures share this composition": [],
                         "property not a number": []}
    for _i, rd in d.iterrows():          # iterrows, not itertuples: human header names contain spaces and '+'
        name = str(rd[id_col]).strip()
        if not name or name.lower() in ("nan", "materials"):
            continue
        phase, chem, _tag = split_name(name)
        comp = composition_of(chem)
        cands = by_comp.get(comp, []) if comp is not None else []
        if not cands:
            skipped["no structure file"].append(name); continue
        free = [c for c in cands if c["file"] not in used]
        pick = [c for c in free if c["phase"] == phase] if phase else free
        if not pick:
            pick = [c for c in cands if c["phase"] == phase] or cands
            if len(pick) > 1 or pick[0]["file"] in used:
                skipped["ambiguous: several structures share this composition"].append(
                    name + f" -> phases {[c['phase'] for c in cands]}")
                continue
        if len(pick) > 1:
            skipped["ambiguous: several structures share this composition"].append(
                name + f" -> phases {[c['phase'] for c in pick]}")
            continue
        chosen = pick[0]
        used.add(chosen["file"])
        s, path = chosen["struct"], chosen["path"]
        try:
            vals = {c: float(str(rd[c]).strip()) for c in prop_cols}
        except (TypeError, ValueError):
            skipped["property not a number"].append(name); continue
        rows.append(dict(material_id=name, cif=s.to(fmt="cif"), formula=s.composition.reduced_formula,
                         natoms=len(s), phase=phase, source_file=os.path.basename(path), **vals))

    out = pd.DataFrame(rows)
    # the pipeline keys on the property column NAMES, so give them simple ids and record the mapping
    simple = {c: re.sub(r"[^A-Za-z0-9]+", "_", c).strip("_") for c in prop_cols}
    out = out.rename(columns=simple)
    out.to_csv(os.path.join(a.out, "table.csv"), index=False)
    unmatched_files = sorted(c["file"] for v in by_comp.values() for c in v if c["file"] not in used)
    rep = dict(table_rows=len(d), structure_files=n_files, matched=len(out),
               skipped={k: len(v) for k, v in skipped.items()}, skipped_examples={k: v[:15] for k, v in skipped.items()},
               structure_files_unmatched=len(unmatched_files), structure_files_unmatched_examples=unmatched_files[:15],
               property_columns=simple, natoms=out.natoms.value_counts().sort_index().to_dict() if len(out) else {},
               formulas=int(out.formula.nunique()) if len(out) else 0)
    json.dump(rep, open(os.path.join(a.out, "ingest_report.json"), "w"), indent=1)
    print(f"matched {len(out)} of {len(d)} rows ({rep['formulas']} distinct formulas); skipped {rep['skipped']}; "
          f"{rep['structure_files_unmatched']} structure files unused", flush=True)
    if len(out):
        print(f"atoms per cell: {rep['natoms']}")
        print(out[["material_id", "formula", "natoms"] + list(simple.values())].head(8).to_string(index=False))


if __name__ == "__main__":
    main()
