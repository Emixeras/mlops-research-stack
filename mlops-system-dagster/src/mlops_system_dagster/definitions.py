from dagster import (
    Definitions,
    FilesystemIOManager,
    load_assets_from_modules,
    define_asset_job,
    in_process_executor,
)

from .defs import assets, monitoring_assets


all_assets = load_assets_from_modules([assets, monitoring_assets])

# Job for drift monitoring with in-process executor (Evidently doesn't work well with multiprocess)
drift_monitoring_job = define_asset_job(
    name="drift_monitoring",
    selection=["drift_report"],
    executor_def=in_process_executor,
)

defs = Definitions(
    assets=all_assets,
    jobs=[drift_monitoring_job],
    resources={
        # Use our new custom IO Manager
        "io_manager": FilesystemIOManager(base_dir="/dagster_outputs"),
    },
)