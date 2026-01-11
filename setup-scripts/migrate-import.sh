#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Look for .env.migration in script directory or /tmp
if [[ -f "${SCRIPT_DIR}/.env.migration" ]]; then
    ENV_FILE="${SCRIPT_DIR}/.env.migration"
elif [[ -f "/tmp/.env.migration" ]]; then
    ENV_FILE="/tmp/.env.migration"
else
    ENV_FILE="${SCRIPT_DIR}/.env.migration"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Load environment file
if [[ ! -f "$ENV_FILE" ]]; then
    echo_error ".env.migration not found. Copy from old server and configure it."
    exit 1
fi

source "$ENV_FILE"

# Verify required variables
required_vars=("NEW_SERVER_HOST" "GIT_REPO_URL" "GIT_USERNAME" "GIT_PAT")
for var in "${required_vars[@]}"; do
    if [[ -z "${!var:-}" ]]; then
        echo_error "Required variable $var is not set in .env.migration"
        exit 1
    fi
done

MLOPS_DIR="/home/shared/mlops"
REPO_DIR="${MLOPS_DIR}/2025_msc_felix_hagenbrock"
ARCHIVE_FILE="/tmp/mlops_migration.tar.gz"

echo_info "=========================================="
echo_info "MLOps System Migration - IMPORT (NEW SERVER)"
echo_info "=========================================="
echo ""

# Confirmation
echo_warn "This will:"
echo_warn "  1. Extract archive to ${MLOPS_DIR}"
echo_warn "  2. Clone repository with provided credentials"
echo_warn "  3. Update docker-compose to new hostname: ${NEW_SERVER_HOST}"
echo_warn "  4. Configure DVC and permissions"
echo_warn "  5. Start the system"
echo ""
read -p "Continue? (yes/no): " confirm
if [[ "$confirm" != "yes" ]]; then
    echo_info "Aborted."
    exit 0
fi

# Check if archive exists
if [[ ! -f "$ARCHIVE_FILE" ]]; then
    echo_error "Archive not found at $ARCHIVE_FILE"
    echo_error "Please transfer it first: scp user@old-server:/home/shared/mlops/mlops_migration.tar.gz /tmp/"
    exit 1
fi

# Step 1: Create Base Directory
echo_info "[1/9] Creating base directory..."
sudo mkdir -p "$MLOPS_DIR"

# Step 2: Extract Archive
echo_info "[2/9] Extracting archive (this may take several minutes)..."
sudo tar -xzvf "$ARCHIVE_FILE" -C "$MLOPS_DIR"
echo_info "Extraction complete."

# Step 3: Clone Repository
echo_info "[3/9] Cloning repository..."
cd "$MLOPS_DIR"

# Build authenticated Git URL
GIT_URL_WITH_CREDS=$(echo "$GIT_REPO_URL" | sed "s|https://|https://${GIT_USERNAME}:${GIT_PAT}@|")

if [[ -d "$REPO_DIR" ]]; then
    echo_warn "Repository directory already exists. Removing..."
    sudo rm -rf "$REPO_DIR"
fi

sudo git clone "$GIT_URL_WITH_CREDS" 2025_msc_felix_hagenbrock
echo_info "Repository cloned."

# Step 4: Setup Traefik Users File
echo_info "[4/9] Setting up Traefik users file..."
TRAEFIK_FILE="${REPO_DIR}/traefik-users.txt"

if [[ -f "/tmp/traefik-users.txt" ]]; then
    # Copy existing traefik-users.txt from old server
    echo_info "Using existing traefik-users.txt from old server..."
    sudo cp /tmp/traefik-users.txt "$TRAEFIK_FILE"
    sudo chmod 644 "$TRAEFIK_FILE"
    echo_info "Traefik users copied from old server."
else
    # Create new traefik-users.txt (for fresh installations)
    echo_warn "No traefik-users.txt transferred. Creating placeholder..."
    echo_info "You need to create users manually with: htpasswd -c ${TRAEFIK_FILE} username"
    sudo touch "$TRAEFIK_FILE"
    sudo chmod 644 "$TRAEFIK_FILE"
fi

# Step 5: Create mlops Group
echo_info "[5/9] Creating mlops group..."
if ! getent group mlops > /dev/null; then
    sudo groupadd mlops
    echo_info "Group mlops created."
else
    echo_warn "Group mlops already exists."
fi
sudo usermod -aG mlops "$USER"

# Step 6: Restore Permissions
echo_info "[6/9] Restoring permissions..."
cd "${REPO_DIR}/setup-scripts"
chmod +x setup-permissions.sh
sudo ./setup-permissions.sh

# Step 7: Configure DVC
echo_info "[7/9] Configuring DVC for local remote..."
cd "$REPO_DIR"
sudo bash -c "cat > .dvc/config.local" <<'EOF'
[cache]
    dir = /dvc-cache
    type = "reflink,hardlink,symlink,copy"
[core]
    remote = local_remote
['remote "local_remote"']
    url = /dvc-remote-storage
EOF
echo_info "DVC configured."

# Step 8: Update Hostname in docker-compose
echo_info "[8/9] Updating hostname in docker-compose_server.yml..."
OLD_HOSTS=("luke.nt.fh-koeln.de" "old-server.example.com" "localhost")

for OLD_HOST in "${OLD_HOSTS[@]}"; do
    sudo sed -i "s|Host(\`${OLD_HOST}\`)|Host(\`${NEW_SERVER_HOST}\`)|g" "${REPO_DIR}/docker-compose_server.yml"
    sudo sed -i "s|${OLD_HOST}|${NEW_SERVER_HOST}|g" "${REPO_DIR}/docker-compose_server.yml"
done

echo_info "Hostname updated to: ${NEW_SERVER_HOST}"

# Step 9: Start System
echo_info "[9/9] Starting Docker containers..."
cd "$REPO_DIR"
sudo docker compose -f docker-compose_server.yml up -d --build

echo ""
echo_info "=========================================="
echo_info "IMPORT COMPLETE!"
echo_info "=========================================="
echo_info "System is starting up. Services will be available at:"
echo_info "  • MLflow:  http://${NEW_SERVER_HOST}:8090"
echo_info "  • Dagster: http://${NEW_SERVER_HOST}:8090/dagster"
echo_info "  • Gradio:  http://${NEW_SERVER_HOST}:8090/gradio"
echo_info "  • Landing: http://${NEW_SERVER_HOST}:8090/welcome"
echo_info "  • Traefik: http://${NEW_SERVER_HOST}:8091"
echo ""
echo_info "Check status: docker compose -f docker-compose_server.yml ps"
echo_info "View logs:    docker compose -f docker-compose_server.yml logs -f"
echo ""
echo_warn "Note: You may need to log out and back in for group membership to take effect."
