"""Pure numpy helpers behind the readiness report and the candidate evidence.

The training distribution of a property is described by the statistics block that the artefact builder writes
(min, max, percentiles, std, zero share, and the same block for the non-zero values). For a property whose values
are mostly exactly zero (a band gap: 96 % of Perov-5 gaps are 0), the non-zero block is the basis of every
percentile test, because the zero spike says nothing about where a non-zero target sits.
"""
from __future__ import annotations

import numpy as np

DOMAIN_STATUSES = ("in_distribution", "near_boundary", "extrapolating", "far_outside")
DOMAIN_WORDS = {"in_distribution": "Interpolating", "near_boundary": "Boundary", "extrapolating": "Extrapolating",
                "far_outside": "Extrapolating"}
EXTRAPOLATION_SENTENCE = "Extrapolating beyond observed property support"
ENGINE_MARGIN = 0.05            # the engine flags a prediction beyond 5 % of the span outside the training range


def effective_stats(p: dict) -> tuple[str, dict]:
    """("nonzero", block) when more than half of the values are exactly zero and non-zero values exist, else ("all", p)."""
    if p.get("zero_share", 0.0) > 0.5 and p.get("nonzero"):
        return "nonzero", p["nonzero"]
    return "all", p


def fmt(v: float, unit: str = "") -> str:
    s = f"{v:.3g}" if abs(v) < 1000 else f"{v:,.0f}"
    return f"{s} {unit}".strip()


def basis_phrase(p: dict, basis: str) -> str:
    label = p.get("label", "the property")
    n = (p["nonzero"]["n"] if basis == "nonzero" else p["n"])
    return f"the {n:,} training materials" + (f" with a non-zero {label.lower()}" if basis == "nonzero" else "")


def domain_status(value: float, p: dict) -> tuple[str, str]:
    """Where a value sits in the training distribution of a property, with the sentence that says why."""
    basis, s = effective_stats(p)
    pc, unit = s["percentiles"], p.get("unit", "")
    lo, hi = float(p["min"]), float(p["max"])
    span = hi - lo
    v = float(value)
    if pc["p5"] <= v <= pc["p95"]:
        return "in_distribution", (f"{fmt(v, unit)} lies between the 5th and 95th percentiles ({fmt(pc['p5'])}–{fmt(pc['p95'], unit)}) "
                                   f"of {basis_phrase(p, basis)}.")
    if pc["p1"] <= v <= pc["p99"]:
        return "near_boundary", (f"{fmt(v, unit)} lies near the edge of the training distribution: outside the 5th–95th percentile band "
                                 f"({fmt(pc['p5'])}–{fmt(pc['p95'], unit)}) but inside the 1st–99th ({fmt(pc['p1'])}–{fmt(pc['p99'], unit)}) "
                                 f"of {basis_phrase(p, basis)}.")
    side = "low" if v < pc["p1"] else "high"
    if lo <= v <= hi:
        return "extrapolating", (f"{EXTRAPOLATION_SENTENCE}: {fmt(v, unit)} lies inside the training range ({fmt(lo)}–{fmt(hi, unit)}) but "
                                 f"outside the 1st–99th percentile band ({fmt(pc['p1'])}–{fmt(pc['p99'], unit)}) of {basis_phrase(p, basis)}: "
                                 f"fewer than 1 % of them have a value this {side} (percentile test on the training distribution).")
    if lo - ENGINE_MARGIN * span <= v <= hi + ENGINE_MARGIN * span:
        return "extrapolating", (f"{EXTRAPOLATION_SENTENCE}: {fmt(v, unit)} is outside the training range ({fmt(lo)}–{fmt(hi, unit)}) by less than "
                                 f"5 % of its span (range test).")
    return "far_outside", (f"{EXTRAPOLATION_SENTENCE}: {fmt(v, unit)} is outside the training range ({fmt(lo)}–{fmt(hi, unit)}) by more than "
                           f"5 % of its span (range test).")


def worse(a: str, b: str) -> str:
    return a if DOMAIN_STATUSES.index(a) >= DOMAIN_STATUSES.index(b) else b


def tolerance(p: dict, user_tol: float | None = None) -> float:
    """Half-width of the box around a target value: 5 % of the property's span, or the user's tolerance if wider."""
    return max(ENGINE_MARGIN * (float(p["max"]) - float(p["min"])), float(user_tol or 0.0))


def box_mask(Y: np.ndarray, columns: list[str], windows: dict[str, tuple[float | None, float | None]]) -> np.ndarray:
    """Rows of Y (one column per property) inside every window; a missing bound is open."""
    mask = np.ones(len(Y), dtype=bool)
    for j, c in enumerate(columns):
        if c not in windows:
            continue
        lo, hi = windows[c]
        if lo is not None:
            mask &= Y[:, j] >= lo
        if hi is not None:
            mask &= Y[:, j] <= hi
    return mask


def share_below(values: np.ndarray, v: float) -> float:
    return float((values <= v).mean()) if len(values) else 0.0


def leader_clusters(Z: np.ndarray, cosine: float = 0.9) -> int:
    """Greedy leader clustering of unit vectors: a point joins the first leader it is at least `cosine` close to."""
    leaders = []
    for z in Z:
        if not leaders or (np.asarray(leaders) @ z).max() < cosine:
            leaders.append(z)
    return len(leaders)


def quality(mae: float, std: float) -> tuple[str, float | None]:
    """The engine's wording for an error against a spread (meidnet.report.quality_word)."""
    from meidnet.report import quality_word
    return quality_word(mae, std)
