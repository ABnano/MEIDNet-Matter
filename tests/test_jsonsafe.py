"""JSON answers never contain NaN or numpy types."""
import json
import math

import numpy as np

from matter.jsonsafe import MatterJSONResponse, finite


def test_non_finite_numbers_become_null_and_numpy_becomes_plain():
    obj = {"a": float("nan"), "b": [1.0, float("inf"), -float("inf")], "c": np.float32(2.5), "d": np.int64(3),
           "e": np.array([1.0, np.nan]), "f": {"g": (np.bool_(True), None, "s")}}
    out = finite(obj)
    assert out == {"a": None, "b": [1.0, None, None], "c": 2.5, "d": 3, "e": [1.0, None], "f": {"g": [True, None, "s"]}}
    assert type(out["c"]) is float and type(out["d"]) is int


def test_response_rendering_is_strict_json():
    body = MatterJSONResponse({"x": float("nan"), "y": math.inf, "z": np.float64(1.0)}).body
    assert json.loads(body) == {"x": None, "y": None, "z": 1.0}
    assert b"NaN" not in body
