# MLOps Research Stack

> This project was developed as part of a research project at TH Köln in the [AI4Science Group](https://www.ai4science.group/).

A modular, self-hosted MLOps stack for collaborative research, featuring pipeline orchestration with Dagster, experiment tracking with MLflow, data versioning with DVC, and model deployment with Gradio. While the current use case is **plant biomass prediction**, the architecture is domain-agnostic and can serve as a template for any research ML project.

> **📺 Video Tutorial:** A comprehensive walkthrough is available at [YouTube](https://www.youtube.com/watch?v=_aYcRDScQdc) (German, 36 min).

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- SSH access to the server (for DVC data)
- (Optional) NVIDIA GPU + Container Toolkit for deep learning models

### Local Development

1. **Configure DVC** (one-time setup):
   ```bash
   dvc remote modify ssh_remote user YOUR_USERNAME --local
   dvc pull
   ```

2. **Start all services**:
   ```powershell
   docker compose up --build
   ```

3. **Access services** (requires adding entries to hosts file or using browser that resolves `.localhost`):
   - MLflow: http://mlflow.localhost:8000
   - Dagster: http://dagster.localhost:8000
   - Gradio: http://gradio.localhost:8000
   - Traefik Dashboard: http://localhost:8080

### Server Deployment (Fresh)

1. **Run the setup script** (requires root, Docker, Git):
   ```bash
   sudo bash setup-scripts/setup-new-deployment.sh <hostname> <admin-user> <git-user> <git-pat>
   ```
   This creates the filesystem layout, clones the repo, configures DVC, and starts Docker Compose.

2. **Create Traefik auth file** (if `htpasswd` was not available during setup):
   ```bash
   apt install apache2-utils
   htpasswd -c /home/shared/mlops/2025_msc_felix_hagenbrock/traefik-users.txt admin
   ```

3. **Populate training data** (the script creates empty directories — data must be added manually):
   - **Option A** — Pull from DVC SSH remote (requires SSH access to the source server):
     ```bash
     cd /home/shared/mlops/2025_msc_felix_hagenbrock && dvc pull
     ```
   - **Option B** — Copy directly from an existing server:
     ```bash
     rsync -a user@old-server:/home/shared/mlops/data/ /home/shared/mlops/data/
     rsync -a user@old-server:/home/shared/mlops/dvc-storage-biomass/ /home/shared/mlops/dvc-storage-biomass/
     ```
   - **Option C** — Pull via Dagster after startup (fetches from DVC remote configured in `.dvc/config.local`):
     Materialize the `sync_biomass_data` asset in the Dagster UI.

> `system-state/` (Postgres, MLflow artifacts, Dagster home) is generated at runtime and does not need to be seeded on a fresh deployment. For migrating an existing server, see [setup-scripts/SERVER_MIGRATION.md](setup-scripts/SERVER_MIGRATION.md).

---

## Project Structure

```
.
├── data/biomass/                      # Training/test CSVs and images (DVC-tracked)
├── data.dvc                           # DVC tracking file
├── docker-compose.yml                 # Local development
├── docker-compose_server.yml          # Server deployment
├── traefik-users.txt                  # Basic auth credentials (not committed)
│
├── mlops-system-dagster/              # Dagster orchestration system
│   ├── workspace.yaml                 # Code locations configuration
│   └── src/
│       ├── mlops_system_dagster/      # Core data ingestion pipeline
│       │   ├── core_utils/            # Shared utilities (preprocessing, evaluation)
│       │   └── defs/
│       │       ├── assets.py          # Core assets (sync_biomass_data, train_val_split)
│       │       └── monitoring_assets.py  # Data drift detection (Evidently AI)
│       └── code_locations/            # Experiment-specific pipelines
│           ├── linear_regression/     # Linear regression experiment
│           ├── xgboost_experiment/    # XGBoost experiment
│           └── resnet_experiment/     # ResNet CNN experiment (PyTorch)
│
├── model-deployment/                  # Gradio inference application
├── mlflow-server/                     # MLflow server Docker setup
├── deployment/landing/                # Static landing page
├── setup-scripts/                     # Server setup & migration
│   ├── setup-new-deployment.sh        # Fresh server deployment (automated)
│   ├── setup-permissions.sh           # Restore filesystem permissions
│   └── SERVER_MIGRATION.md            # Migration from existing server
├── auth-scripts/                      # Authentication utilities (htpasswd generation)
└── production_inference/              # Logged inference requests
```

---

## Architecture Overview

### Code Locations

The system uses Dagster's code locations for namespace isolation, enabling parallel development:

| Code Location | Purpose |
|---------------|---------|
| `core_data_ingestion` | Shared base pipeline: DVC sync, train/val split, drift monitoring |
| `linear_regression_experiment` | Linear regression model training and evaluation |
| `xgboost_experiment` | XGBoost gradient boosting model |
| `resnet_experiment` | PyTorch ResNet CNN for image-based prediction |

Experiments import shared assets (e.g., `train_val_split`) via `AssetIn`, avoiding code duplication.

### Key Features

- **Data Versioning (DVC)**: Dataset versions linked to Git commits for reproducibility
- **Experiment Tracking (MLflow)**: Metrics, parameters, and artifacts logged automatically
- **Model Registry**: Centralized model versioning with staging/production aliases
- **Data Drift Monitoring**: Evidently AI compares training vs. production feature distributions
- **Preprocessing Consistency**: PyFunc wrappers embed preprocessing into MLflow models

---

## Local Services (Docker Compose)

| Service | URL | Description |
|---------|-----|-------------|
| `traefik` | http://localhost:8080 | Reverse proxy dashboard |
| `mlflow` | http://mlflow.localhost:8000 | Experiment tracking & model registry |
| `dagster` | http://dagster.localhost:8000 | Pipeline orchestration (hot reload enabled) |
| `model-deployment` | http://gradio.localhost:8000 | Gradio inference interface |
| `db` | (internal) | PostgreSQL for MLflow metadata |

**Volumes**: `pg_data`, `mlflow_artifacts`, `dagster_home`, `dvc_cache`

**Authentication**: Basic auth via `traefik-users.txt`. Generate credentials:
```bash
python auth-scripts/gen_htpasswd.py USERNAME
```

---

## Server Deployment

When deployed with `docker-compose_server.yml` on `luke.nt.fh-koeln.de`:

| Service | URL |
|---------|-----|
| Landing Page | http://luke.nt.fh-koeln.de:8090/welcome |
| MLflow | http://luke.nt.fh-koeln.de:8090/ |
| Dagster | http://luke.nt.fh-koeln.de:8090/dagster |
| Gradio | http://luke.nt.fh-koeln.de:8090/gradio |
| Traefik Dashboard | http://luke.nt.fh-koeln.de:8091 |

**Server paths**:
- Repository: `/home/shared/mlops/2025_msc_felix_hagenbrock`
- DVC Storage: `/home/shared/mlops/dvc-storage-biomass`
- System State: `/home/shared/mlops/system-state/`

**Fresh deployment** (new server, no existing data):
```bash
sudo bash setup-scripts/setup-new-deployment.sh luke.nt.fh-koeln.de <admin-user> <git-user> <git-pat>
```
This creates the required directory layout, sets permissions, clones the repo, configures DVC, generates `traefik-users.txt`, and starts all services.

**Start server** (existing installation):
```bash
cd /home/shared/mlops/2025_msc_felix_hagenbrock
docker compose -f docker-compose_server.yml up -d --build
```

For migration procedures (moving from an existing server), see [setup-scripts/SERVER_MIGRATION.md](setup-scripts/SERVER_MIGRATION.md).

---

## DVC Setup & Usage

### Remote Storage

DVC remote is configured as SSH storage on `luke.nt.fh-koeln.de`:

```ini
# .dvc/config
[core]
    remote = ssh_remote
['remote "ssh_remote"']
    url = ssh://luke.nt.fh-koeln.de/home/shared/mlops/dvc-storage-biomass
```

### Pulling the Dataset

1. **Configure your SSH username** (one-time):
   ```bash
   dvc remote modify ssh_remote user YOUR_USERNAME --local
   ```

2. **Pull the dataset**:
   ```bash
   dvc pull
   ```

### Updating the Dataset

1. Modify files in `data/`
2. Track and push changes:
   ```bash
   dvc add data
   dvc push
   ```
3. **Commit with a descriptive message**:
   ```bash
   git add data.dvc
   git commit -m "Added 20 new training images"
   git push
   ```

### Previous Dataset Versions

```bash
git checkout <commit_hash>
dvc pull
```

---

## Debugging

VS Code launch configurations are provided in `.vscode/launch.json`.

### Dagster Pipelines

1. Keep dependencies running: `docker compose up -d db mlflow`
2. Stop Dagster container: `docker compose stop dagster`
3. Run "Dagster Local" debug configuration in VS Code
4. Set breakpoints in asset functions and trigger materializations

### Gradio Deployment

1. Set `DEBUG=1` in `docker-compose.yml` for `model-deployment`
2. Start containers and wait for "🐛 Waiting for debugger..."
3. Run "Debug Gradio" configuration to attach

See [mlops-system-dagster/README.md](mlops-system-dagster/README.md) and [model-deployment/README.md](model-deployment/README.md) for details.

---

## Documentation

| Document | Description |
|----------|-------------|
| [mlops-system-dagster/README.md](mlops-system-dagster/README.md) | Dagster setup, debugging, adding experiments |
| [model-deployment/README.md](model-deployment/README.md) | Gradio app configuration and debugging |
| [setup-scripts/setup-new-deployment.sh](setup-scripts/setup-new-deployment.sh) | Automated fresh server deployment |
| [setup-scripts/SERVER_MIGRATION.md](setup-scripts/SERVER_MIGRATION.md) | Migration from an existing server |
| [auth-scripts/README.md](auth-scripts/README.md) | Authentication utilities (htpasswd generation) |
| [presentation/VIDEO_SCRIPT.md](presentation/VIDEO_SCRIPT.md) | Video tutorial script |

