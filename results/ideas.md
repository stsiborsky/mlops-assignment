# Ideas for High P95 Latency (10 RPS)

Even after migrating to a fully asynchronous implementation, a P95 latency of ~1 minute under 10 RPS suggests bottlenecks beyond the agent's thread pool. Given that the vLLM backend reports a P95 of 7 seconds, here are three potential reasons for the remaining latency:

## 1. Sequential Graph Loops (Multi-Turn Latency)
The agent is not a single-shot system; it runs a "Verify-Revise" loop.
- **The Math:** If a single vLLM call takes 7 seconds (P95), an agent run that fails verification and requires 2-3 revisions will naturally accumulate latency.
- **Example:** `generate` (7s) + `verify` (7s) + `revise` (7s) + `verify` (7s) = **28 seconds** of raw model time for a single complex request.
- **Bottleneck:** Under load, if the agent frequently hits the `MAX_ITERATIONS` limit, the additive effect of sequential LLM calls makes the P95 much higher than the backend's single-request P95.

## 2. vLLM Queue Saturation (Head-of-Line Blocking)
While the agent is now async and doesn't block local threads, it is sending 10 requests per second to a backend that might be at its limit.
- **The Issue:** vLLM has its own internal request queue and scheduling (KV cache management). If 10 agent requests arrive per second, and each agent run triggers ~3 LLM calls, the backend is actually seeing **~30 LLM requests per second**.
- **Queuing Effect:** If the vLLM throughput capacity is lower than 30 RPS, requests will sit in the vLLM queue. This "wait time" is part of the E2E latency the agent measures but might not be fully reflected in the "execution time" metrics of the backend if those metrics only track active generation.

## 4. Where do "Hidden" Queues Hide? (5 Ideas)

If requests remain in a queue even after the load test is terminated, they are being held in one of several buffers in the stack:

### 1. vLLM Internal Scheduler (Waiting/Swapped)
vLLM has a complex internal state machine. If the GPU KV cache is full, it moves requests to a "Waiting" queue. If the GPU runs out of memory *during* generation, it "preempts" requests and moves them to a "Swapped" queue in CPU RAM. Even after the load generator stops, vLLM will continue to process these swapped/waiting requests until the internal queues are empty.

### 2. HTTP Client Connection Pooling (Agent Side)
The `ChatOpenAI` client (via `httpx` or `aiohttp`) uses a connection pool. By default, these pools have a limit on concurrent connections (e.g., 100). If the agent attempts to make 300 concurrent LLM calls, 200 of them will be queued *inside the agent's memory* waiting for an available TCP connection to vLLM, even if the agent code is async.

### 3. TCP Listen Backlog (Socket Level)
The operating system and the web server (Uvicorn/FastAPI) have a `backlog` setting. When vLLM's worker is busy, the OS can accept new TCP connections and hold them in a kernel-level queue (SYN/Accept queue). These requests haven't even reached the vLLM application code yet, but the client thinks the connection is "established."

### 4. Reverse Proxy / Load Balancer Buffers
If there is an Nginx or a similar proxy between the agent and vLLM, it likely has its own buffering logic. Proxies can buffer entire request bodies and hold them in a queue before forwarding them to the upstream service, especially if the upstream is reporting a full connection pool.

### 5. Asyncio Task Backlog (Event Loop Lag)
In a high-RPS async environment, if the event loop becomes "laggy" due to CPU-intensive tasks (like JSON parsing or complex SQL rendering), thousands of `asyncio` tasks can be scheduled but not yet executed. These tasks sit in the event loop's "ready" queue. If the load test stops, the loop will continue "draining" these tasks one by one, making it look like the system is still processing a "ghost" queue.
