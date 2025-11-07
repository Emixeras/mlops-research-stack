from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, model_validator
from sklearn.preprocessing import StandardScaler

class TrainFeaturesPayload(BaseModel):
    """Shape-safe container for train feature outputs."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    X: np.ndarray
    y: np.ndarray
    scaler: StandardScaler

    @model_validator(mode="after")
    def _check_shapes(self) -> "TrainFeaturesPayload":
        if self.X.ndim != 2:
            raise ValueError("Expected X to be a 2D array.")
        if self.y.ndim != 1:
            raise ValueError("Expected y to be a 1D array.")
        if self.X.shape[0] != self.y.shape[0]:
            raise ValueError("X and y must have the same number of samples.")
        return self


class TrainValSplitPayload(BaseModel):
    """Validated output for the train/validation split asset."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    X_train: np.ndarray
    X_val: np.ndarray
    y_train: np.ndarray
    y_val: np.ndarray

    @model_validator(mode="after")
    def _check_shapes(self) -> "TrainValSplitPayload":
        if self.X_train.shape[0] != self.y_train.shape[0]:
            raise ValueError("X_train and y_train must align in sample count.")
        if self.X_val.shape[0] != self.y_val.shape[0]:
            raise ValueError("X_val and y_val must align in sample count.")
        return self

    def empty(self) -> bool:
        return self.X_train.size == 0 and self.X_val.size == 0