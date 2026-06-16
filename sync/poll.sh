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

echo "Pulling data from ${VM_USER}@${VM_IP}:${REMOTE_DIR}..."

# Perform rsync (pull)
# -a: archive mode
# -v: verbose
# -z: compress
# -e: specify ssh
rsync -avz \
    -e "ssh -i ${SSH_KEY_PATH} -o StrictHostKeyChecking=no" \
    --include="data/" \
    --include="data/**" \
    --include="evals/eval_set.jsonl" \
    --include="load_test/perf_pool.jsonl" \
    --exclude="*" \
    "${VM_USER}@${VM_IP}:${REMOTE_DIR}/" ./

if [ $? -eq 0 ]; then
    echo "Success: Data pull complete."
else
    echo "Error: Data pull failed."
    exit 1
fi
