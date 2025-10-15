"""Model classes (pyfunc wrappers, etc.)."""
from __future__ import annotations

from typing import Any, List
import numpy as np
import mlflow.pyfunc

from .preprocessing import coerce_images, prepare_image, DEFAULT_PREPROCESS_CONFIG


class LinearRegressionBiomassModel(mlflow.pyfunc.PythonModel):
    """PyFunc model bundling preprocessing + a fitted regressor.

    Input: list/sequence of image paths or raw bytes.
    Output: list of predictions.
    """

    def __init__(self, scaler, regressor, config: dict | None = None):
        self.scaler = scaler
        self.regressor = regressor
        self.config = {**DEFAULT_PREPROCESS_CONFIG, **(config or {})}

    def predict(self, context, model_input: list[Any]) -> list[float]:  # type: ignore[override]
        """Predict biomass values for a batch of inputs.

        MLflow expects batched inputs; we accept a list of paths/bytes (coerced internally).
        Returns a list[float] to align with pyfunc convention.
        """
        images = coerce_images(model_input, config=self.config)
        if not images:
            return []
        feats = [prepare_image(img, config=self.config) for img in images]
        X = np.stack(feats, axis=0)
        X = self.scaler.transform(X)
        preds = self.regressor.predict(X) 
        return preds.tolist()
