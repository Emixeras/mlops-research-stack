"""XGBoost model training and PyFunc wrapper for Gradio deployment."""
from typing import Any
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, r2_score
import mlflow.pyfunc
import numpy as np
from mlops_system_dagster.core_utils.preprocessing import coerce_images, prepare_image, DEFAULT_PREPROCESS_CONFIG


def train_xgboost_regressor(X_train, y_train, n_estimators=100, max_depth=5, learning_rate=0.1):
    """Train XGBoost regression model."""
    model = xgb.XGBRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        objective='reg:squarederror',
        random_state=42
    )
    model.fit(X_train, y_train)
    return model


def evaluate_xgboost(model, X_val, y_val):
    """Evaluate model and return metrics."""
    predictions = model.predict(X_val)
    return {
        'mae': float(mean_absolute_error(y_val, predictions)),
        'r2': float(r2_score(y_val, predictions))
    }


class XGBoostBiomassModel(mlflow.pyfunc.PythonModel):
    """PyFunc model bundling preprocessing + XGBoost regressor.
    
    Input: list/sequence of image paths or raw bytes (from Gradio).
    Output: list of predictions.
    """

    def __init__(self, model, scaler, config: dict | None = None):
        self.model = model
        self.scaler = scaler
        self.config = {**DEFAULT_PREPROCESS_CONFIG, **(config or {})}

    def predict(self, context, model_input: list[Any]) -> list[float]:  # type: ignore[override]
        """Predict biomass values for a batch of inputs.
        
        MLflow expects batched inputs; we accept a list of paths/bytes (coerced internally).
        Returns a list[float] to align with pyfunc convention.
        """
        # Use shared utility to handle input (paths, bytes, etc.)
        images = coerce_images(model_input, config=self.config)
        if not images:
            return []
        
        # Extract features using shared preprocessing
        feats = [prepare_image(img, config=self.config) for img in images]
        X = np.stack(feats, axis=0)
        
        # Apply scaler and predict
        X = self.scaler.transform(X)
        preds = self.model.predict(X)
        return preds.tolist()
