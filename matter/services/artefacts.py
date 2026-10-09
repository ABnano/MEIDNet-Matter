"""The demo project's artefacts (examples/perov5), loaded once: project, models, dataset statistics, held-out
evaluations, the materials table and the training latents."""
from __future__ import annotations

import csv
import gzip
import json
import os
import threading
from dataclasses import dataclass

import numpy as np

from matter.api.errors import ApiError


@dataclass
class Materials:
    """Every material of the dataset: ids, split, formulas, A|B|X site key and the property values."""
    ids: list[str]
    splits: np.ndarray
    formulas: list[str]
    reduced: list[str]
    site_keys: list[str]
    columns: list[str]
    Y: np.ndarray                   # (n, k) physical units

    def __len__(self):
        return len(self.ids)

    @property
    def train_mask(self) -> np.ndarray:
        return self.splits == "train"

    def row(self, i: int) -> dict:
        return {"material_id": self.ids[i], "split": str(self.splits[i]), "formula": self.formulas[i],
                "reduced_formula": self.reduced[i], "site_key": self.site_keys[i] or None,
                "properties": {c: float(self.Y[i, j]) for j, c in enumerate(self.columns)}}


class DemoArtefacts:
    def __init__(self, demo_dir: str):
        self.dir = demo_dir
        if not os.path.exists(os.path.join(demo_dir, "project.json")):
            raise ApiError("not_found", f"demo artefacts not found in {demo_dir}: build them with scripts/build_demo.py", status=503)
        self.project = self._json("project.json")
        self.models = {m["model_id"]: m for m in self._json("models.json")}
        self.dataset = self._json("dataset.json")
        self.readiness = {mid: self._json(os.path.join("readiness", f"{mid}.json")) for mid in self.models}
        self.materials = self._materials()
        self._latents: dict[str, object] = {}
        self._lock = threading.Lock()

    def cell(self, material_id: str) -> dict | None:
        """The cell of a material as sites and a lattice, from the compact store the demo build writes (Perov-5: cubic,
        five sites), or None when the demo ships no cells."""
        with self._lock:
            if not hasattr(self, "_cells"):
                p = os.path.join(self.dir, "explore_cells.npz")
                self._cells = None
                if os.path.isfile(p):
                    z = np.load(p)
                    self._cells = {"index": {str(i): n for n, i in enumerate(z["material_id"])}, "a": z["a"], "species": z["species"], "frac": z["frac"]}
        c = self._cells
        if c is None or material_id not in c["index"]:
            return None
        n = c["index"][material_id]
        a = float(c["a"][n])
        return {"lattice": [[a, 0.0, 0.0], [0.0, a, 0.0], [0.0, 0.0, a]],
                "sites": [{"element": str(e), "frac": [round(float(x), 4) for x in f]} for e, f in zip(c["species"][n], c["frac"][n])]}

    def _json(self, name: str):
        with open(os.path.join(self.dir, name), encoding="utf-8") as f:
            return json.load(f)

    def _materials(self) -> Materials:
        columns = self.dataset["columns"][3:]
        ids, splits, formulas, reduced, keys, Y = [], [], [], [], [], []
        with gzip.open(os.path.join(self.dir, "materials.csv.gz"), "rt", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            pos = {c: header.index(c) for c in columns}
            for row in reader:
                ids.append(row[0]); splits.append(row[1]); formulas.append(row[2]); reduced.append(row[3]); keys.append(row[4])
                Y.append([float(row[pos[c]]) for c in columns])
        return Materials(ids, np.array(splits), formulas, reduced, keys, columns, np.array(Y, dtype=float))

    @property
    def columns(self) -> list[str]:
        return self.materials.columns

    def property(self, column: str) -> dict:
        """The training-split statistics block of a property (the basis of every domain test)."""
        try:
            return self.dataset["properties"][column]
        except KeyError:
            raise ApiError("engine_error", f"'{column}' is not a property of this project ({', '.join(self.columns)})") from None

    def labels(self) -> dict[str, tuple[str, str]]:
        return {c: (self.dataset["properties"][c]["label"], self.dataset["properties"][c]["unit"]) for c in self.columns}

    def latents(self, model_id: str):
        """The training latents of a model as a LatentIndex, or None when the model ships none."""
        from matter.services.latents import LatentIndex
        with self._lock:
            if model_id in self._latents:
                return self._latents[model_id]
            entry = self.models.get(model_id) or {}
            path = os.path.join(self.dir, entry.get("latents_file") or "")
            index = None
            if entry.get("latents_file") and os.path.exists(path):
                z = np.load(path)
                index = LatentIndex(z["z"].astype(np.float32), [str(i) for i in z["material_id"]], z["pred"].astype(float),
                                    [str(c) for c in z["columns"]], self.materials)
            self._latents[model_id] = index
            return index

    def dataset_summary(self, with_grid: bool = False) -> dict:
        d = self.dataset
        out = {k: d[k] for k in ("dataset_id", "title", "source", "rows", "columns", "properties", "properties_basis", "elements",
                                 "family_coverage", "family_like_rows", "profiles", "fingerprint", "skipped")}
        if with_grid:
            out["ambiguity_grid"] = d["ambiguity_grid"]
            out["properties_all"] = d["properties_all"]
            out["elements_by_split"] = d["elements_by_split"]
        return out
