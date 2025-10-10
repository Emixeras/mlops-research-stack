# MLflow server with PostgreSQL and local artifacts (Docker volumes)

## Stack
- Database: Postgres 15 (service: `db`) stored in named volume `pg_data`
- MLflow UI: http://localhost:5000 (service: `mlflow`)
- Artifacts: stored in named volume `mlflow_artifacts`, mounted at `/mlflow-artifacts` in the mlflow container, served via `--serve-artifacts`

## Usage
```powershell
# Build images
docker compose build

# Start services
docker compose up -d

# Follow logs
docker compose logs -f mlflow

# Stop and remove containers (volumes are preserved unless you add -v)
docker compose down
```

## Details
- Backend store URI: `postgresql://mlflow:mlflow_password@db:5432/mlflow`
- Artifact root: `file:///mlflow-artifacts`
- Postgres is not exposed to the host, avoiding port conflicts

## Inspect the artifacts volume
```powershell
# List top-level contents in the artifacts volume using a throwaway container
$vol = "mlflow_artifacts"
# The full volume name may be prefixed by the Compose project; list volumes to confirm
# docker volume ls

docker run --rm -it -v ${vol}:/data alpine ls -R /data
```