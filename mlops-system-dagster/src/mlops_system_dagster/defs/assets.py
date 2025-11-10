import os
from pathlib import Path

from mlops_system_dagster.defs.resources import TrainValSplitConfig
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
from mlops_system_dagster.core_utils.dvc_utils import (
    configure_cache,
    dvc_pull,
    get_git_commit_hash,
    get_git_branch,
    get_git_repo_url,
    get_dvc_data_hash,
)
from mlops_system_dagster.core_utils.schemas import (
    TrainFeaturesPayload,
    TrainValSplitPayload,
)

@asset
def sync_biomass_data(context) -> dict:
    """Ensure DVC-tracked biomass data present; return directory path and version info."""
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
    
    # Get version information for traceability
    git_hash = get_git_commit_hash(GIT_REPO_ROOT)
    git_branch = get_git_branch(GIT_REPO_ROOT)
    git_repo_url = get_git_repo_url(GIT_REPO_ROOT)
    dvc_hash = get_dvc_data_hash(GIT_REPO_ROOT, "data.dvc")
    
    context.add_output_metadata({
        "git_commit": MetadataValue.text(git_hash or "unknown"),
        "git_branch": MetadataValue.text(git_branch or "unknown"),
        "git_repo_url": MetadataValue.text(git_repo_url or "unknown"),
        "dvc_data_hash": MetadataValue.text(dvc_hash or "unknown"),
    })
    
    return {
        "data_dir": data_dir,
        "git_commit": git_hash,
        "git_branch": git_branch,
        "git_repo_url": git_repo_url,
        "dvc_data_hash": dvc_hash,
    }

@asset
def train_table(context, sync_biomass_data: dict) -> pd.DataFrame:  # type: ignore[override]
    data_dir = Path(sync_biomass_data["data_dir"])
    df = pd.read_csv(data_dir / "train.csv")
    preview = df.head().to_markdown()
    context.add_output_metadata({"preview": MetadataValue.md(preview)})
    return df


@asset
def test_table(context, sync_biomass_data: dict) -> pd.DataFrame:  # type: ignore[override]
    data_dir = Path(sync_biomass_data["data_dir"])
    path = data_dir / "test.csv"
    if not path.exists():
        context.log.warning("test.csv not found; returning empty DataFrame")
        return pd.DataFrame()
    df = pd.read_csv(path)
    preview = df.head().to_markdown()
    context.add_output_metadata({"preview": MetadataValue.md(preview)})
    return df


@asset
def train_features(context, train_table: pd.DataFrame, sync_biomass_data: dict) -> dict:  # type: ignore[override]
    data_dir = Path(sync_biomass_data["data_dir"])
    images_dir = data_dir / "images" / "train"
    X, y, scaler, preview_md = extract_train_features(train_table, images_dir, row_limit=ROW_LIMIT)
    payload = TrainFeaturesPayload(X=X, y=y, scaler=scaler)
    context.add_output_metadata({"preview": MetadataValue.md(preview_md)})
    return payload.model_dump()


@asset
def test_features(context, test_table: pd.DataFrame, train_features: dict, sync_biomass_data: dict) -> dict:  # type: ignore[override]
    data_dir = Path(sync_biomass_data["data_dir"])
    X_train_scaler = train_features.get("scaler") if isinstance(train_features, dict) else None
    images_dir = data_dir / "images" / "test"
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
def train_val_split(context, train_features: dict, config: TrainValSplitConfig) -> dict:
    """Splits features into train/validation sets based on config."""
    features = TrainFeaturesPayload.model_validate(train_features)
    # The 'config' parameter is now directly injected by Dagster and already validated.
    test_size = config.test_size

    X_train, X_val, y_train, y_val = train_test_split(
        features.X,
        features.y,
        test_size=test_size,
        random_state=42,
    )

    payload = TrainValSplitPayload(
        X_train=X_train,
        X_val=X_val,
        y_train=y_train,
        y_val=y_val,
    )
    context.add_output_metadata(
        {
            "preview": MetadataValue.md(
                f"### Train/Val Split\n- train_samples: `{X_train.shape[0]}`\n"
                f"- val_samples: `{X_val.shape[0]}`\n- test_size: `{test_size}`"
            )
        }
    )
    return payload.model_dump()


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
def mlflow_logged_model(context, simple_model, train_val_split: dict, train_features: dict, sync_biomass_data: dict):  # type: ignore[override]
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
    
    # Extract version information
    git_commit = sync_biomass_data.get("git_commit")
    git_branch = sync_biomass_data.get("git_branch")
    git_repo_url = sync_biomass_data.get("git_repo_url")
    dvc_data_hash = sync_biomass_data.get("dvc_data_hash")
    
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(tracking_uri)

    with mlflow.start_run(run_name="biomass_linear_regression") as run:
        # Log parameters
        for k, v in params.items():
            if v is not None:
                mlflow.log_param(k, v)
        
        # Log version info as parameters for better discoverability
        if git_commit:
            mlflow.log_param("git_commit", git_commit)
        if git_branch:
            mlflow.log_param("git_branch", git_branch)
        if git_repo_url:
            mlflow.log_param("git_repo_url", git_repo_url)
        if dvc_data_hash:
            mlflow.log_param("dvc_data_hash", dvc_data_hash)
        
        # Use the actual package directory (not the parent 'src') so MLflow adds correct import path
        package_dir = GIT_REPO_ROOT / 'mlops-system-dagster' / 'src' / 'mlops_system_dagster'
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=pyfunc_model,
            code_paths=[str(package_dir)],
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
                "git_commit": MetadataValue.text(git_commit or "unknown"),
                "git_branch": MetadataValue.text(git_branch or "unknown"),
                "git_repo_url": MetadataValue.text(git_repo_url or "unknown"),
                "dvc_data_hash": MetadataValue.text(dvc_data_hash or "unknown"),
            }
        )
        context.log.info(
            f"Logged pyfunc model to MLflow (experiment {experiment_id}, run {run_id})"
        )
        context.log.info(f"Version: git={git_commit} (branch={git_branch}), dvc_data={dvc_data_hash}")
    return {"experiment_id": experiment_id, "run_id": run_id, "regressor": simple_model}


@asset
def model_evaluation(context, train_val_split: dict, mlflow_logged_model: dict):  # type: ignore[override]
    """Compute validation metrics using the same fitted regressor bundled in mlflow_logged_model and log to that run.

    Assumes mlflow_logged_model returned a dict containing 'regressor' and 'run_id'.
    Fails fast if required pieces are missing.
    """
    if not isinstance(mlflow_logged_model, dict):
        raise ValueError("mlflow_logged_model output malformed (expected dict).")
    regressor = mlflow_logged_model.get("regressor")
    run_id = mlflow_logged_model.get("run_id")
    if regressor is None:
        raise ValueError("Missing 'regressor' in mlflow_logged_model output.")
    if not run_id:
        raise ValueError("Missing 'run_id' in mlflow_logged_model output.")
    X_val = train_val_split["X_val"]
    y_val = train_val_split["y_val"]
    if X_val.size == 0:
        raise ValueError("Empty validation split; cannot evaluate.")
    metrics = regression_metrics(X_val, y_val, regressor)
    md = preview_markdown(metrics, y_val)
    context.add_output_metadata({"preview": MetadataValue.md(md)})

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    with mlflow.start_run(run_id=run_id):
        scalar_metrics = {k: v for k, v in metrics.items() if k not in {"preds"}}
        mlflow.log_metrics({k: float(v) for k, v in scalar_metrics.items() if isinstance(v, (int, float))})
        preview_art = {
            "preds_preview": metrics["preds"][:25].tolist(),
            "y_preview": y_val[:25].tolist(),
            "n_total": int(metrics["n"]),
        }
        mlflow.log_dict(preview_art, "evaluation/pred_preview.json")
    return {k: v for k, v in metrics.items() if k != "preds"}

