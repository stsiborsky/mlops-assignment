# Project Instructions

- **No Local GPU/ML Runs:** Do not execute any commands or scripts that require NVIDIA GPUs, CUDA, or heavy PyTorch computation locally on this machine. All model inference must be directed to the configured `VLLM_BASE_URL` (typically `http://localhost:8000/v1`).
- **Phase 3 Focus:** For Phase 3, you can implement and test the agent logic using a lighter backend or by ensuring `vLLM` is running remotely/on the designated H100 as per the `README.md`.
