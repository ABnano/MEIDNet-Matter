"""JSON that any browser can parse: NaN and infinities become null, numpy scalars become Python numbers.

FastAPI's default response would write the tokens ``NaN``/``Infinity``, which ``JSON.parse`` rejects. The walk is the
same as the Studio server's ``_finite``.
"""
from __future__ import annotations

import json
import math
from typing import Any

from fastapi.responses import JSONResponse


def finite(obj: Any) -> Any:
    """Return a copy of ``obj`` with non-finite floats replaced by None and numpy types converted."""
    if isinstance(obj, dict):
        return {str(k): finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [finite(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, (bool, int, str)) or obj is None:
        return obj
    if hasattr(obj, "tolist"):                      # numpy scalars and arrays
        return finite(obj.tolist())
    if hasattr(obj, "item"):
        return finite(obj.item())
    return obj


class MatterJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(finite(content), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
