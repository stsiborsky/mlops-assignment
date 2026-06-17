#!/bin/bash

# Define the output zip file
ZIP_NAME="submission.zip"

# Define the array of required files
FILES=(
    "REPORT.md"
    "infra/grafana/provisioning/dashboards/serving.json"
    "agent/graph.py"
    "agent/prompts.py"
    "evals/run_eval.py"
    "results/eval_baseline.json"
    "results/eval_after_tuning.json"
    "screenshots/vllm_manual_query.png"
    "screenshots/grafana_serving.png"
    "screenshots/langfuse_trace.png"
    "screenshots/langfuse_tags.png"
    "screenshots/grafana_eval_run.png"
    "screenshots/grafana_before.png"
    "screenshots/grafana_after.png"
)

echo "=== Verifying submission files ==="
MISSING_FILES=0

# Check if each file exists
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "[✓] Found: $file"
    else
        echo "[X] MISSING: $file"
        MISSING_FILES=$((MISSING_FILES + 1))
    fi
done

echo "----------------------------------"

# If files are missing, warn the user and ask for confirmation
if [ $MISSING_FILES -gt 0 ]; then
    echo "⚠️ Warning: $MISSING_FILES required file(s) are missing."
    read -p "Do you still want to create the zip file? (y/N): " choice
    case "$choice" in
        y|Y ) echo "Proceeding with missing files...";;
        * ) echo "Aborting submission creation."; exit 1;;
    esac
fi

# Remove old zip if it exists to avoid appending issues
if [ -f "$ZIP_NAME" ]; then
    echo "Removing old $ZIP_NAME..."
    rm "$ZIP_NAME"
fi

echo "=== Creating $ZIP_NAME ==="
# Zip the files while preserving the directory structure
# Only zips files that actually exist
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        zip -r "$ZIP_NAME" "$file" > /dev/null
    fi
done

if [ -f "$ZIP_NAME" ]; then
    echo "🎉 Successfully created $ZIP_NAME!"
    echo "Contents of your submission:"
    zipinfo -1 "$ZIP_NAME"
else
    echo "❌ Failed to create $ZIP_NAME."
fi