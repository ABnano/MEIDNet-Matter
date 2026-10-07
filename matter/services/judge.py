"""The independent band-gap judge: MEGNet multi-fidelity, a model that played no part in generation.

Its error on the dataset's own test split was measured before it was believed (and which fidelity head matches the
dataset was decided by that measurement); the numbers ship with the research artefacts and are quoted with every
verdict.  Predictions are made one job at a time behind a lock.  If the judge cannot load, generation still runs and
the result says the independent judgement is missing, rather than failing.
"""
from __future__ import annotations

import json
import os
import threading

WEIGHTS = "MEGNet-BandGap-mfi-MP-2019.4.1"


class MegnetJudge:
    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.Lock()
        self.model = None
        self.error: str | None = None
        self.qualification: dict | None = None
        q = os.path.join(settings.research_dir, "support", "mp20", "judge_qualification.json")
        if os.path.isfile(q):
            with open(q, encoding="utf-8") as f:
                self.qualification = json.load(f)

    @property
    def fidelity(self) -> int:
        return int((self.qualification or {}).get("fidelity", 0))

    @property
    def available(self) -> bool:
        return self.model is not None

    def ready(self) -> bool:
        """Load the weights once (from the local cache when the host is offline)."""
        if self.model is not None:
            return True
        if self.error is not None:
            return False
        with self.lock:
            if self.model is not None:
                return True
            try:
                import matgl
                self.model = matgl.load_model(WEIGHTS)
                return True
            except Exception as e:                       # matgl missing or weights not cached: generation still works
                self.error = f"{type(e).__name__}: {str(e)[:120]}"
                return False

    def gaps(self, structures) -> list:
        """Band gaps (eV) for a list of structures; None where the judge is unavailable or fails on a cell."""
        if not self.ready():
            return [None] * len(structures)
        import torch
        out = []
        with self.lock:
            for s in structures:
                try:
                    out.append(max(0.0, float(self.model.predict_structure(s, state_attr=torch.tensor([self.fidelity])))))
                except Exception:
                    out.append(None)
        return out

    def describe(self) -> dict:
        q = self.qualification or {}
        return {"name": "MEGNet multi-fidelity band gap", "weights": WEIGHTS, "fidelity": self.fidelity, "available": self.available,
                "error": self.error,
                "qualification": {"split": q.get("split", "MP-20 test split"), "n": q.get("n"), "mae_eV": q.get("mae"),
                                  "spearman": q.get("spearman"), "mae_on_nonzero_eV": q.get("mae_on_nonzero"),
                                  "share_zero_truth": q.get("share_zero_truth")} if q else None}
