"""
Turning a user's table + structures into something MEIDNet can learn from.

The steps are deliberately small and individually testable:

1. ``read_table``          – CSV / Excel / JSON / Parquet → DataFrame
2. ``parse_structure``     – CIF text or file → pymatgen Structure
3. ``align_to_prototype``  – re-order atoms so site i matches prototype site i
4. ``featurize``           – Structure → fixed-length vector (the crystal modality)
5. ``load_dataset``        – all of the above for every row, with a report of
                              what was kept, skipped and why.
"""
from __future__ import annotations

import os
import warnings
from collections import Counter
from dataclasses import dataclass, field
from itertools import product

import numpy as np
import pandas as pd
import torch
from pymatgen.core import Structure
from pymatgen.io.cif import CifParser
from torch.utils.data import Dataset

from meidnet.chem import ELEMENT_INDEX, NUM_SPECIES

warnings.filterwarnings("ignore", message="Issues encountered while parsing CIF")
warnings.filterwarnings("ignore", message="No\\sPauling\\selectronegativity")


# ───────────────────────── 1) tables ─────────────────────────
# Readers pandas needs an extra package for, and what to tell the user when it is missing.
_READER_HINTS = {
    ".xlsx": "Reading .xlsx files needs the 'openpyxl' package: pip install openpyxl",
    ".xls": "Reading old .xls files needs the 'xlrd' package: pip install xlrd (or save the sheet as .xlsx or CSV)",
    ".parquet": "Reading Parquet files needs the 'pyarrow' package: pip install pyarrow (or save the table as CSV)",
}


def read_table(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".xlsx", ".xls"):
            return pd.read_excel(path)
        if ext == ".json":
            return pd.read_json(path)
        if ext == ".parquet":
            return pd.read_parquet(path)
    except ImportError as e:
        raise ImportError(_READER_HINTS.get(ext, str(e))) from e
    return pd.read_csv(path)


def normalise_id(value) -> str:
    """IDs are compared as strings; 12.0 and '12' both become '12' (as in MEIDNet v1)."""
    try:
        f = float(value)
        if f.is_integer():
            return str(int(f))
    except (TypeError, ValueError):
        pass
    return str(value).strip()


# ───────────────────────── 2) structures ─────────────────────────
def parse_structure(cif_text: str | None = None, path: str | None = None) -> Structure:
    parser = CifParser(path) if path is not None else CifParser.from_str(cif_text)
    structs = parser.parse_structures(primitive=False)
    if not structs:
        raise ValueError("the CIF contains no structure")
    s = structs[0]
    while isinstance(s, list) and s:
        s = s[0]
    if not isinstance(s, Structure):
        raise ValueError("could not read a single structure from the CIF")
    return s


def _formula_ab(formula):
    """A and B element of a Perov-5 style formula string ("TlCoN2O" -> ("Tl", "Co")): A is written first, B second."""
    import re
    els = re.findall(r"[A-Z][a-z]?", str(formula or ""))
    return (els[0], els[1]) if len(els) >= 2 and els[0] != els[1] else None


def order_perovskite_sites(s: Structure, formula=None) -> Structure:
    """A site, B site, then the three anions, for a 5-atom ABX3 cell (other cells are returned unchanged).
    A has the largest mean distance to its 6 nearest neighbours (12 anions at a/sqrt2); among the rest, B has the smallest
    (6 anions at a/2); the remaining three sites are the anions.  Robust to the off-grid displacements in Perov-5."""
    if len(s) != 5:
        return s
    ab = _formula_ab(formula)
    if ab:                       # the dataset's own A/B assignment, when the formula string gives it
        syms = [site.specie.symbol for site in s]
        if syms.count(ab[0]) == 1 and syms.count(ab[1]) == 1:
            ia, ib = syms.index(ab[0]), syms.index(ab[1])
            return Structure.from_sites([s[ia], s[ib]] + [s[i] for i in range(5) if i not in (ia, ib)])
    nn = []
    for i in range(5):
        dists = sorted([nb[1] for nb in s.get_neighbors(s[i], 6.0)])[:6]
        nn.append(float(np.mean(dists)) if dists else np.inf)
    a_idx = int(np.argmax(nn))
    rest = [i for i in range(5) if i != a_idx]
    b_idx = min(rest, key=lambda i: nn[i])
    order = [a_idx, b_idx] + [i for i in rest if i != b_idx]
    return Structure.from_sites([s[i] for i in order])


ANION_ELEMENTS = ("F", "O", "Cl", "N", "Br", "I", "S", "Se", "Te")      # elements that can be anions


def anion_elements(s: Structure) -> set:
    """The anions of a structure.  First choice: charge balance (pymatgen's oxidation-state guess on the composition: the
    elements with a negative state, e.g. S2- in ZnCdO2S, not Te4+ in TeHfO3).  Fallback when no charge-balanced assignment
    exists (chemically implausible compositions): the most electronegative anion-type element always, another anion-type
    element only if its nearest neighbours are not that anion."""
    from pymatgen.core import Element
    present = sorted({site.specie.symbol for site in s} & set(ANION_ELEMENTS), key=lambda e: -Element(e).X)
    if not present:
        return set()
    try:
        guesses = s.composition.oxi_state_guesses(max_sites=-1)
    except Exception:
        guesses = ()
    if guesses:
        return {el for el, ox in guesses[0].items() if ox < 0}
    top, out = present[0], {present[0]}
    for el in present[1:]:                      # sits in a polyhedron of the top anion (>= 4 within 1.4 x nearest) -> cation
        coord = []
        for site in s:
            if site.specie.symbol == el:
                nb = s.get_neighbors(site, 6.0)
                dmin = min(n[1] for n in nb)
                coord.append(sum(1 for n in nb if n.specie.symbol == top and n[1] <= 1.4 * dmin))
        if np.mean(coord) < 4:
            out.add(el)
    return out


def order_sites_by_role(s: Structure) -> Structure:
    """Any cell size, geometry only: cation elements by site size (mean distance to the 6 nearest neighbours, largest first, so
    a perovskite's A precedes B), then the anions (most electronegative first); within an element, sites sorted by fractional
    coordinates.  A 5-atom ABX3 cell comes out as A, B, X, X, X like 'perovskite', without needing the formula string."""
    from pymatgen.core import Element
    size = {}
    for i, site in enumerate(s):
        d = sorted(nb[1] for nb in s.get_neighbors(site, 6.0))[:6]
        size.setdefault(site.specie.symbol, []).append(float(np.mean(d)) if d else np.inf)
    anions = anion_elements(s)
    def rank(el):
        if el in anions:
            return (1, -Element(el).X, 0.0)
        return (0, 0, -float(np.mean(size[el])))
    def key(i):
        return (rank(s[i].specie.symbol), s[i].specie.symbol, tuple(np.round(s[i].frac_coords % 1.0, 3)))
    return Structure.from_sites([s[i] for i in sorted(range(len(s)), key=key)])


# ───────────────────────── 3) prototype alignment ─────────────────────────
class AlignmentError(ValueError):
    pass


def _periodic_delta(a: np.ndarray) -> np.ndarray:
    return a - np.round(a)


def align_to_prototype(struct: Structure, family, tol: float = 0.12) -> tuple[Structure, dict]:
    """
    Re-order (and shift) the atoms of ``struct`` so that atom i sits on prototype
    site i.  Uses fractional coordinates in the structure's own cell: every origin
    shift that puts some atom on some prototype site is tried, atoms are matched to
    sites by the Hungarian algorithm, and the best match is kept.  Fails (with a
    reason) if the cell has a different number of atoms or any atom is farther than
    ``tol`` (fractional units) from its site.
    """
    from scipy.optimize import linear_sum_assignment

    proto = family.frac_coords
    n = len(struct)
    if n != len(proto):
        raise AlignmentError(f"has {n} atoms but the {family.name} prototype has {len(proto)}")
    frac = np.array(struct.frac_coords, dtype=np.float64)
    groups = [g for g, _ in family.sites]
    allowed = {g: set(family.groups[g].universe) for g in family.groups}
    species = [site.specie.symbol for site in struct]

    best = None
    for i, k in product(range(n), range(n)):
        shift = frac[i] - proto[k]
        d = _periodic_delta((frac - shift)[:, None, :] - proto[None, :, :])  # (atom, site, 3)
        cost = np.sqrt((d ** 2).sum(-1))
        rows, cols = linear_sum_assignment(cost)
        geo = cost[rows, cols]
        # tie-breaker: prefer assignments that put elements in groups that list them
        chem = sum(0 if (not allowed[groups[c]] or species[r] in allowed[groups[c]]) else 1 for r, c in zip(rows, cols))
        key = (round(float(geo.max()), 3), chem, float(geo.sum()))
        if best is None or key < best[0]:
            best = (key, shift, rows.copy(), cols.copy(), d)
    (gmax, chem, _), shift, rows, cols, d = best
    if gmax > tol:
        raise AlignmentError(f"atoms are up to {gmax:.2f} (fractional) away from the prototype sites")
    order = np.empty(n, dtype=int)
    order[cols] = rows                       # order[site] = atom index
    new_frac = np.array([proto[s] + d[order[s], s] for s in range(n)])
    aligned = Structure(struct.lattice, [species[order[s]] for s in range(n)], new_frac)
    return aligned, {"max_offset": gmax, "elements_out_of_group": chem}


# ───────────────────────── 4) featurisation ─────────────────────────
def dense_length(max_sites: int) -> int:
    return 6 + max_sites * max_sites + max_sites * NUM_SPECIES + max_sites * 3


def scale_lattice(a, b, c, alpha, beta, gamma) -> np.ndarray:
    return np.array([a / 20.0, b / 20.0, c / 20.0, alpha / 180.0, beta / 180.0, gamma / 180.0], dtype=np.float32)


def fit_to_max_sites(struct: Structure, max_sites: int) -> Structure:
    """The structure itself when it has at most ``max_sites`` atoms, else its primitive cell when that fits.

    A conventional cell is often a multiple of what the model needs: the 40-atom conventional cell of a rock-salt ordered
    double perovskite is four 10-atom primitive cells, the same crystal.  Reducing it changes nothing physical, so a
    user's file and a generated cell are read instead of refused.  A crystal whose primitive cell is still too large is
    returned unchanged, and the caller reports it.
    """
    if len(struct) <= max_sites:
        return struct
    try:
        prim = struct.get_primitive_structure()
    except Exception:
        return struct
    return prim if len(prim) <= max_sites else struct


def featurize(struct: Structure, max_sites: int = 20, cutoff: float = 4.0) -> np.ndarray:
    """
    Fixed-length vector for one structure:
    [scaled lattice (6) | adjacency (N×N) | one-hot species (N×118) | fractional coords (N×3)],
    padded with zeros up to ``max_sites`` atoms.  Identical to MEIDNet v1.
    """
    n = len(struct)
    if n > max_sites:
        raise ValueError(f"has {n} atoms, more than max_sites={max_sites}")
    a, b, c = struct.lattice.abc
    alpha, beta, gamma = struct.lattice.angles
    lat = scale_lattice(a, b, c, alpha, beta, gamma)

    adj = np.zeros((max_sites, max_sites), dtype=np.float32)
    i0, i1, _, _ = struct.get_neighbor_list(r=cutoff)
    for i, j in zip(i0, i1):
        if i < max_sites and j < max_sites and i != j:
            adj[i, j] = 1.0

    spc = np.zeros((max_sites, NUM_SPECIES), dtype=np.float32)
    crd = np.zeros((max_sites, 3), dtype=np.float32)
    for i, site in enumerate(struct):
        sym = site.specie.symbol
        if sym not in ELEMENT_INDEX:
            raise ValueError(f"contains '{sym}', which is not a plain element")
        spc[i, ELEMENT_INDEX[sym]] = 1.0
        crd[i] = site.frac_coords
    return np.concatenate([lat.flatten(), adj.flatten(), spc.flatten(), crd.flatten()], axis=0)


def split_dense(x: torch.Tensor, max_sites: int) -> dict[str, torch.Tensor]:
    B = x.size(0)
    o = 0
    lat = x[:, o:o + 6]; o += 6
    adj = x[:, o:o + max_sites * max_sites].view(B, max_sites, max_sites); o += max_sites * max_sites
    spc = x[:, o:o + max_sites * NUM_SPECIES].view(B, max_sites, NUM_SPECIES); o += max_sites * NUM_SPECIES
    crd = x[:, o:o + max_sites * 3].view(B, max_sites, 3)
    return {"lat": lat, "adj": adj, "species": spc, "coords": crd}


# ───────────────────────── 5) datasets ─────────────────────────
@dataclass
class PropertyStats:
    columns: list[str]
    mean: np.ndarray
    std: np.ndarray
    labels: list[str] = field(default_factory=list)
    units: list[str] = field(default_factory=list)
    minimum: np.ndarray | None = None
    maximum: np.ndarray | None = None

    def normalize(self, values: np.ndarray) -> np.ndarray:
        return (values - self.mean) / self.std

    def denormalize_tensor(self, t: torch.Tensor) -> torch.Tensor:
        mean = torch.as_tensor(self.mean, dtype=t.dtype, device=t.device)
        std = torch.as_tensor(self.std, dtype=t.dtype, device=t.device)
        return t * std + mean

    def index(self, column: str) -> int:
        try:
            return self.columns.index(column)
        except ValueError:
            raise KeyError(f"'{column}' is not one of the model's properties {self.columns}") from None

    def to_dict(self) -> list[dict]:
        out = []
        for i, c in enumerate(self.columns):
            out.append({
                "column": c, "label": self.labels[i] if self.labels else c,
                "unit": self.units[i] if self.units else "",
                "mean": float(self.mean[i]), "std": float(self.std[i]),
                "min": None if self.minimum is None else float(self.minimum[i]),
                "max": None if self.maximum is None else float(self.maximum[i]),
            })
        return out

    @classmethod
    def from_dict(cls, items: list[dict]) -> "PropertyStats":
        return cls(
            columns=[d["column"] for d in items],
            mean=np.array([d["mean"] for d in items], dtype=np.float64),
            std=np.array([d["std"] for d in items], dtype=np.float64),
            labels=[d.get("label", d["column"]) for d in items],
            units=[d.get("unit", "") for d in items],
            minimum=None if items[0].get("min") is None else np.array([d["min"] for d in items]),
            maximum=None if items[0].get("max") is None else np.array([d["max"] for d in items]),
        )


@dataclass
class Record:
    material_id: str
    dense: np.ndarray
    properties: np.ndarray        # raw (physical units)
    formula: str
    structure: object = None      # pymatgen Structure, kept only with keep_structures=True


@dataclass
class DataReport:
    """What happened to every row - shown by `meidnet check` and in reports."""
    source: str
    rows: int = 0
    kept: int = 0
    skipped: Counter = field(default_factory=Counter)
    examples: dict = field(default_factory=dict)
    site_counts: Counter = field(default_factory=Counter)
    elements: Counter = field(default_factory=Counter)
    aligned: int = 0
    reduced_to_primitive: int = 0        # cells larger than max_sites that were read as their primitive cell

    def skip(self, reason: str, material_id: str):
        self.skipped[reason] += 1
        self.examples.setdefault(reason, [])
        if len(self.examples[reason]) < 3:
            self.examples[reason].append(material_id)


class MaterialsDataset(Dataset):
    """Torch dataset of (crystal vector, normalised property vector) pairs."""

    def __init__(self, records: list[Record], stats: PropertyStats):
        self.records = records
        self.stats = stats
        self._props = [stats.normalize(r.properties.astype(np.float64)).astype(np.float32) for r in records]

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        r = self.records[idx]
        return {
            "crystal_vec": torch.from_numpy(r.dense).float(),
            "props": torch.from_numpy(self._props[idx]),
            "material_id": r.material_id,
        }


def compute_stats(records: list[Record], columns, normalize_flags, labels=None, units=None) -> PropertyStats:
    vals = np.stack([r.properties for r in records]).astype(np.float64)
    mean = np.where(normalize_flags, vals.mean(0), 0.0)
    std = np.where(normalize_flags, vals.std(0), 1.0)
    std = np.where(std < 1e-12, 1.0, std)
    return PropertyStats(list(columns), mean, std, list(labels or columns), list(units or [""] * len(columns)),
                         vals.min(0), vals.max(0))


def load_records(df: pd.DataFrame, data_cfg, base_resolve, family=None, source: str = "table",
                 report: DataReport | None = None, keep_structures: bool = False) -> tuple[list[Record], DataReport]:
    report = report or DataReport(source=source)
    cols = [p.column for p in data_cfg.properties]
    missing_cols = [c for c in [data_cfg.id_column, *cols] if c not in df.columns]
    if data_cfg.cif_column and data_cfg.cif_column not in df.columns and not data_cfg.structures_dir:
        missing_cols.append(data_cfg.cif_column)
    if missing_cols:
        raise ValueError(
            f"{source}: column(s) {missing_cols} not found. Available columns: {list(df.columns)}"
        )
    use_col = bool(data_cfg.cif_column) and data_cfg.cif_column in df.columns
    sdir = base_resolve(data_cfg.structures_dir) if data_cfg.structures_dir else None
    align = bool(family) and data_cfg.align_to_prototype
    records = []
    for _, row in df.iterrows():
        report.rows += 1
        mid = normalise_id(row[data_cfg.id_column])
        try:
            props = np.array([float(row[c]) for c in cols], dtype=np.float64)
        except (TypeError, ValueError):
            report.skip("non-numeric property value", mid)
            continue
        if not np.all(np.isfinite(props)):
            report.skip("missing property value", mid)
            continue
        try:
            if use_col and isinstance(row[data_cfg.cif_column], str):
                s = parse_structure(cif_text=row[data_cfg.cif_column])
            elif sdir:
                if not mid or any(ch in mid for ch in "/\\:") or mid.startswith("."):
                    report.skip("id is not a valid file name", mid)   # the file must be inside structures_dir
                    continue
                path = os.path.join(sdir, f"{mid}.cif")
                if not os.path.exists(path):
                    report.skip("no CIF file for this id", mid)
                    continue
                s = parse_structure(path=path)
            else:
                report.skip("no structure given", mid)
                continue
        except Exception:
            report.skip("CIF could not be read", mid)
            continue
        report.site_counts[len(s)] += 1
        if len(s) > data_cfg.max_sites:
            s = fit_to_max_sites(s, data_cfg.max_sites)        # a conventional cell is read as its primitive cell
            if len(s) > data_cfg.max_sites:
                report.skip(f"more than max_sites={data_cfg.max_sites} atoms (also as its primitive cell)", mid)
                continue
            report.reduced_to_primitive += 1
        if not s.is_ordered:        # doped / solid-solution CIFs: one element per site is needed
            report.skip("partially occupied site (doped or solid solution): one element per site is needed", mid)
            continue
        try:
            if getattr(data_cfg, "site_order", "file") == "perovskite":
                s = order_perovskite_sites(s, row["formula"] if "formula" in df.columns else None)
            elif getattr(data_cfg, "site_order", "file") == "roles":
                s = order_sites_by_role(s)
            if align:
                try:
                    s, _ = align_to_prototype(s, family, tol=data_cfg.prototype_tolerance)
                    report.aligned += 1
                except AlignmentError:
                    report.skip(f"does not match the {family.name} prototype", mid)
                    continue
            dense = featurize(s, data_cfg.max_sites, data_cfg.neighbor_cutoff)
        except ValueError:
            report.skip("unsupported species", mid)
            continue
        except Exception as e:      # one odd structure must not stop the whole table
            report.skip(f"structure could not be processed ({type(e).__name__})", mid)
            continue
        for el in s.composition.elements:
            report.elements[str(el)] += 1
        records.append(Record(mid, dense, props, s.composition.reduced_formula, s if keep_structures else None))
        report.kept += 1
    return records, report


def split_records(records: list[Record], val_fraction: float, seed: int) -> tuple[list[Record], list[Record]]:
    if val_fraction <= 0 or len(records) < 10:
        return records, []
    rng = np.random.RandomState(seed)
    idx = rng.permutation(len(records))
    n_val = max(1, int(round(val_fraction * len(records))))
    val = set(idx[:n_val].tolist())
    return [r for i, r in enumerate(records) if i not in val], [r for i, r in enumerate(records) if i in val]
