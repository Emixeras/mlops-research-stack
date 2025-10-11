"""Model evaluation helpers (metrics + formatting + MLflow logging)."""
from __future__ import annotations

from typing import Dict, Any
import numpy as np


def regression_metrics(X_val, y_val, model) -> Dict[str, Any]:
    preds = model.predict(X_val)
    errors = preds - y_val
    abs_errors = np.abs(errors)
    mae = float(np.mean(abs_errors))
    mse = float(np.mean(errors**2))
    ss_res = float(np.sum(errors**2))
    ss_tot = float(np.sum((y_val - np.mean(y_val)) ** 2)) if y_val.size else 0.0
    r2 = float(1 - ss_res / ss_tot) if ss_tot else float("nan")
    eps = 1e-9
    smape = (
        float(np.mean(2 * abs_errors / (np.abs(y_val) + np.abs(preds) + eps))) * 100.0
    )
    return {
        "preds": preds,
        "mae": mae,
        "mse": mse,
        "r2": r2,
        "smape_percent": smape,
        "n": len(y_val),
    }


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
