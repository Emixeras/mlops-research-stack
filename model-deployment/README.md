# Model Deployment

Gradio web UI for serving registered MLflow biomass prediction models.

## Quick Start

### Docker Compose (recommended)
```powershell
# From repo root
docker compose up -d model-deployment
```
Open http://localhost:7860

### Local (uv)
```powershell
uv sync
uv run python app.py
```

## Usage

1. Select a registered model from the dropdown (click **Refresh** to reload)
2. Upload one or more biomass images
3. Click **Predict**

## Requirements

- MLflow tracking server at `MLFLOW_TRACKING_URI` (default: http://localhost:5000)
- At least one registered model in the Model Registry

## Environment Variables

| Variable | Default |
|----------|---------|
| `MLFLOW_TRACKING_URI` | `http://localhost:5000` |
| `GRADIO_SERVER_NAME` | `0.0.0.0` (in Docker) |
| `GRADIO_SERVER_PORT` | `7860` |
