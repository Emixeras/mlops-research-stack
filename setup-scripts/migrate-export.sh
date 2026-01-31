#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env.migration"

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
    echo_error ".env.migration not found. Copy .env.migration.example and configure it."
    exit 1
fi

source "$ENV_FILE"

# Verify required variables
required_vars=("NEW_SERVER_USER" "NEW_SERVER_HOST")
for var in "${required_vars[@]}"; do
    if [[ -z "${!var:-}" ]]; then
        echo_error "Required variable $var is not set in .env.migration"
        exit 1
    fi
done

MLOPS_DIR="/home/shared/mlops"
REPO_DIR="${MLOPS_DIR}/2025_msc_felix_hagenbrock"
ARCHIVE_FILE="${MLOPS_DIR}/mlops_migration.tar.gz"

echo_info "=========================================="
echo_info "MLOps System Migration - EXPORT (OLD SERVER)"
echo_info "=========================================="
echo ""

# Confirmation
echo_warn "This will:"
echo_warn "  1. Stop all Docker containers"
echo_warn "  2. Create archive of system-state and data (~several GB)"
echo_warn "  3. Transfer to ${NEW_SERVER_USER}@${NEW_SERVER_HOST}"
echo ""
read -p "Continue? (yes/no): " confirm
if [[ "$confirm" != "yes" ]]; then
    echo_info "Aborted."
    exit 0
fi

# Step 1: Stop Docker
echo_info "[1/3] Stopping Docker containers..."
cd "$REPO_DIR"
if docker compose -f docker-compose_server.yml ps -q | grep -q .; then
    docker compose -f docker-compose_server.yml down
    echo_info "Containers stopped."
else
    echo_warn "No running containers found."
fi

# This did not work in my test case probably because the server ran out of memory while archiving the big dataset
# Step 2: Create Archive
echo_info "[2/3] Creating migration archive (this may take several minutes)..."
cd "$MLOPS_DIR"
if [[ -f "$ARCHIVE_FILE" ]]; then
    echo_warn "Old archive found. Removing..."
    sudo rm -f "$ARCHIVE_FILE"
fi

sudo tar -czvf "$ARCHIVE_FILE" \
    --exclude='2025_msc_felix_hagenbrock' \
    --exclude='*.log' \
    --exclude='__pycache__' \
    .

echo_info "Archive created: $ARCHIVE_FILE"
sudo ls -lh "$ARCHIVE_FILE"

# Step 3: Transfer
echo_info "[3/3] Transferring to new server..."
echo_info "Destination: ${NEW_SERVER_USER}@${NEW_SERVER_HOST}:/tmp/"

# Transfer archive
sudo scp "$ARCHIVE_FILE" "${NEW_SERVER_USER}@${NEW_SERVER_HOST}:/tmp/"

# Transfer migration scripts and config
echo_info "Transferring migration scripts and configuration..."
scp "${SCRIPT_DIR}/migrate-import.sh" "${NEW_SERVER_USER}@${NEW_SERVER_HOST}:/tmp/"
scp "${ENV_FILE}" "${NEW_SERVER_USER}@${NEW_SERVER_HOST}:/tmp/.env.migration"

# Transfer existing traefik-users.txt if it exists
if [[ -f "${REPO_DIR}/traefik-users.txt" ]]; then
    echo_info "Transferring existing traefik-users.txt..."
    scp "${REPO_DIR}/traefik-users.txt" "${NEW_SERVER_USER}@${NEW_SERVER_HOST}:/tmp/traefik-users.txt"
else
    echo_warn "No traefik-users.txt found. You'll need to create it on the new server."
fi

echo ""
echo_info "=========================================="
echo_info "EXPORT COMPLETE!"
echo_info "=========================================="
echo_info "Transferred to new server /tmp/:"
echo_info "  • mlops_migration.tar.gz"
echo_info "  • migrate-import.sh"
echo_info "  • .env.migration"
echo_info "  • traefik-users.txt (if existed)"
echo ""
echo_info "Next steps:"
echo_info "  1. SSH to new server: ssh ${NEW_SERVER_USER}@${NEW_SERVER_HOST}"
echo_info "  2. Run: cd /tmp && chmod +x migrate-import.sh && ./migrate-import.sh"
echo ""
