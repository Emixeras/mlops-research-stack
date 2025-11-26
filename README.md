# Plant Biomass Prediction MLOps Project

This repository contains the design and implementation of a modern MLOps architecture for plant biomass prediction using machine learning and DVC for data versioning.


## Local services (Docker Compose)

This repo includes a root-level `docker-compose.yml` to run Postgres (for MLflow), MLflow UI, and the Dagster webserver with hot reload.

Services
- `traefik`: Reverse proxy (http://localhost:8000), dashboard at http://localhost:8080
- `db`: Postgres 15 (metadata for MLflow), data persisted in named volume `pg_data`
- `mlflow`: MLflow server (http://localhost:5000), artifacts in named volume `mlflow_artifacts` and served via `--serve-artifacts`
- `dagster`: Dagster webserver (http://localhost:3000), running `dagster dev` with code hot-reloaded from `mlops-system-dagster/src`
- `model-deployment`: Gradio app (http://localhost:7860), serving the model

Run
```powershell
# Build and start services
docker compose up --build
```

## Project Structure

- `data/biomass/` — Contains training and test CSVs and images
- `data.dvc` — DVC tracking file for the dataset
- `README.md` — Project documentation

## DVC Setup & Usage

### Remote Storage

Notes
- The `mlops-system-dagster` project is bind-mounted into the `dagster` container for live editing.
- MLflow tracking URI inside the `dagster` container is `http://mlflow:5000`.
- Postgres is internal-only (no host port exposed) to avoid conflicts.

DVC remote storage is implemented as an SSH server in the folder of `fhagenbr` on the MLflow server `mlflow.nt.fh-koeln.de`, as specified in `/.dvc/config`.

**Access Requirements:**
- SSH access to the server
- Read permissions for the folder: `mlflow.nt.fh-koeln.de/home/fhagenbr/dvc-storage-biomass`

### Pulling the Current Dataset

1. **Install DVC:**
	```sh
	e.g. with pip install dvc
	```
2. **Configure SSH user:**
	```sh
	dvc remote modify ssh_remote user <your_user> --local
	```
3. **Pull the dataset:**
	```sh
	dvc pull
	```
	This pulls the dataset associated with the hash in `data.dvc`. To pull a previous version, checkout the specific git commit (so `data.dvc` points to that version).

### Changing the Dataset & Pushing Changes

1. Add, delete, or modify files in the `data/` folder.
2. Track changes with DVC:
	```sh
	dvc add data
	dvc push
	```
3. **Commit the changes in git with a clear message!**
	```sh
	git add data.dvc
	git commit -m "Added 20 images to the training set"
	git push
	```

	> ⚠️ **Important:** Always use a clear and descriptive commit message when updating the dataset. This makes it easy for users to identify and revert to previous versions if needed.

	> **Note:** This updates the hash in `data.dvc` to point to the new dataset version. Users can revert to previous datasets by checking out earlier commits.

### Pulling a Previous Dataset Version

1. Checkout the desired commit:
	```sh
	git checkout <commit_hash>
	```
2. Pull the dataset:
	```sh
	dvc pull
	```

---

## Service Paths (Server deployment)

When deployed with `docker-compose_server.yml` on the server `mlflow.nt.fh-koeln.de`, services are available at these paths and ports:

- **Traefik (HTTP gateway)**: `http://mlflow.nt.fh-koeln.de:8090/` — root path proxies to MLflow.
- **Traefik Dashboard**: `http://mlflow.nt.fh-koeln.de:8091/` — Traefik dashboard (useful to inspect routers and services).
- **MLflow UI**: `http://mlflow.nt.fh-koeln.de:8090/` — MLflow served at `/` behind Traefik. Basic auth is enabled.
- **Dagster UI**: `http://mlflow.nt.fh-koeln.de:8090/dagster` — routed with PathPrefix `/dagster`; the prefix is stripped before forwarding to the Dagster process.
- **Gradio App**: `http://mlflow.nt.fh-koeln.de:8090/gradio` — routed with PathPrefix `/gradio`; Gradio is configured with `GRADIO_ROOT_PATH=/gradio`.

Notes:
- Basic auth is enabled for MLflow, Dagster and Gradio. Credentials are read from the file `/traefik-users.txt` inside the Traefik container.
- If you run the local `docker-compose.yml` for development, use the local hostnames and ports defined there (e.g. `mlflow.localhost` on port `8000`).

**Landing Page**
- **Path**: `http://mlflow.nt.fh-koeln.de:8090/welcome` — a small static landing page that links to MLflow (`/`), Dagster (`/dagster`) and Gradio (`/gradio`).
- **Source**: the HTML is stored in `deployment/landing/index.html` in this repository.
- **Service**: served by the `landing` nginx service in `docker-compose_server.yml` and routed by Traefik using PathPrefix `/welcome`.
- **How to start (server)**: start Traefik and the landing service only:

```powershell
docker compose -f docker-compose_server.yml up -d traefik landing
```

- **Notes**:
	- Traefik applies a `stripPrefix` middleware so the upstream nginx receives requests without the `/welcome` prefix and serves the page correctly.
	- Ensure the host path `\`/home/shared/mlops/2025_msc_felix_hagenbrock/deployment/landing\` exists and is readable by Docker on the server host.
	- If you prefer the landing page at the root (`/`) instead of MLflow, rework the Traefik router rules and consider moving MLflow to a subpath (this will require updating `MLFLOW_SERVER_ALLOWED_HOSTS` and adjusting MLflow/Traefik labels).

