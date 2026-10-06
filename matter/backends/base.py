"""The backend interface: what a design engine must offer Matter. MEIDNet is the first implementation; another
engine (a geometry-generating model, a user's own model) implements the same methods.

Phase 0 uses load_model, describe_model, assess_readiness, search, score_candidates and export; inspect_dataset,
train and evaluate are reserved for Phase 1 and raise NotAvailableInPhase until then.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from matter.api.errors import NotAvailableInPhase  # noqa: F401  (re-exported for backends)


@dataclass(frozen=True)
class ModelHandle:
    model_id: str
    path: str
    backend: str
    sha256: str
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetHandle:
    dataset_id: str
    fingerprint: str
    root: str
    meta: dict = field(default_factory=dict)


@dataclass
class SearchHooks:
    log: Callable[[str], None]
    on_step: Callable[[int, int, float], None]
    on_candidate: Callable[[dict, dict], None]
    should_stop: Callable[[], bool]


class DesignBackend(ABC):
    name: str = "abstract"

    @abstractmethod
    def load_model(self, handle: ModelHandle) -> Any: ...

    @abstractmethod
    def describe_model(self, model: Any) -> dict: ...

    def inspect_dataset(self, dataset: DatasetHandle, spec: dict) -> dict:
        raise NotAvailableInPhase(1, "Inspecting your own dataset")

    def train(self, dataset: DatasetHandle, config: dict, hooks: SearchHooks) -> ModelHandle:
        raise NotAvailableInPhase(1, "Training a model")

    def evaluate(self, model: Any, dataset: DatasetHandle, split: str) -> dict:
        raise NotAvailableInPhase(1, "Evaluating a model on your own data")

    @abstractmethod
    def assess_readiness(self, validated: Any, services: Any) -> dict: ...

    @abstractmethod
    def search(self, model: Any, config: Any, family: Any, out_dir: str, hooks: SearchHooks) -> Any: ...

    @abstractmethod
    def score_candidates(self, raw: list[dict], context: Any) -> list[dict]: ...

    @abstractmethod
    def export(self, run: dict, fmt: str, services: Any) -> bytes: ...
