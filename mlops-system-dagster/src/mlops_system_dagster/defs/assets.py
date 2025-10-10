import os
import subprocess
from pathlib import Path
from typing import Generator
import joblib
from tempfile import TemporaryDirectory

import pandas as pd
from dagster import asset, MetadataValue
from PIL import Image
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

LABEL_COLUMN = "fresh_weight_total"
import numpy as np
import mlflow
import mlflow.sklearn

GIT_REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent

IMAGE_SIZE = (64, 64)  # central place to change feature resolution
ROW_LIMIT = 100  # subset size for PoC speed


def _load_and_flatten(image_path: Path) -> np.ndarray | None:
    if not image_path.exists():
        return None
    with Image.open(image_path).convert("L") as img:
        return np.array(img.resize(IMAGE_SIZE)).flatten()


@asset
def sync_biomass_data(context) -> Path:
    """Load DVC data and return the biomass data directory path."""
    data_dir = GIT_REPO_ROOT / "data" / "biomass"
    result = subprocess.run(
        ["dvc", "pull"], capture_output=True, text=True, cwd=GIT_REPO_ROOT
    )
    if result.returncode != 0:
        raise Exception(
            "dvc pull failed\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    context.log.info("DVC sync complete")
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
    features, labels = [], []
    for _, row in train_table.head(ROW_LIMIT).iterrows():
        img_path = images_dir / row.get("filename", "")
        arr = _load_and_flatten(img_path)
        if arr is not None:
            features.append(arr)
            labels.append(row.get("fresh_weight_total"))
    if not features:
        return {"X": np.array([]), "y": np.array([]), "scaler": None}
    scaler = StandardScaler()
    X = scaler.fit_transform(features)
    y = np.array(labels)
    preview_md = (
        "### Train Features Preview\n"
        f"- samples: `{X.shape[0]}`\n"
        f"- feature_dim: `{X.shape[1]}`\n"
        f"- y_preview: `{y[:5].tolist()}`\n"
    )
    context.add_output_metadata({"preview": MetadataValue.md(preview_md)})
    return {"X": X, "y": y, "scaler": scaler}


@asset
def test_features(context, test_table: pd.DataFrame, train_features: dict, sync_biomass_data: Path) -> dict:  # type: ignore[override]
    """Prepare test features (labels OPTIONAL; not used in evaluation now)."""
    if test_table.empty:
        context.add_output_metadata({"preview": MetadataValue.md("Empty test table")})
        return {"X": np.array([]), "y": np.array([]), "labels_present": False}
    images_dir = sync_biomass_data / "images" / "test"
    scaler = train_features.get("scaler")
    features, labels = [], []
    label_present = LABEL_COLUMN in test_table.columns
    for _, row in test_table.head(ROW_LIMIT).iterrows():
        img_path = images_dir / row.get("filename", "")
        arr = _load_and_flatten(img_path)
        if arr is not None:
            features.append(arr)
            if label_present:
                labels.append(row.get(LABEL_COLUMN))
    if not features:
        context.add_output_metadata(
            {"preview": MetadataValue.md("No test images produced features")}
        )
        return {"X": np.array([]), "y": np.array([]), "labels_present": label_present}
    X = scaler.transform(features) if scaler else np.array(features)
    y = np.array(labels) if label_present else np.array([])
    preview_md = (
        "### Test Features Preview\n"
        f"- samples: `{X.shape[0]}`\n"
        f"- feature_dim: `{X.shape[1] if X.ndim==2 else 'NA'}`\n"
        f"- labels_present: `{label_present}`\n"
        f"- y_preview: `{y[:5].tolist()}`\n"
    )
    context.add_output_metadata({"preview": MetadataValue.md(preview_md)})
    return {"X": X, "y": y, "labels_present": label_present}


@asset
def train_val_split(context, train_features: dict):  # type: ignore[override]
    X = train_features["X"]
    y = train_features["y"]
    if X.size == 0:
        return {
            "X_train": np.array([]),
            "X_val": np.array([]),
            "y_train": np.array([]),
            "y_val": np.array([]),
        }
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
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
def simple_model(context, train_val_split: dict):  # type: ignore[override]
    X_train = train_val_split["X_train"]
    y_train = train_val_split["y_train"]
    if X_train.size == 0:
        return None

    # Train model
    model = LinearRegression()
    model.fit(X_train, y_train)

    # Simple MLflow logging
    try:
        mlflow.set_tracking_uri("http://localhost:5000")
        with mlflow.start_run(run_name="biomass_linear_regression") as run:
            mlflow.log_param("model_type", "LinearRegression")
            mlflow.log_param("n_features", X_train.shape[1])
            mlflow.log_param("n_samples", X_train.shape[0])

            # Log the model using mlflow.sklearn
            mlflow.sklearn.log_model(sk_model=model, artifact_path="model")

            run_id = run.info.run_id
            context.add_output_metadata({
                "mlflow_run_id": MetadataValue.text(run_id),
                "mlflow_url": MetadataValue.url(f"http://localhost:5000/#/experiments/0/runs/{run_id}"),
            })
            context.log.info(f"Successfully logged model to MLflow run: {run_id}")

    except Exception as e:
        context.log.warning(f"MLflow logging failed: {e}")

    # Model coefficients metadata
    if getattr(model, "coef_", None) is not None and model.coef_.size <= 10:
        coeffs_preview = {f"w{i}": float(c) for i, c in enumerate(model.coef_)}
        context.add_output_metadata({
            "coefficients": MetadataValue.md(
                "\n".join([f"- {k}: {v:.4f}" for k, v in coeffs_preview.items()])
            )
        })

    return model


@asset
def model_evaluation(context, simple_model, train_val_split: dict):  # type: ignore[override]
    if simple_model is None:
        return {"error": "Model not trained"}
    X_val = train_val_split["X_val"]
    y_val = train_val_split["y_val"]
    if X_val.size == 0:
        return {"error": "Empty validation split"}

    # Calculate predictions and metrics
    preds = simple_model.predict(X_val)
    errors = preds - y_val
    abs_errors = np.abs(errors)
    mae = float(np.mean(abs_errors))
    mse = float(np.mean(errors**2))
    ss_res = float(np.sum(errors**2))
    ss_tot = float(np.sum((y_val - np.mean(y_val)) ** 2)) if y_val.size else 0.0
    r2 = float(1 - ss_res / ss_tot) if ss_tot else float("nan")

    # Percentage-style metric: sMAPE (symmetric MAPE)
    eps = 1e-9
    smape = (
        float(np.mean(2 * abs_errors / (np.abs(y_val) + np.abs(preds) + eps))) * 100.0
    )

    # Try to log metrics to MLflow with error handling
    try:
        mlflow.set_tracking_uri("http://localhost:5000")

        # Get the most recent run and log metrics to it
        experiment = mlflow.get_experiment_by_name("Default")
        if experiment:
            runs = mlflow.search_runs(
                experiment_ids=[experiment.experiment_id], max_results=1
            )
            if not runs.empty:
                run_id = runs.iloc[0]["run_id"]
                with mlflow.start_run(run_id=run_id):
                    mlflow.log_metric("mae", mae)
                    mlflow.log_metric("mse", mse)
                    mlflow.log_metric("r2", r2)
                    mlflow.log_metric("smape_percent", smape)

                    context.log.info("Successfully logged metrics to MLflow")

    except Exception as e:
        context.log.warning(f"Could not log metrics to MLflow: {e}")
        # Continue without MLflow - don't fail the pipeline

    preview_md = (
        "### Validation Metrics\n"
        f"- samples: `{len(y_val)}`\n"
        f"- MAE: `{mae:.4f}`\n"
        f"- MSE: `{mse:.4f}`\n"
        f"- R2: `{r2:.4f}`\n"
        f"- sMAPE (%): `{smape:.2f}`\n"
        f"- preds_preview: `{preds[:5].tolist()}`\n"
        f"- true_preview: `{y_val[:5].tolist()}`\n"
    )
    context.add_output_metadata({"preview": MetadataValue.md(preview_md)})
    return {
        "mae": mae,
        "mse": mse,
        "r2": r2,
        "smape_percent": smape,
        "n": len(y_val),
    }

