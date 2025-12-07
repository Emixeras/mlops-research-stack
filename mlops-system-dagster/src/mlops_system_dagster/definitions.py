from dagster import (
    Definitions,
    FilesystemIOManager,
    load_assets_from_modules,
    in_process_executor,
)

from .defs import assets, monitoring_assets


all_assets = load_assets_from_modules([assets, monitoring_assets])

defs = Definitions(
    assets=all_assets,
    resources={
        # Use our new custom IO Manager
        "io_manager": FilesystemIOManager(base_dir="/dagster_outputs"),
    },
)