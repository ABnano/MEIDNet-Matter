"""Nearest training materials and neighbourhood statistics in a model's latent space."""
from __future__ import annotations

import numpy as np

from matter.services.artefacts import Materials
from matter.services.support import leader_clusters


class LatentIndex:
    def __init__(self, z: np.ndarray, ids: list[str], pred: np.ndarray, columns: list[str], materials: Materials):
        norms = np.maximum(np.linalg.norm(z, axis=1, keepdims=True), 1e-12)
        self.z = (z / norms).astype(np.float32)
        self.ids = ids
        self.pred = pred
        self.columns = columns
        self.materials = materials
        pos = {mid: i for i, mid in enumerate(materials.ids)}
        self.rows = np.array([pos[i] for i in ids])         # row of each latent in the materials table
        self.Y = materials.Y[self.rows]

    def __len__(self):
        return len(self.ids)

    def cosines(self, zq: np.ndarray) -> np.ndarray:
        q = np.asarray(zq, dtype=np.float32).reshape(-1)
        q = q / max(float(np.linalg.norm(q)), 1e-12)
        return self.z @ q

    def nearest(self, zq: np.ndarray, k: int = 3) -> list[dict]:
        cos = self.cosines(zq)
        k = min(k, len(cos))
        idx = np.argpartition(-cos, k - 1)[:k]
        idx = idx[np.argsort(-cos[idx])]
        out = []
        for i in idx:
            row = self.materials.row(int(self.rows[i]))
            out.append({**row, "cosine": float(cos[i]),
                        "encoder_prediction": {c: float(self.pred[i, j]) for j, c in enumerate(self.columns)}})
        return out

    def knn_mean(self, zq: np.ndarray, k: int = 5) -> dict[str, float]:
        cos = self.cosines(zq)
        idx = np.argpartition(-cos, min(k, len(cos)) - 1)[:k]
        return {c: float(self.Y[idx, j].mean()) for j, c in enumerate(self.materials.columns)}

    def clusters(self, mask: np.ndarray, cosine: float = 0.9) -> int:
        """Distinct latent clusters among the training materials selected by `mask` (over the materials table)."""
        sel = mask[self.rows]
        if not sel.any():
            return 0
        return leader_clusters(self.z[sel], cosine)

    def tied_to(self, zq: np.ndarray, within: float = 0.02) -> int:
        """How many training structures are within `within` of the best cosine to a query latent."""
        cos = self.cosines(zq)
        return int((cos >= cos.max() - within).sum())
