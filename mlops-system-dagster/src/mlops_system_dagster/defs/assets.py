import os
from pathlib import Path

import pandas as pd
from dagster import asset, MetadataValue
from sklearn.model_selection import train_test_split
import numpy as np
import mlflow
import mlflow.pyfunc

LABEL_COLUMN = "fresh_weight_total"

GIT_REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent

from mlops_system_dagster.core_utils.preprocessing import (
    IMAGE_SIZE,
    ROW_LIMIT,
    DEFAULT_PREPROCESS_CONFIG,
    extract_train_features,
    extract_test_features,
)
from mlops_system_dagster.core_utils.training import train_linear_regression, build_pyfunc_model
from mlops_system_dagster.core_utils.evaluation import regression_metrics, preview_markdown
from mlops_system_dagster.core_utils.dvc_utils import configure_cache, dvc_pull


@asset
def sync_biomass_data(context) -> Path:
    """Ensure DVC-tracked biomass data present; return its directory path."""
    data_dir = GIT_REPO_ROOT / "data" / "biomass"
    env = os.environ.copy()
    try:
        cache_dir = configure_cache(GIT_REPO_ROOT, env=env)
        if cache_dir:
            context.log.info(f"Configured DVC cache.dir to {cache_dir}")
    except Exception as e:
        context.log.warning(f"DVC cache configuration failed/skipped: {e}")
    try:
        dvc_pull(GIT_REPO_ROOT, env=env)
        context.log.info("DVC sync complete")
    except Exception as e:
        raise RuntimeError(f"dvc pull failed: {e}") from e
    return data_dir

@asset
def train_table(context, sync_biomass_data: Path) -> pd.DataFrame:  # type: ignore[override]
    df = pd.read_csv(sync_biomass_data / "train.csv")
    preview = df.head().to_markdown()
    context.add_output_metadata({"preview": MetadataValue.md(preview)})
    return df


@asset
def test_table(context, sync_biomass_data: Path) -> pd.DataFrame:  # type: ignore[override]
    path = sync_biomass_data / "test.csv"
    if not path.exists():
        context.log.warning("test.csv not found; returning empty DataFrame")
        return pd.DataFrame()
    df = pd.read_csv(path)
    preview = df.head().to_markdown()
    context.add_output_metadata({"preview": MetadataValue.md(preview)})
    return df


@asset
def train_features(context, train_table: pd.DataFrame, sync_biomass_data: Path) -> dict:  # type: ignore[override]
    images_dir = sync_biomass_data / "images" / "train"
    X, y, scaler, preview_md = extract_train_features(train_table, images_dir, row_limit=ROW_LIMIT)
    context.add_output_metadata({"preview": MetadataValue.md(preview_md)})
    return {"X": X, "y": y, "scaler": scaler}


@asset
def test_features(context, test_table: pd.DataFrame, train_features: dict, sync_biomass_data: Path) -> dict:  # type: ignore[override]
    X_train_scaler = train_features.get("scaler") if isinstance(train_features, dict) else None
    images_dir = sync_biomass_data / "images" / "test"
    X, y, labels_present, preview_md = extract_test_features(
        test_table,
        images_dir,
        scaler=X_train_scaler,
        label_column=LABEL_COLUMN,
        row_limit=ROW_LIMIT,
    )
    context.add_output_metadata({"preview": MetadataValue.md(preview_md)})
    return {"X": X, "y": y, "labels_present": labels_present}


@asset
def train_val_split(context, train_features: dict):  # type: ignore[override]
    X = train_features["X"]
    y = train_features["y"]
    if X.size == 0:
        return {"X_train": np.array([]), "X_val": np.array([]), "y_train": np.array([]), "y_val": np.array([])}
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
    context.add_output_metadata(
        {
            "preview": MetadataValue.md(
                "### Train/Val Split\n"
                f"- train_samples: `{X_train.shape[0]}`\n"
                f"- val_samples: `{X_val.shape[0]}`\n"
            )
        }
    )
    return {"X_train": X_train, "X_val": X_val, "y_train": y_train, "y_val": y_val}


@asset
def simple_model(context, train_val_split: dict, train_features: dict):  # type: ignore[override]
    X_train = train_val_split["X_train"]
    y_train = train_val_split["y_train"]
    if X_train.size == 0:
        return None
    model = train_linear_regression(X_train, y_train)
    scaler = train_features.get("scaler") if isinstance(train_features, dict) else None
    # Keep model training isolated; logging handled by downstream asset
    return model


@asset
def mlflow_logged_model(context, simple_model, train_val_split: dict, train_features: dict):  # type: ignore[override]
    """Log the trained model (with preprocessing wrapper) to MLflow as pyfunc.

    Returns dict containing experiment_id and run_id (or None values if logging skipped).
    """
    if simple_model is None:
        context.log.warning("No model to log (simple_model returned None)")
        return {"experiment_id": None, "run_id": None}
    X_train = train_val_split.get("X_train", np.array([]))
    scaler = train_features.get("scaler") if isinstance(train_features, dict) else None
    pyfunc_model = build_pyfunc_model(simple_model, scaler, DEFAULT_PREPROCESS_CONFIG)
    params = {
        "model_type": "LinearRegression",
        "n_features": int(X_train.shape[1]) if X_train.size else None,
        "n_samples": int(X_train.shape[0]) if X_train.size else None,
        "image_size": f"{IMAGE_SIZE[0]}x{IMAGE_SIZE[1]}",
        "image_mode": "L",
        "flatten": True,
    }
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(tracking_uri)

    with mlflow.start_run(run_name="biomass_linear_regression") as run:
        for k, v in params.items():
            if v is not None:
                mlflow.log_param(k, v)
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=pyfunc_model,
            code_paths=[str(GIT_REPO_ROOT / 'mlops-system-dagster' / 'src')],
        )
        run_id = run.info.run_id
        experiment_id = run.info.experiment_id
        context.add_output_metadata(
            {
                "mlflow_run_id": MetadataValue.text(run_id),
                "mlflow_experiment_id": MetadataValue.text(experiment_id),
                "mlflow_url": MetadataValue.url(
                    f"{tracking_uri.rstrip('/')}/#/experiments/{experiment_id}/runs/{run_id}"
                ),
            }
        )
        context.log.info(
            f"Logged pyfunc model to MLflow (experiment {experiment_id}, run {run_id})"
        )
    return {"experiment_id": experiment_id, "run_id": run_id}


@asset
def model_evaluation(context, simple_model, train_val_split: dict):  # type: ignore[override]
    if simple_model is None:
        return {"error": "Model not trained"}
    X_val = train_val_split["X_val"]
    y_val = train_val_split["y_val"]
    if X_val.size == 0:
        return {"error": "Empty validation split"}
    metrics = regression_metrics(X_val, y_val, simple_model)
    md = preview_markdown(metrics, y_val)
    context.add_output_metadata({"preview": MetadataValue.md(md)})
    # Best effort: attach metrics to latest run if we captured one in simple_model metadata
    run_id_meta = context.get_step_context().parent_run_id if hasattr(context, "get_step_context") else None
    # Fall back to mlflow search disabled here to keep deterministic; rely on simple_model output metadata
    try:
        # Only log scalar metrics (exclude preds array)
        scalar_metrics = {k: v for k, v in metrics.items() if k not in {"preds", "n"}}
        # We cannot easily recover run_id from metadata here without Dagster IO manager; skip if absent
        # Provided for future extension.
        pass
    except Exception:
        context.log.debug("Metric logging skipped")
    return {k: v for k, v in metrics.items() if k != "preds"}

