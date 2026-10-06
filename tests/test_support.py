"""The numpy helpers behind the readiness report, on synthetic distributions."""
import numpy as np
import pytest

from matter.services.support import (EXTRAPOLATION_SENTENCE, box_mask, domain_status, effective_stats, leader_clusters, tolerance, worse)


def _stats(values, label="Band gap", unit="eV"):
    v = np.asarray(values, dtype=float)
    pct = lambda a: {f"p{p}": float(np.percentile(a, p)) for p in (1, 5, 10, 25, 50, 75, 90, 95, 99)}  # noqa: E731
    out = {"label": label, "unit": unit, "n": len(v), "std": float(v.std()), "min": float(v.min()), "max": float(v.max()),
           "span": float(v.max() - v.min()), "percentiles": pct(v), "zero_share": float((v == 0).mean())}
    nz = v[v != 0]
    if 0 < len(nz) < len(v):
        out["nonzero"] = {"n": len(nz), "std": float(nz.std()), "min": float(nz.min()), "max": float(nz.max()), "percentiles": pct(nz)}
    return out


def test_domain_status_bands_and_sentences():
    p = _stats(np.linspace(0, 10, 1001))                   # p1 = 0.1, p5 = 0.5, p95 = 9.5, p99 = 9.9, margin 0.5
    assert domain_status(5.0, p)[0] == "in_distribution"
    assert domain_status(0.5, p)[0] == "in_distribution" and domain_status(9.5, p)[0] == "in_distribution"
    assert domain_status(0.3, p)[0] == "near_boundary" and domain_status(9.7, p)[0] == "near_boundary"
    assert domain_status(-0.4, p)[0] == "extrapolating" and domain_status(10.4, p)[0] == "extrapolating"
    assert domain_status(-0.6, p)[0] == "far_outside" and domain_status(12.0, p)[0] == "far_outside"
    for v in (-0.4, 12.0):
        assert EXTRAPOLATION_SENTENCE in domain_status(v, p)[1]
    assert "between the 5th and 95th percentiles" in domain_status(5.0, p)[1]


def test_zero_inflated_properties_use_the_nonzero_values():
    values = np.concatenate([np.zeros(960), np.linspace(1, 5, 40)])
    p = _stats(values)
    basis, s = effective_stats(p)
    assert basis == "nonzero" and s["n"] == 40
    status, reason = domain_status(2.0, p)
    assert status == "in_distribution" and "non-zero band gap" in reason
    assert domain_status(0.0, p)[0] in ("extrapolating", "far_outside")          # a zero target sits outside the non-zero spread


def test_worse_tolerance_box_and_clusters():
    assert worse("in_distribution", "near_boundary") == "near_boundary"
    assert worse("far_outside", "extrapolating") == "far_outside"
    p = _stats(np.linspace(0, 10, 101))
    assert tolerance(p) == pytest.approx(0.5) and tolerance(p, 1.2) == pytest.approx(1.2)
    Y = np.array([[0.0, 1.0], [1.0, 2.0], [2.0, 3.0], [3.0, 4.0]])
    assert box_mask(Y, ["a", "b"], {"a": (0.5, 2.5)}).tolist() == [False, True, True, False]
    assert box_mask(Y, ["a", "b"], {"a": (None, 1.0), "b": (1.5, None)}).tolist() == [False, True, False, False]
    z = np.array([[1, 0], [0.99, 0.14], [0, 1], [-1, 0]], dtype=float)
    z /= np.linalg.norm(z, axis=1, keepdims=True)
    assert leader_clusters(z, 0.9) == 3
