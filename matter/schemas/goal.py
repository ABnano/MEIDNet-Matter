"""A design goal: what the candidate should satisfy, in the researcher's terms. The goals service turns it into the
engine's generation settings."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Kind = Literal["value", "values", "range", "at_least", "at_most", "maximize", "minimize"]
Priority = Literal["primary", "secondary", "tertiary"]


class Objective(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property: str = Field(description="a property the model predicts, e.g. dir_gap")
    kind: Kind = "value"
    value: float | None = Field(None, description="the target for value / at_least / at_most")
    values: list[float] | None = Field(None, description="several targets, one search target per value")
    low: float | None = Field(None, description="the lower end of a range")
    high: float | None = Field(None, description="the upper end of a range")
    tolerance: float | None = Field(None, ge=0, description="half-width of the accepted window around a value")
    priority: Priority = "primary"
    loss: Literal["l1", "l2"] | None = Field(None, description="distance used while searching (default l2)")

    @model_validator(mode="after")
    def _needs(self):
        k = self.kind
        if k in ("value", "at_least", "at_most") and self.value is None:
            raise ValueError(f"kind '{k}' needs a value")
        if k == "values" and not self.values:
            raise ValueError("kind 'values' needs a non-empty list of values")
        if k == "range":
            if self.low is None or self.high is None:
                raise ValueError("kind 'range' needs low and high")
            if self.low >= self.high:
                raise ValueError("a range needs low < high")
        return self


class ElementsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exclude: list[str] = Field(default_factory=list)
    only: dict[str, list[str]] = Field(default_factory=dict, description="group -> allowed elements")
    presets: list[str] = Field(default_factory=list)


class NoveltySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    require_not_in_dataset: bool = False


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    per_target: int = Field(3, ge=1, le=50, description="candidates to keep per target")
    population: int = Field(24, ge=4, le=256)
    rounds: int = Field(3, ge=1, le=200)
    steps: int = Field(300, ge=10, le=5000)
    seed: int = 937
    min_cosine_sep: float = Field(0.98, ge=0.5, le=1.0)


class Goal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = "perov5-demo"
    model_id: str | None = None
    family: str = "perovskite_abx3"
    variant: str | None = None
    objectives: list[Objective] = Field(min_length=1)
    elements: ElementsSpec = Field(default_factory=ElementsSpec)
    max_elements: int | None = Field(None, ge=1)
    rule_overrides: dict[str, dict[str, float]] = Field(default_factory=dict)
    disabled_rules: list[str] = Field(default_factory=list)
    novelty: NoveltySpec = Field(default_factory=NoveltySpec)
    budget: Budget = Field(default_factory=Budget)
    diverse_set: bool | None = Field(None, description="search for a diverse set (set by the readiness advice when omitted)")

    @model_validator(mode="after")
    def _distinct_properties(self):
        seen = set()
        for o in self.objectives:
            if o.property in seen:
                raise ValueError(f"property '{o.property}' appears twice in the objectives")
            seen.add(o.property)
        return self
