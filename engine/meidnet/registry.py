"""
A tiny registry so that names in family files map to Python functions.

Adding your own constraint or search term takes three lines::

    from meidnet.constraints import CONSTRAINTS

    @CONSTRAINTS.register("no_lead", "Rejects any composition containing Pb.")
    def no_lead(cand, **params):
        return cand.result("no_lead", "Pb" not in cand.elements.values())

and then ``- {name: no_lead}`` in the family's ``constraints`` list (load the file
that defines it with ``plugins: [my_rules.py]`` in meidnet.yaml).
"""
from __future__ import annotations

from typing import Callable


class Registry:
    def __init__(self, kind: str):
        self.kind = kind
        self._items: dict[str, Callable] = {}
        self._docs: dict[str, str] = {}

    def register(self, name: str, doc: str = ""):
        def deco(fn):
            self._items[name] = fn
            self._docs[name] = doc or (fn.__doc__ or "").strip()
            return fn
        return deco

    def get(self, name: str) -> Callable:
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(
                f"Unknown {self.kind} '{name}'. Available: {', '.join(sorted(self._items))}. "
                "Custom ones must be registered in a plugin file listed under 'plugins'."
            ) from None

    def doc(self, name: str) -> str:
        return self._docs.get(name, "")

    def names(self) -> list[str]:
        return sorted(self._items)

    def __contains__(self, name: str) -> bool:
        return name in self._items
