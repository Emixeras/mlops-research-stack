import os
from pathlib import Path

from mlops_system_dagster.defs.resources import TrainValSplitConfig
import pandas as pd
from dagster import asset, MetadataValue, AssetKey, Definitions, FilesystemIOManager, AssetIn
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
from mlops_system_dagster.core_utils.training import train_linear_regression
from mlops_system_dagster.core_utils.models import LinearRegressionBiomassModel
from mlops_system_dagster.core_utils.evaluation import calculate_regression_metrics, preview_markdown
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
def train_val_split(context, train_table: pd.DataFrame, config: TrainValSplitConfig) -> dict:
    """Splits the training table into train and validation sets based on config."""
    test_size = config.test_size
    
    train_df, val_df = train_test_split(
        train_table,
        test_size=test_size,
        random_state=42,
    )

    context.add_output_metadata(
        {
            "preview": MetadataValue.md(
                f"### Train/Val Split\n- train_samples: `{len(train_df)}`\n"
                f"- val_samples: `{len(val_df)}`\n- test_size: `{test_size}`"
            )
        }
    )
    return {
        "train_df": train_df,
        "val_df": val_df,
    }



defs = Definitions(
    assets=[
        sync_biomass_data,
        train_table,
        test_table,
        train_val_split,
    ],
    resources={
        "io_manager": FilesystemIOManager(base_dir="mlops-system-dagster/dagster_outputs"),
    },
)



