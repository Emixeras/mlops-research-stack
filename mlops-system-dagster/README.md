# mlops_system_dagster

Dagster orchestration system for plant biomass prediction pipelines.

## Architecture

The system uses **code locations** for namespace isolation, enabling parallel development:

| Code Location | Purpose |
|---------------|---------|
| `core_data_ingestion` | Shared base pipeline: DVC sync, train/val split, drift monitoring |
| `linear_regression_experiment` | Linear regression model training and evaluation |
| `xgboost_experiment` | XGBoost gradient boosting model |
| `resnet_experiment` | PyTorch ResNet CNN for image-based prediction |

Code locations are configured in `workspace.yaml`. Experiments import shared assets via `AssetIn`.

## Getting started

### Installing dependencies

**Option 1: uv**

Ensure [`uv`](https://docs.astral.sh/uv/) is installed following their [official documentation](https://docs.astral.sh/uv/getting-started/installation/).

Create a virtual environment, and install the required dependencies using _sync_:

```bash
uv sync
```

Then, activate the virtual environment:

| OS | Command |
| --- | --- |
| MacOS | ```source .venv/bin/activate``` |
| Windows | ```.venv\Scripts\activate``` |

**Option 2: pip**

Install the python dependencies with [pip](https://pypi.org/project/pip/):

```bash
python3 -m venv .venv
```

Then activate the virtual environment:

| OS | Command |
| --- | --- |
| MacOS | ```source .venv/bin/activate``` |
| Windows | ```.venv\Scripts\activate``` |

Install the required dependencies:

```bash
pip install -e ".[dev]"
```

### Running Dagster

Start the Dagster UI web server:

```bash
dg dev
```

Open http://localhost:3000 in your browser to see the project.

## Adding a New Experiment

1. Create a new code location in `src/code_locations/your_experiment/`
2. Define assets that import from `core_data_ingestion` using `AssetIn`
3. Add the code location to `workspace.yaml`
4. Restart Dagster to load the new location

Example asset importing shared data:
```python
from dagster import asset, AssetIn

@asset(ins={"train_val_split": AssetIn(key="train_val_split")})
def your_model(train_val_split):
    X_train, X_val, y_train, y_val = train_val_split
    # Your model training logic
    return model
```

## Debugging

**Local debugging:**
1. Keep dependencies running: `docker compose up -d db mlflow`
2. Stop Dagster container: `docker compose stop dagster`
3. Go to Run and Debug → Select "Dagster Local"
4. Set breakpoints and trigger materializations at http://localhost:3000
5. When done: `docker compose up -d` to restart all services
