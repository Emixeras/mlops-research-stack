"""XGBoost experiment Dagster assets."""
from dagster import asset, Definitions, AssetIn, SourceAsset, AssetKey, FilesystemIOManager, MetadataValue
import pandas as pd
import os
from pathlib import Path
import mlflow
import mlflow.pyfunc

from mlops_system_dagster.core_utils.preprocessing import (
    IMAGE_SIZE,
    ROW_LIMIT,
    DEFAULT_PREPROCESS_CONFIG,
    extract_train_features,
    extract_test_features,
)
from .model import train_xgboost_regressor, evaluate_xgboost, XGBoostBiomassModel

# Import base assets from core pipeline
sync_biomass_data = SourceAsset(key=AssetKey("sync_biomass_data"))
train_val_split = SourceAsset(key=AssetKey("train_val_split"))


@asset(ins={"train_val_split": AssetIn("train_val_split"), "sync_biomass_data": AssetIn("sync_biomass_data")})
def xgboost_train_features(context, train_val_split: dict, sync_biomass_data: dict) -> dict:
    """Extract features from the training split for XGBoost."""
    data_dir = Path(sync_biomass_data["data_dir"])
    images_dir = data_dir / "images" / "train"
    
    train_df = train_val_split["train_df"]
    
    # Extract features using shared preprocessing (grayscale pixel stats)
    X, y, scaler, preview_md = extract_train_features(train_df, images_dir, row_limit=ROW_LIMIT)
    
    context.add_output_metadata({"preview": MetadataValue.md(preview_md)})
    
    return {
        "X": X,
        "y": y,
        "scaler": scaler
    }


@asset(ins={"train_val_split": AssetIn("train_val_split"), "xgboost_train_features": AssetIn("xgboost_train_features"), "sync_biomass_data": AssetIn("sync_biomass_data")})
def xgboost_val_features(context, train_val_split: dict, xgboost_train_features: dict, sync_biomass_data: dict) -> dict:
    """Extract features from the validation split using the scaler from training."""
    data_dir = Path(sync_biomass_data["data_dir"])
    images_dir = data_dir / "images" / "train"  # Validation images are in the same folder
    
    val_df = train_val_split["val_df"]
    scaler = xgboost_train_features["scaler"]
    
    # Use extract_test_features because it handles applying an existing scaler
    X, y, labels_present, preview_md = extract_test_features(
        val_df,
        images_dir,
        scaler=scaler,
        label_column="fresh_weight_total",
        row_limit=ROW_LIMIT,
    )
    
    context.add_output_metadata({"preview": MetadataValue.md(preview_md)})
    return {"X": X, "y": y}


@asset(ins={"xgboost_train_features": AssetIn("xgboost_train_features")})
def xgboost_model(context, xgboost_train_features: dict):
    """Train XGBoost model."""
    X_train = xgboost_train_features["X"]
    y_train = xgboost_train_features["y"]
    
    if X_train.size == 0:
        context.log.warning("No training data available")
        return None
    
    # Hyperparameters
    n_estimators = 150
    max_depth = 7
    learning_rate = 0.1
    
    model = train_xgboost_regressor(X_train, y_train, n_estimators, max_depth, learning_rate)
    scaler = xgboost_train_features.get("scaler")
    
    # Prepare metadata
    params = {
        "n_estimators": n_estimators,
        "max_depth": max_depth,
        "learning_rate": learning_rate,
        "n_features": int(X_train.shape[1]) if X_train.size else None,
        "n_samples": int(X_train.shape[0]) if X_train.size else None,
        "image_size": f"{IMAGE_SIZE[0]}x{IMAGE_SIZE[1]}",
        "image_mode": "L",
        "flatten": True,
    }
    
    context.add_output_metadata({
        "n_estimators": n_estimators,
        "max_depth": max_depth,
        "training_samples": len(X_train)
    })
    
    return {
        "model": model,
        "params": params,
        "scaler": scaler,
    }


@asset(ins={"trained_model": AssetIn("xgboost_model"), "sync_biomass_data": AssetIn("sync_biomass_data")})
def xgboost_mlflow_logged_model(context, trained_model: dict, sync_biomass_data: dict):
    """Log XGBoost model to MLflow with PyFunc wrapper for Gradio compatibility."""
    
    # Hardcoded constants
    model_type = "XGBoost"
    experiment_name = "xgboost2"
    run_name = "biomass_xgboost"
    
    # Code paths for MLflow to bundle
    src_dir = Path(__file__).parent.parent.parent
    code_paths = [
        str(src_dir / "code_locations"),
        str(src_dir / "mlops_system_dagster")
    ]
    pip_requirements = ["xgboost", "scikit-learn", "pandas", "numpy", "mlflow", "pillow"]

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
    
    # Instantiate the PyFunc wrapper directly (like LinearRegression/ResNet)
    pyfunc_model = XGBoostBiomassModel(
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
        
        # Log model with PyFunc wrapper (NOT mlflow.xgboost.log_model)
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
        "model": model,
        "model_type": model_type,
        "pyfunc_model": pyfunc_model
    }


@asset(ins={"xgboost_val_features": AssetIn("xgboost_val_features"), "mlflow_logged_model": AssetIn("xgboost_mlflow_logged_model")})
def xgboost_evaluation(context, xgboost_val_features: dict, mlflow_logged_model: dict):
    """Evaluate the XGBoost model using the PyFunc wrapper."""
    from mlops_system_dagster.core_utils.evaluation import calculate_regression_metrics, preview_markdown
    import numpy as np
    
    run_id = mlflow_logged_model["run_id"]
    pyfunc_model = mlflow_logged_model["pyfunc_model"]
    
    X_val = xgboost_val_features["X"]
    y_val = xgboost_val_features["y"]
    
    if X_val.size == 0:
        context.log.warning("No validation data available")
        return None
    
    # Evaluate using the PyFunc wrapper's predict method
    # Note: PyFunc expects list input, but we have numpy array with features already extracted
    # For evaluation, we'll use the raw model directly since we already have features
    model = mlflow_logged_model["model"]
    predictions = model.predict(X_val)
    
    metrics = calculate_regression_metrics(y_val, predictions)
    preview_md = preview_markdown(metrics, y_val)
    
    # Log metrics to MLflow
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(tracking_uri)
    
    with mlflow.start_run(run_id=run_id):
        mlflow.log_metric("val_mae", metrics["mae"])
        mlflow.log_metric("val_r2", metrics["r2"])
        mlflow.log_metric("val_mse", metrics["mse"])
    
    context.add_output_metadata({
        "val_mae": metrics["mae"],
        "val_r2": metrics["r2"],
        "val_mse": metrics["mse"],
        "preview": MetadataValue.md(preview_md)
    })
    
    return metrics


defs = Definitions(
    assets=[
        sync_biomass_data, 
        train_val_split, 
        xgboost_train_features, 
        xgboost_val_features,
        xgboost_model, 
        xgboost_mlflow_logged_model,
        xgboost_evaluation
    ],
    resources={"io_manager": FilesystemIOManager(base_dir="/dagster_outputs")}
)
