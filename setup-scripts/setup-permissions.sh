#!/bin/bash

# Base directory
BASE_DIR="/home/shared/mlops"

echo "Starting permission restoration for $BASE_DIR..."

# ---------------------------------------------------------
# 1. Set Base Ownership (Default: root:root)
# ---------------------------------------------------------
# Most folders in your structure are root:root (755 or 775)
echo "Setting base ownership to root:root..."
sudo chown -R root:root "$BASE_DIR"
sudo chmod -R 755 "$BASE_DIR"

# ---------------------------------------------------------
# 2. Configure 'dvc-storage-biomass' (Group: mlops, SGID)
# ---------------------------------------------------------
# Current: drwxrwsr-x 3 root mlops
echo "Configuring dvc-storage-biomass..."
TARGET="$BASE_DIR/dvc-storage-biomass"
if [ -d "$TARGET" ]; then
    sudo chown -R root:mlops "$TARGET"
    sudo chmod -R 775 "$TARGET"
    # Set SGID bit so new files inherit 'mlops' group
    sudo find "$TARGET" -type d -exec chmod g+s {} +
else
    echo "Warning: $TARGET not found."
fi

# ---------------------------------------------------------
# 3. Configure 'system-state/dagster_outputs' (Group: mlops, SGID)
# ---------------------------------------------------------
# Current: drwxr-s--- 2 root mlops (750 or 770 usually, yours looks like 750)
echo "Configuring system-state/dagster_outputs..."
TARGET="$BASE_DIR/system-state/dagster_outputs"
if [ -d "$TARGET" ]; then
    sudo chown -R root:mlops "$TARGET"
    # Your ls -l shows 'r-s' for group, which implies read+execute+setgid
    sudo chmod -R 750 "$TARGET" 
    # Set SGID bit
    sudo find "$TARGET" -type d -exec chmod g+s {} +
else
    echo "Warning: $TARGET not found."
fi

# ---------------------------------------------------------
# 4. Configure 'system-state/postgres' (Special Case)
# ---------------------------------------------------------
# Current: drwx------ 19 999 root (Postgres container user is usually UID 999)
echo "Configuring system-state/postgres..."
TARGET="$BASE_DIR/system-state/postgres"
if [ -d "$TARGET" ]; then
    # Postgres requires the owner to be UID 999 (postgres user inside container)
    sudo chown -R 999:root "$TARGET"
    sudo chmod -R 700 "$TARGET"
else
    echo "Warning: $TARGET not found."
fi

echo "Permission restoration complete."