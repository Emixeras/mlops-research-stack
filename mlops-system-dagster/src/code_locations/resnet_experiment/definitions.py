from dagster import asset, Definitions, AssetIn, SourceAsset, AssetKey, FilesystemIOManager, MetadataValue, Config
import pandas as pd
import os
from pathlib import Path
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
import mlflow
import mlflow.pyfunc

from .model import build_resnet_regressor, ResNetBiomassModel
from .dataset import BiomassImageDataset, get_transforms

# Define assets from the base pipeline that we depend on
sync_biomass_data = SourceAsset(key=AssetKey("sync_biomass_data"))
train_val_split = SourceAsset(key=AssetKey("train_val_split"))

class ResNetConfig(Config):
    resnet_type: str = "resnet18"
    pretrained: bool = True
    freeze_layers: bool = True
    num_epochs: int = 15
    learning_rate: float = 1e-3
    batch_size: int = 64

@asset(group_name="resnet_experiment", ins={"train_val_split": AssetIn("train_val_split"), "sync_biomass_data": AssetIn("sync_biomass_data")})
def resnet_image_datasets(context, train_val_split: dict, sync_biomass_data: dict):
    """
    Creates PyTorch Datasets for training and validation.
    """
    data_dir = Path(sync_biomass_data["data_dir"])
    images_dir = data_dir / "images" / "train"
    target_col = "fresh_weight_total"
    img_size = 224
    
    train_df = train_val_split["train_df"]
    val_df = train_val_split["val_df"]
    
    transform = get_transforms(img_size)
    
    train_dataset = BiomassImageDataset(train_df, str(images_dir), target_col, transform=transform)
    val_dataset = BiomassImageDataset(val_df, str(images_dir), target_col, transform=transform)
    
    context.add_output_metadata({
        "train_dataset_len": len(train_dataset),
        "val_dataset_len": len(val_dataset),
        "image_size": f"{img_size}x{img_size}"
    })
    
    return {"train_dataset": train_dataset, "val_dataset": val_dataset}

@asset(group_name="resnet_experiment", ins={"resnet_image_datasets": AssetIn("resnet_image_datasets")})
def resnet_model(context, resnet_image_datasets: dict, config: ResNetConfig):
    """
    Trains a ResNet regressor using the prepared datasets.
    """
    # Configuration
    resnet_type = config.resnet_type
    pretrained = config.pretrained
    freeze_layers = config.freeze_layers
    num_epochs = config.num_epochs
    learning_rate = config.learning_rate
    batch_size = config.batch_size
    
    train_dataset = resnet_image_datasets["train_dataset"]
    val_dataset = resnet_image_datasets["val_dataset"]
    
    # Loaders - optimized for GPU training
    train_loader = DataLoader(
        train_dataset, 
        batch_size=batch_size, 
        shuffle=True,
        num_workers=2,          # Reduced to avoid blocking Dagster heartbeat
        pin_memory=True,        # Fast CPU->GPU transfer
        persistent_workers=False # Avoid holding resources between epochs
    )
    val_loader = DataLoader(
        val_dataset, 
        batch_size=batch_size, 
        shuffle=False,
        num_workers=2,          # Reduced for validation
        pin_memory=True
    )
    
    # Model
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    context.log.info(f"Training on device: {device}")
    
    model = build_resnet_regressor(resnet_type, pretrained, freeze_layers)
    model = model.to(device)
    
    criterion = nn.MSELoss()
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=learning_rate)
    
    # Training Loop
    best_val_loss = float('inf')
    best_model_state = None
    
    for epoch in range(num_epochs):
        model.train()
        batch_losses = []
        for images, targets in train_loader:
            images = images.to(device)
            targets = targets.to(device).unsqueeze(1)
            
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()
            batch_losses.append(loss.item())
            
        epoch_loss = sum(batch_losses) / len(batch_losses) if batch_losses else 0
        
        # Validation
        model.eval()
        val_batch_losses = []
        with torch.no_grad():
            for images, targets in val_loader:
                images = images.to(device)
                targets = targets.to(device).unsqueeze(1)
                outputs = model(images)
                loss = criterion(outputs, targets)
                val_batch_losses.append(loss.item())
        
        val_loss = sum(val_batch_losses) / len(val_batch_losses) if val_batch_losses else 0
        
        context.log.info(f"Epoch {epoch+1}/{num_epochs} - Train Loss: {epoch_loss:.4f} - Val Loss: {val_loss:.4f}")
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            # Ensure state dict is on CPU to avoid deserialization issues in CPU-only environments
            best_model_state = {k: v.cpu() for k, v in model.state_dict().items()}
            
    # Load the best weights into the model and move to CPU
    model.load_state_dict(best_model_state)
    model.cpu()

    # Return the best model state
    context.add_output_metadata({
        "best_val_loss": float(best_val_loss),
        "epochs_trained": num_epochs,
        "device": str(device)
    })
    
    # Prepare metadata for the generic logger
    params = {
        "epochs": num_epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "best_val_loss": best_val_loss,
        "resnet_type": resnet_type,
        "pretrained": pretrained,
        "freeze_layers": freeze_layers,
    }
    
    src_dir = Path(__file__).parent.parent.parent
    
    return {
        "model": model,
        "params": params,
    }

@asset(group_name="resnet_experiment", ins={"trained_model": AssetIn("resnet_model"), "sync_biomass_data": AssetIn("sync_biomass_data")})
def resnet_mlflow_logged_model(context, trained_model: dict, sync_biomass_data: dict):
    """
    Logs the trained ResNet model to MLflow.
    """
    # Hardcoded constants
    model_type = "ResNet18"
    experiment_name = "resnet"
    run_name = "biomass_resnet"
    src_dir = Path(__file__).parent.parent.parent
    code_paths = [
        str(src_dir / "code_locations"),
        str(src_dir / "mlops_system_dagster")
    ]
    pip_requirements = ["torch", "torchvision", "pillow", "pandas", "numpy"]

    # Extract version information
    git_commit = sync_biomass_data.get("git_commit")
    git_branch = sync_biomass_data.get("git_branch")
    git_repo_url = sync_biomass_data.get("git_repo_url")
    dvc_data_hash = sync_biomass_data.get("dvc_data_hash")
    
    # Extract model info
    model = trained_model["model"]
    params = trained_model.get("params", {})
    
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    
    # Instantiate the wrapper directly
    pyfunc_model = ResNetBiomassModel(model)
    
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

@asset(group_name="resnet_experiment", ins={"train_val_split": AssetIn("train_val_split"), "mlflow_logged_model": AssetIn("resnet_mlflow_logged_model"), "sync_biomass_data": AssetIn("sync_biomass_data")})
def resnet_evaluation(context, train_val_split: dict, mlflow_logged_model: dict, sync_biomass_data: dict):
    """
    Evaluates the ResNet model using the PyFunc wrapper.
    """
    from mlops_system_dagster.core_utils.evaluation import calculate_regression_metrics, preview_markdown
    import numpy as np
    
    run_id = mlflow_logged_model["run_id"]
    pyfunc_model = mlflow_logged_model["pyfunc_model"]
    
    val_df = train_val_split["val_df"].copy()
    y_val = val_df["fresh_weight_total"].values
    
    # Construct paths for prediction
    data_dir = Path(sync_biomass_data["data_dir"])
    images_dir = data_dir / "images" / "train"
    
    if 'filename' not in val_df.columns and 'sample_id' in val_df.columns:
        val_df['filename'] = val_df['sample_id'].astype(str) + ".png"
        
    val_df['path'] = val_df['filename'].apply(lambda x: str(images_dir / x))

    # Predict using the pyfunc wrapper
    # Pass list of paths instead of DataFrame to match the simple model pattern
    paths = val_df['path'].tolist()
    preds = pyfunc_model.predict(None, paths)
    preds = np.array(preds, dtype=float).flatten()
    
    # Ensure y_val is also flattened and of the same type
    y_val = np.array(y_val, dtype=float).flatten()
    
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
    assets=[sync_biomass_data, train_val_split, resnet_image_datasets, resnet_model, resnet_mlflow_logged_model, resnet_evaluation],
    resources={
        "io_manager": FilesystemIOManager(base_dir="/dagster_outputs"),
    }
)
