from dagster import asset, Definitions, AssetIn, SourceAsset, AssetKey, FilesystemIOManager, MetadataValue, Config
import pandas as pd
import os
from pathlib import Path
import numpy as np
import mlflow
import mlflow.pyfunc
from sklearn.linear_model import LinearRegression

from mlops_system_dagster.core_utils.preprocessing import (
    IMAGE_SIZE,
    ROW_LIMIT,
    DEFAULT_PREPROCESS_CONFIG,
    extract_train_features,
    extract_test_features,
)
from mlops_system_dagster.core_utils.training import train_linear_regression
from mlops_system_dagster.core_utils.models import LinearRegressionBiomassModel
from mlops_system_dagster.core_utils.evaluation import calculate_regression_metrics, preview_markdown
from mlops_system_dagster.core_utils.schemas import TrainFeaturesPayload

# Define assets from the base pipeline that we depend on
sync_biomass_data = SourceAsset(key=AssetKey("sync_biomass_data"))
train_val_split = SourceAsset(key=AssetKey("train_val_split"))

from dagster import asset, Definitions, AssetIn, SourceAsset, AssetKey, FilesystemIOManager, MetadataValue
import pandas as pd
import os
from pathlib import Path
import numpy as np
import mlflow
import mlflow.pyfunc
from sklearn.linear_model import LinearRegression

from mlops_system_dagster.core_utils.preprocessing import (
    IMAGE_SIZE,
    ROW_LIMIT,
    DEFAULT_PREPROCESS_CONFIG,
    extract_train_features,
    extract_test_features,
)
from mlops_system_dagster.core_utils.training import train_linear_regression
from mlops_system_dagster.core_utils.models import LinearRegressionBiomassModel
from mlops_system_dagster.core_utils.evaluation import calculate_regression_metrics, preview_markdown
from mlops_system_dagster.core_utils.schemas import TrainFeaturesPayload

# Define assets from the base pipeline that we depend on
sync_biomass_data = SourceAsset(key=AssetKey("sync_biomass_data"))
train_val_split = SourceAsset(key=AssetKey("train_val_split"))

@asset(ins={"train_val_split": AssetIn("train_val_split"), "sync_biomass_data": AssetIn("sync_biomass_data")})

def lr_train_features(context, train_val_split: dict, sync_biomass_data: dict) -> dict:
    """Extract features from the training split."""
    data_dir = Path(sync_biomass_data["data_dir"])
    images_dir = data_dir / "images" / "train"
    
    train_df = train_val_split["train_df"]
    
    X, y, scaler, preview_md = extract_train_features(train_df, images_dir, row_limit=ROW_LIMIT)
    
    context.add_output_metadata({"preview": MetadataValue.md(preview_md)})
    
    return {
        "X": X,
        "y": y,
        "scaler": scaler
    }

@asset(ins={"train_val_split": AssetIn("train_val_split"), "lr_train_features": AssetIn("lr_train_features"), "sync_biomass_data": AssetIn("sync_biomass_data")})
def lr_val_features(context, train_val_split: dict, lr_train_features: dict, sync_biomass_data: dict) -> dict:
    """Extract features from the validation split using the scaler from training."""
    data_dir = Path(sync_biomass_data["data_dir"])
    images_dir = data_dir / "images" / "train" # Validation images are in the same folder as train images
    
    val_df = train_val_split["val_df"]
    scaler = lr_train_features["scaler"]
    
    # We use extract_test_features because it handles applying an existing scaler
    # and returns X, y.
    X, y, labels_present, preview_md = extract_test_features(
        val_df,
        images_dir,
        scaler=scaler,
        label_column="fresh_weight_total",
        row_limit=ROW_LIMIT,
    )
    
    context.add_output_metadata({"preview": MetadataValue.md(preview_md)})
    return {"X": X, "y": y}

@asset(ins={"lr_train_features": AssetIn("lr_train_features")})
def linear_regression_model(context, lr_train_features: dict):
    X_train = lr_train_features["X"]
    y_train = lr_train_features["y"]
    
    if X_train.size == 0:
        return None
    
    model = train_linear_regression(X_train, y_train)
    
    scaler = lr_train_features.get("scaler")
    
    # Prepare metadata for the generic logger
    params = {
        "n_features": int(X_train.shape[1]) if X_train.size else None,
        "n_samples": int(X_train.shape[0]) if X_train.size else None,
        "image_size": f"{IMAGE_SIZE[0]}x{IMAGE_SIZE[1]}",
        "image_mode": "L",
        "flatten": True,
    }
    
    return {
        "model": model,
        "params": params,
        "scaler": scaler,
    }

@asset(ins={"trained_model": AssetIn("linear_regression_model"), "sync_biomass_data": AssetIn("sync_biomass_data")})
def linear_regression_mlflow_logged_model(context, trained_model: dict, sync_biomass_data: dict):
    """
    Logs the trained Linear Regression model to MLflow.
    """
    # Hardcoded constants
    model_type = "LinearRegression"
    experiment_name = "linear_regression"
    run_name = "biomass_linear_regression"
    
    # We need to point to the root of the repo to include all code
    src_dir = Path(__file__).parent.parent.parent
    code_paths = [
        str(src_dir / "code_locations"),
        str(src_dir / "mlops_system_dagster")
    ]
    pip_requirements = ["scikit-learn", "pandas", "numpy", "mlflow"]

    # Extract version information
    git_commit = sync_biomass_data.get("git_commit")
    git_branch = sync_biomass_data.get("git_branch")
    git_repo_url = sync_biomass_data.get("git_repo_url")
    dvc_data_hash = sync_biomass_data.get("dvc_data_hash")
    
    # Extract model info
    model = trained_model["model"]
    params = trained_model.get("params", {})
    scaler = trained_model.get("scaler")
    
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    
    # Instantiate the wrapper directly
    pyfunc_model = LinearRegressionBiomassModel(
        model, 
        scaler=scaler, 
        config=DEFAULT_PREPROCESS_CONFIG
    )
    
    with mlflow.start_run(run_name=run_name) as run:
        # Log parameters
        mlflow.log_param("model_type", model_type)
        for k, v in params.items():
            if v is not None:
                mlflow.log_param(k, v)
        
        # Log version info
        if git_commit: mlflow.log_param("git_commit", git_commit)
        if git_branch: mlflow.log_param("git_branch", git_branch)
        if git_repo_url: mlflow.log_param("git_repo_url", git_repo_url)
        if dvc_data_hash: mlflow.log_param("dvc_data_hash", dvc_data_hash)
        
        # Log model
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=pyfunc_model,
            code_paths=code_paths,
            pip_requirements=pip_requirements
        )
        
        run_id = run.info.run_id
        experiment_id = run.info.experiment_id
        
        context.add_output_metadata({
            "mlflow_run_id": MetadataValue.text(run_id),
            "mlflow_experiment_id": MetadataValue.text(experiment_id),
            "mlflow_url": MetadataValue.url(
                f"{tracking_uri.rstrip('/')}/#/experiments/{experiment_id}/runs/{run_id}"
            ),
            "git_commit": MetadataValue.text(git_commit or "unknown"),
        })
        
        context.log.info(f"Logged {model_type} model to MLflow (experiment '{experiment_name}', run {run_id})")
        
    return {
        "experiment_id": experiment_id, 
        "run_id": run_id, 
        "regressor": model,
        "model_type": model_type,
        "pyfunc_model": pyfunc_model
    }

@asset(ins={"lr_val_features": AssetIn("lr_val_features"), "mlflow_logged_model": AssetIn("linear_regression_mlflow_logged_model")})
def linear_regression_evaluation(context, lr_val_features: dict, mlflow_logged_model: dict):
    """Compute validation metrics using the same fitted regressor bundled in mlflow_logged_model and log to that run."""
    
    regressor = mlflow_logged_model.get("regressor")
    run_id = mlflow_logged_model.get("run_id")
    
    X_val = lr_val_features["X"]
    y_val = lr_val_features["y"]
    
    if X_val.size == 0:
        raise ValueError("Empty validation split; cannot evaluate.")
    
    preds = regressor.predict(X_val)
    metrics = calculate_regression_metrics(y_val, preds)
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

defs = Definitions(
    assets=[
        sync_biomass_data,
        train_val_split,
        lr_train_features,
        lr_val_features,
        linear_regression_model,
        linear_regression_mlflow_logged_model,
        linear_regression_evaluation,
    ],
    resources={
        "io_manager": FilesystemIOManager(base_dir="/dagster_outputs"),
    },
)
