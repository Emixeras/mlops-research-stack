import dagster as dg
from dagster import Config
from pydantic import model_validator

class TrainValSplitConfig(Config):
    """Validated split configuration using dagster.Config."""

    val_size: float = 0.2

    @model_validator(mode="after")
    def check_val_size_range(self) -> "TrainValSplitConfig":
        if not (0.0 < self.val_size < 1.0):
            raise ValueError(f"val_size must be between 0 and 1, but got {self.val_size}")
        return self

    @property
    def test_size(self) -> float:
        return self.val_size

@dg.definitions
def resources() -> dg.Definitions:
    return dg.Definitions(resources={"config": TrainValSplitConfig()})
