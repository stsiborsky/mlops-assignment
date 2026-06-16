# Phase 1: vLLM Configuration Report

## Serving Configuration

The following configuration is used to serve the `Qwen/Qwen3-30B-A3B-Instruct-2507` model using vLLM on the provided hardware (1x H100).

| Flag | Justification |
| :--- | :--- |
| `--model "Qwen/Qwen3-30B-A3B-Instruct-2507"` | Specifies the mandatory MoE model required for the assignment. |
| `--host 0.0.0.0` | Enables external access to the inference server on the remote VM. |
| `--port 8000` | Standard port for providing an OpenAI-compatible API. |
| `--max-model-len 32768` | Reduced from 262k to fit the KV cache into the available ~8.7GB VRAM. |
| `--gpu-memory-utilization 0.95` | Maximizes VRAM allocated for the KV cache to improve throughput on a single GPU. |

## Manual Verification

The configuration was verified by sending several manual queries to the `/v1/chat/completions` endpoint. The model correctly generated SQL queries based on provided schemas and questions, confirming the inference layer is functional and optimized for the available hardware constraints.
