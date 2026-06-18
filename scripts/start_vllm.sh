#!/usr/bin/env bash
#
# Start vLLM with your chosen configuration.
# Reference: https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html

set -euo pipefail

MODEL="Qwen/Qwen3-30B-A3B-Instruct-2507"

exec uv run python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.95 \
    --max-num-seqs 1024 \
    --max-num-batched-tokens 16384 \
    --enable-prefix-caching \
    --dtype bfloat16 \
    --kv-cache-dtype auto \
    --enable-chunked-prefill \
    --disable-log-requests
