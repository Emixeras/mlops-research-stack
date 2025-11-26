"""Training helpers for model fitting and wrapping."""
from __future__ import annotations

from typing import Dict, Any

from sklearn.linear_model import LinearRegression

from .preprocessing import DEFAULT_PREPROCESS_CONFIG
from .models import LinearRegressionBiomassModel


def train_linear_regression(X, y) -> LinearRegression:
    model = LinearRegression()
    model.fit(X, y)
    return model


def build_pyfunc_model(regressor, scaler, config: Dict[str, Any] | None = None) -> LinearRegressionBiomassModel:
    cfg = {**DEFAULT_PREPROCESS_CONFIG, **(config or {})}
    return LinearRegressionBiomassModel(regressor=regressor, scaler=scaler, config=cfg)
