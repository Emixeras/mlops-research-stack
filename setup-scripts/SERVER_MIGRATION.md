# Server Migration Guide

Quick guide to migrate the MLOps system to a new server.

## Phase 1: OLD Server (Pack & Export)

1. **Stop Docker:**
   ```bash
   cd /home/shared/mlops/2025_msc_felix_hagenbrock
   docker compose -f docker-compose_server.yml down
   ```

2. **Create Archive (excludes git repo):**
    Takes a few mins since we also transfer the whole dataset.
   ```bash
   cd /home/shared/mlops
   sudo tar -czvf mlops_migration.tar.gz --exclude='2025_msc_felix_hagenbrock' .
   ```

3. **Transfer to New Server:**
   ```bash
   # direct transfer if both hare in same network
    scp /home/shared/mlops/mlops_migration.tar.gz user@new-server:/tmp/
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

4. **Create Traefik Users File:**
   Generate basic auth credentials (or copy existing `traefik-users.txt`):
   ```bash
   # Option 1: Copy from old server (if available locally)
   # cp /path/to/old/traefik-users.txt /home/shared/mlops/2025_msc_felix_hagenbrock/
   
   # Option 2: Create new users
   cd /home/shared/mlops/2025_msc_felix_hagenbrock
   htpasswd -c traefik-users.txt admin
   htpasswd traefik-users.txt user
   ```

6. **Create mlops Group:**
   ```bash
   sudo groupadd mlops
   sudo usermod -aG mlops $USER
   ```

7. **Restore Permissions:**
   ```bash
   cd /home/shared/mlops/2025_msc_felix_hagenbrock/setup-scripts
   chmod +x setup-permissions.sh
   ./setup-permissions.sh
   ```

8. **Configure DVC for Local Remote:**
   Create `.dvc/config.local` with local DVC remote settings:
   ```bash
   cd /home/shared/mlops/2025_msc_felix_hagenbrock
   cat > .dvc/config.local << 'EOF'
   [cache]
       dir = /dvc-cache
       type = "reflink,hardlink,symlink,copy"
   [core]
       remote = local_remote
   ['remote "local_remote"']
       url = /dvc-remote-storage
   EOF
   ```

9. **Update Hostname:**
   Edit `docker-compose_server.yml` and replace all instances of the old hostname with your new server's hostname (if not already done).

10. **Start System:**
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
