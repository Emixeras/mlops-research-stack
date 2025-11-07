from dagster import (
    Definitions,
    FilesystemIOManager,
    load_assets_from_modules,
)

from .defs import assets


all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
    resources={
        # Use our new custom IO Manager
        "io_manager": FilesystemIOManager(base_dir="mlops-system-dagster/dagster_outputs"),
    },
)