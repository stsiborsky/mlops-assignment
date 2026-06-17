#!/bin/bash

# Load configuration from .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "Error: .env file not found. Please create one based on .env.example"
    exit 1
fi

# Validate essential variables
if [ -z "$VM_IP" ] || [ -z "$VM_USER" ] || [ -z "$SSH_KEY_PATH" ]; then
    echo "Error: Missing required variables in .env (VM_IP, VM_USER, SSH_KEY_PATH)"
    exit 1
fi

# Set default remote directory if not provided
REMOTE_DIR=${REMOTE_DIR:-"~/mlops"}

echo "Syncing local files to ${VM_USER}@${VM_IP}:${REMOTE_DIR}..."

# Perform rsync
# -a: archive mode (preserves permissions, symlinks, etc.)
# -v: verbose
# -z: compress during transfer
# --delete: delete files on remote that are deleted locally (use with caution!)
# -e: specify the remote shell (to use the SSH key)
rsync -avz \
    -e "ssh -i ${SSH_KEY_PATH} -o StrictHostKeyChecking=no" \
    --exclude ".venv" \
    --exclude "__pycache__" \
    --exclude ".git" \
    --exclude "results" \
    --exclude ".idea" \
    --exclude ".vscode" \
    ./ "${VM_USER}@${VM_IP}:${REMOTE_DIR}/"

if [ $? -eq 0 ]; then
    echo "Success: Sync complete."
else
    echo "Error: Sync failed."
    exit 1
fi
