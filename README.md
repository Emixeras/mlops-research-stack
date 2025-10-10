# Plant Biomass Prediction MLOps Project

This repository contains the design and implementation of a modern MLOps architecture for plant biomass prediction using machine learning and DVC for data versioning.


## Local services (Docker Compose)

This repo includes a root-level `docker-compose.yml` to run Postgres (for MLflow), MLflow UI, and the Dagster webserver with hot reload.

Services
- `db`: Postgres 15 (metadata for MLflow), data persisted in named volume `pg_data`
- `mlflow`: MLflow server (http://localhost:5000), artifacts in named volume `mlflow_artifacts` and served via `--serve-artifacts`
- `dagster`: Dagster webserver (http://localhost:3000), running `dagster dev` with code hot-reloaded from `mlops-system-dagster/src`

Run
```powershell
# Build images
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
