"""Is a composition in the dataset? Checked by reduced formula and by A|B|X site assignment, because Perov-5 holds
both site orderings of many compositions (BaTiO3 with Ba on A, and with Ti on A) with different properties."""
from __future__ import annotations

from collections import defaultdict

from matter.services.artefacts import Materials


class DatasetIndex:
    def __init__(self, materials: Materials, dataset_name: str = "Perov-5"):
        self.m = materials
        self.name = dataset_name
        self.by_formula: dict[str, list[int]] = defaultdict(list)
        self.by_site: dict[str, list[int]] = defaultdict(list)
        for i, (f, k) in enumerate(zip(materials.reduced, materials.site_keys)):
            self.by_formula[f].append(i)
            if k:
                self.by_site[k].append(i)
        self.n_all = len(materials)
        self.n_train = int(materials.train_mask.sum())

    def _match(self, reduced: str, site_key: str | None, train_only: bool) -> dict | None:
        rows = []
        by = None
        if site_key and site_key in self.by_site:
            rows, by = self.by_site[site_key], "A|B|X site assignment"
        elif reduced in self.by_formula:
            rows, by = self.by_formula[reduced], "reduced formula"
        if train_only:
            rows = [i for i in rows if self.m.splits[i] == "train"]
        if not rows:
            return None
        i = rows[0]
        return {**self.m.row(i), "matched_by": by, "n_matches": len(rows)}

    def lookup(self, reduced: str, site_key: str | None) -> dict:
        dataset = self._match(reduced, site_key, train_only=False)
        training = self._match(reduced, site_key, train_only=True)
        scope_all = f"{self.name} dataset ({self.n_all:,} materials)"
        scope_train = f"training split ({self.n_train:,} materials)"
        return {
            "method": "reduced formula and A|B|X site assignment",
            "dataset": {"checked_against": scope_all, "found": dataset is not None, "match": dataset,
                        "label": (f"Found in the {scope_all}: {dataset['formula']} ({dataset['material_id']}, {dataset['split']} split)"
                                  if dataset else f"Not found in the {scope_all}")},
            "training_split": {"checked_against": scope_train, "found": training is not None, "match": training,
                               "label": (f"Found in the {scope_train}: {training['formula']} ({training['material_id']})"
                                         if training else f"Not found in the {scope_train}")},
        }
