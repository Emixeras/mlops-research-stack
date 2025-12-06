# Server Migration Guide

Quick guide to migrate the MLOps system to a new server.

## Phase 1: OLD Server (Pack & Export)

1. **Stop Docker:**
   ```bash
   cd /home/shared/mlops/2025_msc_felix_hagenbrock
   docker compose -f docker-compose_server.yml down
   ```

2. **Create Archive (excludes git repo):**
   ```bash
   cd /home/shared/mlops
   sudo tar -czvf mlops_migration.tar.gz --exclude='2025_msc_felix_hagenbrock' .
   ```

3. **Transfer to New Server:**
   ```bash
   # From local machine or directly between servers
   scp user@old-server:/home/shared/mlops/mlops_migration.tar.gz .
   scp mlops_migration.tar.gz user@new-server:/tmp/
   ```

## Phase 2: NEW Server (Unpack & Setup)

1. **Create Base Directory:**
   ```bash
   sudo mkdir -p /home/shared/mlops
   ```

2. **Extract Archive:**
   ```bash
   sudo tar -xzvf /tmp/mlops_migration.tar.gz -C /home/shared/mlops
   ```

3. **Clone Repository:**
   ```bash
   cd /home/shared/mlops
   sudo git clone https://git-ce.rwth-aachen.de/ai4science/plant_biomass/2025_msc_felix_hagenbrock.git
   ```

4. **Create mlops Group:**
   ```bash
   sudo groupadd mlops
   sudo usermod -aG mlops $USER
   ```

5. **Restore Permissions:**
   ```bash
   cd /home/shared/mlops/2025_msc_felix_hagenbrock/setup-scripts
   chmod +x setup-permissions.sh
   ./setup-permissions.sh
   ```

6. **Start System:**
   ```bash
   cd /home/shared/mlops/2025_msc_felix_hagenbrock
   docker compose -f docker-compose_server.yml up -d --build
   ```

## What Gets Migrated

- ✅ `data/` - Training/test datasets
- ✅ `dvc-storage-biomass/` - DVC remote storage
- ✅ `production_inference/` - Production logs
- ✅ `system-state/` - MLflow artifacts, Dagster state, Postgres DB, DVC cache
- ❌ `2025_msc_felix_hagenbrock/` - Git repo (clone fresh)

## Notes

- Use `tar` to preserve permissions (don't use `cp -r`)
- The `setup-permissions.sh` script handles all ownership/permission restoration
- Postgres data owned by UID 999, DVC storage by group `mlops`
