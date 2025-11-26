"""Model evaluation helpers (metrics + formatting + MLflow logging)."""
from __future__ import annotations

from typing import Dict, Any
import numpy as np


def calculate_regression_metrics(y_true, y_pred) -> Dict[str, Any]:
    errors = y_pred - y_true
    abs_errors = np.abs(errors)
    mae = float(np.mean(abs_errors))
    mse = float(np.mean(errors**2))
    ss_res = float(np.sum(errors**2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2)) if y_true.size else 0.0
    r2 = float(1 - ss_res / ss_tot) if ss_tot else float("nan")
    eps = 1e-9
    smape = (
        float(np.mean(2 * abs_errors / (np.abs(y_true) + np.abs(y_pred) + eps))) * 100.0
    )
    return {
        "preds": y_pred,
        "mae": mae,
        "mse": mse,
        "r2": r2,
        "smape_percent": smape,
        "n": len(y_true),
    }


def regression_metrics(X_val, y_val, model) -> Dict[str, Any]:
    """Legacy wrapper for backward compatibility."""
    preds = model.predict(X_val)
    return calculate_regression_metrics(y_val, preds)


def preview_markdown(metrics: Dict[str, Any], y_val) -> str:
    preds = metrics["preds"]
    return (
        "### Validation Metrics\n"
        f"- samples: `{metrics['n']}`\n"
        f"- MAE: `{metrics['mae']:.4f}`\n"
        f"- MSE: `{metrics['mse']:.4f}`\n"
        f"- R2: `{metrics['r2']:.4f}`\n"
        f"- sMAPE (%): `{metrics['smape_percent']:.2f}`\n"
        f"- preds_preview: `{preds[:5].tolist()}`\n"
        f"- true_preview: `{y_val[:5].tolist()}`\n"
    )
