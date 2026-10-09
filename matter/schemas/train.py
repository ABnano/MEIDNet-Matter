"""A Train Lite request: a small, fixed MEIDNet training on the shared server, meant for understanding the method.

The data (a 1,500-material subset of Perov-5, featurised at build time), the recipe (the demo's own) and the budget are
fixed; the user chooses the number of epochs and the seed. The result is a real MEIDNet model trained from scratch,
measured on 500 validation materials next to the demo's full model measured on the same ones.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TRAINLITE_SCHEMA_ID = "meidnet-matter/trainlite/1"
EPOCH_OPTIONS = (10, 20, 50)


class TrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    epochs: Literal[10, 20, 50] = Field(20, description="how many passes over the 1,500 materials (10, 20 or 50)")
    seed: int = Field(0, ge=0, le=9999, description="weight initialisation and shuffling; the same seed gives the same model")
