#!/bin/bash
# =============================================================================
# setup-new-deployment.sh
# Fresh server deployment script for the MLOps system.
#
# Run this script on a brand-new server (not a migration).
# It creates the required filesystem layout, clones the repo,
# configures DVC, sets up authentication, and starts Docker Compose.
#
# Usage:
#   sudo bash setup-new-deployment.sh [HOSTNAME] [ADMIN_USER]
#
#   HOSTNAME    - The public hostname for Traefik routing
#                 (e.g. luke.nt.fh-koeln.de)
#   ADMIN_USER  - Linux user that will run the system (defaults to $SUDO_USER)
#
# Example:
#   sudo bash setup-new-deployment.sh luke.nt.fh-koeln.de pascal
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR="/home/shared/mlops"
REPO_URL="https://git-ce.rwth-aachen.de/ai4science/plant_biomass/2025_msc_felix_hagenbrock.git"
REPO_DIR="$BASE_DIR/2025_msc_felix_hagenbrock"

HOSTNAME="${1:-}"
ADMIN_USER="${2:-${SUDO_USER:-$USER}}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { echo "[INFO]  $*"; }
warn()  { echo "[WARN]  $*"; }
die()   { echo "[ERROR] $*" >&2; exit 1; }

require_root() {
    [ "$(id -u)" -eq 0 ] || die "This script must be run as root (sudo)."
}

# ---------------------------------------------------------------------------
# 0. Pre-flight checks
# ---------------------------------------------------------------------------
require_root

if [ -z "$HOSTNAME" ]; then
    read -rp "Enter the public hostname for this server (e.g. myserver.example.com): " HOSTNAME
    [ -n "$HOSTNAME" ] || die "Hostname cannot be empty."
fi

info "Deploying to hostname: $HOSTNAME"
info "Admin user: $ADMIN_USER"

command -v docker  >/dev/null 2>&1 || die "Docker is not installed. Install it first."
command -v git     >/dev/null 2>&1 || die "Git is not installed."
command -v htpasswd >/dev/null 2>&1 || warn "htpasswd not found – you must create traefik-users.txt manually (apt install apache2-utils)."

# ---------------------------------------------------------------------------
# 1. Create mlops group and add admin user
# ---------------------------------------------------------------------------
info "Setting up mlops group..."
if ! getent group mlops >/dev/null 2>&1; then
    groupadd mlops
    info "  Created group: mlops"
else
    info "  Group mlops already exists – skipping."
fi

if id "$ADMIN_USER" >/dev/null 2>&1; then
    usermod -aG mlops "$ADMIN_USER"
    info "  Added $ADMIN_USER to mlops group."
else
    warn "  User '$ADMIN_USER' not found – skipping group assignment."
fi

# ---------------------------------------------------------------------------
# 2. Create filesystem layout
#
# Expected layout (see presentation/server_structure.txt):
#
#   /home/shared/
#   └── mlops/
#       ├── 2025_msc_felix_hagenbrock/   ← git repo (created in step 3)
#       ├── data/                         ← training data (populated via DVC)
#       ├── dvc-storage-biomass/          ← DVC local remote  (root:mlops 2775)
#       ├── production_inference/         ← Gradio inference logs
#       └── system-state/
#           ├── dagster_home/
#           ├── dagster_outputs/          ← root:mlops 2750
#           ├── dvc_cache/
#           ├── mlflow_artifacts/
#           └── postgres/                 ← owned by UID 999 (postgres)
# ---------------------------------------------------------------------------
info "Creating directory structure under $BASE_DIR..."

mkdir -p \
    "$BASE_DIR/data" \
    "$BASE_DIR/dvc-storage-biomass" \
    "$BASE_DIR/production_inference" \
    "$BASE_DIR/system-state/dagster_home" \
    "$BASE_DIR/system-state/dagster_outputs" \
    "$BASE_DIR/system-state/dvc_cache" \
    "$BASE_DIR/system-state/mlflow_artifacts" \
    "$BASE_DIR/system-state/postgres"

# Base ownership
chown -R root:root "$BASE_DIR"
chmod -R 755 "$BASE_DIR"

# dvc-storage-biomass: shared write access for mlops group (SGID)
chown -R root:mlops "$BASE_DIR/dvc-storage-biomass"
chmod -R 775 "$BASE_DIR/dvc-storage-biomass"
find "$BASE_DIR/dvc-storage-biomass" -type d -exec chmod g+s {} +

# dagster_outputs: group-readable by mlops (SGID)
chown -R root:mlops "$BASE_DIR/system-state/dagster_outputs"
chmod -R 750 "$BASE_DIR/system-state/dagster_outputs"
find "$BASE_DIR/system-state/dagster_outputs" -type d -exec chmod g+s {} +

# postgres: must be owned by UID 999 (postgres container user)
chown -R 999:root "$BASE_DIR/system-state/postgres"
chmod -R 700 "$BASE_DIR/system-state/postgres"

info "Directory structure created."

# ---------------------------------------------------------------------------
# 3. Clone the repository
# ---------------------------------------------------------------------------
if [ -d "$REPO_DIR/.git" ]; then
    info "Repository already cloned at $REPO_DIR – skipping."
else
    info "Cloning repository into $REPO_DIR..."
    git clone "$REPO_URL" "$REPO_DIR"
    chown -R root:root "$REPO_DIR"
fi

# ---------------------------------------------------------------------------
# 4. Update hostname in docker-compose_server.yml
# ---------------------------------------------------------------------------
COMPOSE_FILE="$REPO_DIR/docker-compose_server.yml"
if [ -f "$COMPOSE_FILE" ]; then
    info "Updating hostname to '$HOSTNAME' in docker-compose_server.yml..."
    # Replace any existing Host(...) rule with the new hostname
    sed -i "s/Host(\`[^)]*\`)/Host(\`$HOSTNAME\`)/g" "$COMPOSE_FILE"
else
    warn "docker-compose_server.yml not found at $COMPOSE_FILE – skipping hostname update."
fi

# ---------------------------------------------------------------------------
# 5. Configure DVC local remote (.dvc/config.local)
# ---------------------------------------------------------------------------
info "Configuring DVC local remote..."
DVC_CONFIG_LOCAL="$REPO_DIR/.dvc/config.local"
mkdir -p "$REPO_DIR/.dvc"
cat > "$DVC_CONFIG_LOCAL" << 'EOF'
[cache]
    dir = /dvc-cache
    type = "reflink,hardlink,symlink,copy"
[core]
    remote = local_remote
['remote "local_remote"']
    url = /dvc-remote-storage
EOF
info "  Written: $DVC_CONFIG_LOCAL"

# ---------------------------------------------------------------------------
# 6. Create Traefik basic-auth users file
# ---------------------------------------------------------------------------
TRAEFIK_USERS="$REPO_DIR/traefik-users.txt"
if [ -f "$TRAEFIK_USERS" ]; then
    info "traefik-users.txt already exists – skipping."
elif command -v htpasswd >/dev/null 2>&1; then
    info "Creating traefik-users.txt (you will be prompted for passwords)..."
    read -rp "  Enter username for admin account [admin]: " TRAEFIK_ADMIN
    TRAEFIK_ADMIN="${TRAEFIK_ADMIN:-admin}"
    htpasswd -c "$TRAEFIK_USERS" "$TRAEFIK_ADMIN"
    read -rp "  Add another user? (y/N): " ADD_USER
    if [[ "$ADD_USER" =~ ^[Yy]$ ]]; then
        read -rp "  Username: " TRAEFIK_USER2
        htpasswd "$TRAEFIK_USERS" "$TRAEFIK_USER2"
    fi
    info "  traefik-users.txt created."
else
    warn "htpasswd not available – create $TRAEFIK_USERS manually before starting Docker."
    warn "  Install with: apt install apache2-utils"
    warn "  Then run: htpasswd -c $TRAEFIK_USERS admin"
fi

# ---------------------------------------------------------------------------
# 7. Start the system
# ---------------------------------------------------------------------------
info "Starting Docker Compose stack..."
cd "$REPO_DIR"
docker compose -f docker-compose_server.yml up -d --build

# ---------------------------------------------------------------------------
# 8. Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  Deployment complete!"
echo "============================================================"
echo ""
echo "  Hostname : $HOSTNAME"
echo "  Base dir : $BASE_DIR"
echo "  Repo     : $REPO_DIR"
echo ""
echo "  Services :"
echo "    MLflow   http://$HOSTNAME:8090  (proxied via Traefik)"
echo "    Dagster  http://$HOSTNAME:8090/dagster"
echo "    Traefik  http://$HOSTNAME:8091  (dashboard)"
echo ""
echo "  Next steps (if not done yet):"
echo "    - Pull data via DVC:  cd $REPO_DIR && dvc pull"
echo "    - Verify services:    docker compose -f docker-compose_server.yml ps"
echo "    - Check logs:         docker compose -f docker-compose_server.yml logs -f"
echo ""
