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
#   sudo bash setup-new-deployment.sh [HOSTNAME] [ADMIN_USER] [GIT_USERNAME] [GIT_PAT]
#
#   HOSTNAME     - The public hostname for Traefik routing (e.g. luke.nt.fh-koeln.de)
#   ADMIN_USER   - Linux user that will run the system (defaults to $SUDO_USER)
#   GIT_USERNAME - GitLab username for cloning the private repo
#   GIT_PAT      - GitLab personal access token (or password)
#
# Example:
#   sudo bash setup-new-deployment.sh luke.nt.fh-koeln.de pascal myuser mytoken
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR="/home/shared/mlops"
REPO_URL="https://git-ce.rwth-aachen.de/ai4science/plant_biomass/2025_msc_felix_hagenbrock.git"
REPO_DIR="$BASE_DIR/2025_msc_felix_hagenbrock"

SERVER_HOSTNAME="${1:-}"
ADMIN_USER="${2:-${SUDO_USER:-$USER}}"
GIT_USERNAME="${3:-}"
GIT_PAT="${4:-}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { echo "[INFO]  $*"; }
warn()  { echo "[WARN]  $*"; }
die()   { echo "[ERROR] $*" >&2; exit 1; }

# In dry-run mode, print commands instead of executing them.
DRY_RUN="${DRY_RUN:-0}"
run() {
    if [ "$DRY_RUN" = "1" ]; then
        echo "[DRY-RUN] $*"
    else
        "$@"
    fi
}

require_root() {
    [ "$(id -u)" -eq 0 ] || die "This script must be run as root (sudo)."
}

# ---------------------------------------------------------------------------
# 0. Pre-flight checks
# ---------------------------------------------------------------------------
[ "$DRY_RUN" = "1" ] || require_root

if [ -z "$SERVER_HOSTNAME" ]; then
    read -rp "Enter the public hostname for this server (e.g. myserver.example.com): " SERVER_HOSTNAME
    [ -n "$SERVER_HOSTNAME" ] || die "Hostname cannot be empty."
fi

if [ -z "$GIT_USERNAME" ]; then
    read -rp "GitLab username for cloning the repo: " GIT_USERNAME
fi
if [ -z "$GIT_PAT" ]; then
    read -rsp "GitLab personal access token (input hidden): " GIT_PAT
    echo
fi

info "Deploying to hostname: $SERVER_HOSTNAME"
info "Admin user: $ADMIN_USER"

command -v docker  >/dev/null 2>&1 || die "Docker is not installed. Install it first."
command -v git     >/dev/null 2>&1 || die "Git is not installed."
command -v htpasswd >/dev/null 2>&1 || warn "htpasswd not found – you must create traefik-users.txt manually (apt install apache2-utils)."

# ---------------------------------------------------------------------------
# 1. Create mlops group and add admin user
# ---------------------------------------------------------------------------
info "Setting up mlops group..."
if ! getent group mlops >/dev/null 2>&1; then
    run groupadd mlops
    info "  Created group: mlops"
else
    info "  Group mlops already exists – skipping."
fi

if id "$ADMIN_USER" >/dev/null 2>&1; then
    run usermod -aG mlops "$ADMIN_USER"
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

run mkdir -p \
    "$BASE_DIR/data" \
    "$BASE_DIR/dvc-storage-biomass" \
    "$BASE_DIR/production_inference" \
    "$BASE_DIR/system-state/dagster_home" \
    "$BASE_DIR/system-state/dagster_outputs" \
    "$BASE_DIR/system-state/dvc_cache" \
    "$BASE_DIR/system-state/mlflow_artifacts" \
    "$BASE_DIR/system-state/postgres"

# Base ownership
run chown -R root:root "$BASE_DIR"
run chmod -R 755 "$BASE_DIR"

# dvc-storage-biomass: shared write access for mlops group (SGID)
run chown -R root:mlops "$BASE_DIR/dvc-storage-biomass"
run chmod -R 775 "$BASE_DIR/dvc-storage-biomass"
run find "$BASE_DIR/dvc-storage-biomass" -type d -exec chmod g+s {} +

# dagster_outputs: group-readable by mlops (SGID)
run chown -R root:mlops "$BASE_DIR/system-state/dagster_outputs"
run chmod -R 750 "$BASE_DIR/system-state/dagster_outputs"
run find "$BASE_DIR/system-state/dagster_outputs" -type d -exec chmod g+s {} +

# postgres: must be owned by UID 999 (postgres container user)
run chown -R 999:root "$BASE_DIR/system-state/postgres"
run chmod -R 700 "$BASE_DIR/system-state/postgres"

info "Directory structure created."

# ---------------------------------------------------------------------------
# 3. Clone the repository
# ---------------------------------------------------------------------------
if [ -d "$REPO_DIR/.git" ]; then
    info "Repository already cloned at $REPO_DIR – skipping."
else
    info "Cloning repository into $REPO_DIR..."
    # Embed credentials in URL for non-interactive clone of the private repo
    REPO_URL_AUTH=$(echo "$REPO_URL" | sed "s|https://|https://${GIT_USERNAME}:${GIT_PAT}@|")
    run git clone "$REPO_URL_AUTH" "$REPO_DIR"
    # Remove embedded credentials from the remote URL in the cloned repo
    run git -C "$REPO_DIR" remote set-url origin "$REPO_URL"
    run chown -R root:root "$REPO_DIR"
fi

# ---------------------------------------------------------------------------
# 4. Update hostname in docker-compose_server.yml
# ---------------------------------------------------------------------------
COMPOSE_FILE="$REPO_DIR/docker-compose_server.yml"
if [ -f "$COMPOSE_FILE" ]; then
    info "Updating hostname to '$SERVER_HOSTNAME' in docker-compose_server.yml..."
    # Replace any existing Host(`...`) rule with the new hostname.
    # Pattern uses [^\`]* to match any chars except backtick (safe, no backtracking needed).
    run sed -i "s/Host(\`[^\`]*\`)/Host(\`$SERVER_HOSTNAME\`)/g" "$COMPOSE_FILE"
else
    warn "docker-compose_server.yml not found at $COMPOSE_FILE – skipping hostname update."
fi

# ---------------------------------------------------------------------------
# 5. Configure DVC local remote (.dvc/config.local)
# ---------------------------------------------------------------------------
info "Configuring DVC local remote..."
DVC_CONFIG_LOCAL="$REPO_DIR/.dvc/config.local"
run mkdir -p "$REPO_DIR/.dvc"
if [ "$DRY_RUN" = "1" ]; then
    echo "[DRY-RUN] write $DVC_CONFIG_LOCAL"
else
    cat > "$DVC_CONFIG_LOCAL" << 'EOF'
[cache]
    dir = /dvc-cache
    type = "reflink,hardlink,symlink,copy"
[core]
    remote = local_remote
['remote "local_remote"']
    url = /dvc-remote-storage
EOF
fi
info "  Written: $DVC_CONFIG_LOCAL"

# ---------------------------------------------------------------------------
# 6. Create Traefik basic-auth users file
# ---------------------------------------------------------------------------
TRAEFIK_USERS="$REPO_DIR/traefik-users.txt"
if [ -f "$TRAEFIK_USERS" ]; then
    info "traefik-users.txt already exists – skipping."
elif command -v htpasswd >/dev/null 2>&1; then
    info "Creating traefik-users.txt (you will be prompted for passwords)..."
    if [ "$DRY_RUN" = "1" ]; then
        echo "[DRY-RUN] htpasswd -c $TRAEFIK_USERS <admin>"
    else
        read -rp "  Enter username for admin account [admin]: " TRAEFIK_ADMIN
        TRAEFIK_ADMIN="${TRAEFIK_ADMIN:-admin}"
        htpasswd -c "$TRAEFIK_USERS" "$TRAEFIK_ADMIN"
        read -rp "  Add another user? (y/N): " ADD_USER
        if [[ "$ADD_USER" =~ ^[Yy]$ ]]; then
            read -rp "  Username: " TRAEFIK_USER2
            htpasswd "$TRAEFIK_USERS" "$TRAEFIK_USER2"
        fi
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
[ "$DRY_RUN" = "1" ] || cd "$REPO_DIR"
run docker compose -f docker-compose_server.yml up -d --build

# ---------------------------------------------------------------------------
# 8. Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  Deployment complete!"
echo "============================================================"
echo ""
echo "  Hostname : $SERVER_HOSTNAME"
echo "  Base dir : $BASE_DIR"
echo "  Repo     : $REPO_DIR"
echo ""
echo "  Services :"
echo "    Landing  http://$SERVER_HOSTNAME:8090/welcome"
echo "    MLflow   http://$SERVER_HOSTNAME:8090/"
echo "    Dagster  http://$SERVER_HOSTNAME:8090/dagster"
echo "    Gradio   http://$SERVER_HOSTNAME:8090/gradio"
echo "    Traefik  http://$SERVER_HOSTNAME:8091  (dashboard)"
echo ""
echo "  Next steps (if not done yet):"
echo "    1. Install htpasswd and create Traefik auth file (if not done during setup):"
echo "       apt install apache2-utils"
echo "       htpasswd -c $REPO_DIR/traefik-users.txt admin"
echo ""
echo "    2. Populate training data (fresh deployment – no data yet):"
echo "       Option A: Pull from DVC SSH remote (requires SSH access to old server):"
echo "         cd $REPO_DIR && dvc pull"
echo "       Option B: Copy from old server via scp/rsync:"
echo "         rsync -a user@old-server:/home/shared/mlops/data/ $BASE_DIR/data/"
echo "         rsync -a user@old-server:/home/shared/mlops/dvc-storage-biomass/ $BASE_DIR/dvc-storage-biomass/"
echo ""
echo "    3. Verify services:   docker compose -f docker-compose_server.yml ps"
echo "    4. Check logs:        docker compose -f docker-compose_server.yml logs -f"
echo ""
echo "  Note: system-state/ (Postgres, MLflow artifacts, Dagster state) is"
echo "  generated at runtime – nothing to copy on a fresh deployment."
echo ""
