from dagster import asset, AssetIn, SourceAsset, AssetKey, MetadataValue
from pathlib import Path
import pandas as pd
import numpy as np
from mlops_system_dagster.core_utils.preprocessing import load_and_flatten, extract_train_features
from evidently import Report
from evidently.presets import DataDriftPreset

@asset(ins={
    "train_val_split": AssetIn("train_val_split"),
    "sync_biomass_data": AssetIn("sync_biomass_data")
})
def reference_features(context, train_val_split: dict, sync_biomass_data: dict):
    """Computes unscaled reference features (raw pixel stats) from training data."""
    train_df = train_val_split["train_df"]
    data_dir = Path(sync_biomass_data["data_dir"])
    images_dir = data_dir / "images" / "train"
    
    # We use a row limit to keep the reference set manageable for reporting
    row_limit = 500
    features = []
    
    # Manual extraction loop to avoid using the Linear Regression scaler logic
    for _, row in train_df.head(row_limit).iterrows():
        img_path = images_dir / row.get("filename", "")
        # load_and_flatten returns raw pixel array (resized to 64x64 grayscale by default)
        arr = load_and_flatten(img_path)
        if arr is not None:
            features.append(arr)
            
    if not features:
        raise ValueError("No reference features could be extracted.")

    X_ref = pd.DataFrame(features)
    
    context.add_output_metadata({
        "n_samples": len(X_ref),
        "n_features": X_ref.shape[1] if len(X_ref) > 0 else 0,
        "note": "Unscaled raw pixel features (64x64 flattened)"
    })
    
    return X_ref

@asset(ins={"reference_features": AssetIn("reference_features")})
def production_features(context, reference_features: pd.DataFrame):
    """Loads production logs and computes unscaled features for drift detection."""
    log_file = Path("/workspace/production_inference/inference_log.csv")
    
    if not log_file.exists():
        raise FileNotFoundError(f"No production inference log found at {log_file}.")
    
    log_df = pd.read_csv(log_file)
    
    if log_df.empty:
        raise ValueError("Production log is empty.")
    
    features = []
    valid_indices = []
    for idx, path in enumerate(log_df["filepath"]):
        # Load raw image data exactly like the reference set
        arr = load_and_flatten(Path(path))
        if arr is not None:
            features.append(arr)
            valid_indices.append(idx)
        else:
            context.log.warning(f"Could not load image at {path}")
    
    if not features:
        raise ValueError("No valid images found in production logs.")

    X_prod = pd.DataFrame(features)
    
    # Filter log_df to match valid features
    log_df_valid = log_df.iloc[valid_indices].reset_index(drop=True)
    
    # Attach metadata columns for the report (Evidently can use these for plotting)
    X_prod["prediction"] = log_df_valid["prediction"].values
    X_prod["timestamp"] = log_df_valid["timestamp"].values
    
    context.add_output_metadata({
        "n_samples": len(X_prod),
        "date_range": f"{log_df_valid['timestamp'].min()} to {log_df_valid['timestamp'].max()}"
    })
    
    return X_prod

@asset(ins={
    "reference_features": AssetIn("reference_features"), 
    "production_features": AssetIn("production_features")
})
def drift_report(context, reference_features: pd.DataFrame, production_features: pd.DataFrame):
    """Generates an HTML drift report comparing Train (Reference) vs Production (Current)."""
    
    if production_features is None or production_features.empty:
        raise ValueError("No production data available.")
    
    if reference_features is None or reference_features.empty:
        raise ValueError("No reference data available.")
        
    # Current data (Production) - Drop metadata columns for the drift calculation
    current_data = production_features.drop(columns=["prediction", "timestamp"], errors="ignore")
    
    if current_data.empty or len(current_data.columns) == 0:
        raise ValueError(f"No feature columns remain after dropping metadata. Production shape: {production_features.shape}")
    
    # Ensure column names are strings (Evidently requirement)
    reference_features.columns = reference_features.columns.astype(str)
    current_data.columns = current_data.columns.astype(str)
    
    # Convert to float for Evidently compatibility
    reference_sample = reference_features.astype(float)
    current_sample = current_data.astype(float)
    
    context.log.info(f"Running drift detection on {len(reference_sample.columns)} columns")
    
    # Run Evidently Report
    report = Report([
        DataDriftPreset(),
    ])
    
    snapshot = report.run(reference_sample, current_sample)
    
    # Save HTML Report
    output_path = Path("/dagster_outputs/drift_report.html")
    output_path.parent.mkdir(exist_ok=True, parents=True)
    snapshot.save_html(str(output_path))
    
    context.add_output_metadata({
        "report_path": MetadataValue.path(str(output_path)),
        "n_reference": len(reference_features),
        "n_current": len(current_data),
        "n_features_analyzed": len(reference_features.columns)
    })
    
    return str(output_path)
