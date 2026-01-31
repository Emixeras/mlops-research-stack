# Automated Migration Scripts

> **⚠️ DEPRECATED:** These scripts did not work during testing and are no longer maintained. The migration was performed manually instead.
> 
> **→ Use [SERVER_MIGRATION.md](SERVER_MIGRATION.md) for the working manual migration procedure.**

---

Quick guide to migrate the MLOps system to a new server using automated scripts.

## Overview

- **migrate-export.sh** - Run on OLD server (creates archive and transfers)
- **migrate-import.sh** - Run on NEW server (extracts and configures)
- **.env.migration** - Configuration file with server details and credentials

## Prerequisites

- **Sudo/root privileges** on both old and new server
- SSH access to both servers
- Git Personal Access Token (PAT) for repository cloning
- Htpasswd-formatted credentials for Traefik Basic Auth

## Setup

### 1. Create Configuration File

On the **old server**:

```bash
cd /home/shared/mlops/2025_msc_felix_hagenbrock/setup-scripts

# Copy template and edit
cp .env.migration.example .env.migration
nano .env.migration
```

**Fill in:**
```bash
# Server Configuration
NEW_SERVER_HOST=luke.nt.fh-koeln.de  # New server hostname/domain
NEW_SERVER_USER=username              # SSH username for new server

# Git Configuration
GIT_REPO_URL=https://git-ce.rwth-aachen.de/ai4science/plant_biomass/2025_msc_felix_hagenbrock.git
GIT_USERNAME=your-username
GIT_PAT=your-personal-access-token

# Traefik Basic Auth (htpasswd format)
# Generate with: htpasswd -nb username password
TRAEFIK_USER_ADMIN=admin:$apr1$xyz...
TRAEFIK_USER_VIEWER=viewer:$apr1$abc...
```

## Usage

### OLD Server - Export

```bash
cd /home/shared/mlops/2025_msc_felix_hagenbrock/setup-scripts

# Make executable
chmod +x migrate-export.sh

# Run export with sudo (will prompt for confirmation)
sudo ./migrate-export.sh
```

**What it does:**
1. Stops all Docker containers
2. Creates archive (~several GB, excludes git repo)
3. Transfers to new server via SCP:
   - `mlops_migration.tar.gz` (data archive)
   - `migrate-import.sh` (import script)
   - `.env.migration` (configuration)

**After export:** System is stopped. Restart with:
```bash
cd /home/shared/mlops/2025_msc_felix_hagenbrock
sudo docker compose -f docker-compose_server.yml up -d
```

### NEW Server - Import

**Requires:** Sudo privileges (script creates directories, extracts archives, configures system)

All files are automatically transferred by the export script. Just run:

```bash
# SSH to new server
ssh user@new-server

# Run import script from /tmp/ with sudo
cd /tmp
chmod +x migrate-import.sh
sudo ./migrate-import.sh
```

**Note:** The export script automatically transfers:
- Archive file
- Import script
- Configuration (.env.migration)

**What it does:**
1. Extracts archive to `/home/shared/mlops/`
2. Clones repository with your credentials
3. Creates Traefik users file
4. Creates `mlops` group and sets permissions
5. Configures DVC for local remote
6. Updates hostname in `docker-compose_server.yml`
7. Starts all Docker containers

**Services available at:**
- MLflow: `http://NEW_SERVER_HOST:8090`
- Dagster: `http://NEW_SERVER_HOST:8090/dagster`
- Gradio: `http://NEW_SERVER_HOST:8090/gradio`
- Landing: `http://NEW_SERVER_HOST:8090/welcome`
- Traefik Dashboard: `http://NEW_SERVER_HOST:8091`

## Testing Migration

You can test the migration without destroying the old server:

1. Run `sudo ./migrate-export.sh` on old server (creates archive, stops containers)
2. Run `sudo ./migrate-import.sh` on test server
3. **Restart old server:** `sudo docker compose -f docker-compose_server.yml up -d`

Both servers will run **independently** with no synchronization.

## What Gets Migrated

✅ **Included:**
- Training/test datasets (`data/`)
- DVC remote storage (`dvc-storage-biomass/`)
- Production inference logs (`production_inference/`)
- MLflow artifacts and Postgres DB (`system-state/mlflow_artifacts`, `system-state/postgres`)
- Dagster state (`system-state/dagster_home`, `system-state/dagster_outputs`)
- DVC cache (`system-state/dvc_cache`)

❌ **Excluded (cloned fresh):**
- Git repository (`2025_msc_felix_hagenbrock/`)

## Security Notes

- `.env.migration` contains sensitive credentials - **DO NOT commit to Git**
- Archive file is stored temporarily in `/tmp/` on new server
- Git PAT is used only during clone and not persisted
- Traefik users file is created with restricted permissions (644)

## Troubleshooting

**Check container status:**
```bash
sudo docker compose -f docker-compose_server.yml ps
```

**View logs:**
```bash
sudo docker compose -f docker-compose_server.yml logs -f
```

**Verify permissions:**
```bash
ls -la /home/shared/mlops/system-state/
```

**Group membership (requires re-login):**
```bash
groups  # Should show 'mlops'
```
