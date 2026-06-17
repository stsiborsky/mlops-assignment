# Phase 3: Agent Metrics and Performance Analysis

## Overview
As part of the Phase 3 implementation, the agent was instrumented to expose Prometheus metrics (latency, request count, and HTTP status codes). These metrics were integrated into a Grafana dashboard to monitor the system's behavior under load.

## Load Testing Observations
During the load testing phase, a significant increase in latency and a high number of concurrent requests waiting for processing were observed.

## Hypothesis: Thread Pool Exhaustion
**Hypothesis:** The agent has a limited number of worker threads available to invoke HTTP requests to the vLLM backend and execute SQL queries. Under heavy load, this thread pool becomes exhausted, leading to request queuing, increased latency, and eventually timeouts or connection errors.

### Why this is a valid hypothesis:
1. **Synchronous Node Execution**: The current agent implementation uses `langgraph` with synchronous nodes (e.g., `generate_sql_node`, `execute_node`). When running inside a FastAPI application with `uvicorn`, synchronous endpoints (defined with `def` rather than `async def`) are executed in an external thread pool to avoid blocking the main event loop.
2. **Default Thread Pool Limits**: By default, Starlette/FastAPI uses a thread pool with a fixed size (often related to the number of CPU cores, but typically capped at 40 threads in many configurations). If the agent takes several seconds to process a request (due to LLM latency or complex SQL), and the arrival rate exceeds the processing capacity, all 40 threads will be occupied.
3. **Blocking I/O**: Each agent run involves multiple sequential blocking calls (multiple LLM calls via `ChatOpenAI.invoke` and SQLite executions). Because these calls are blocking, the thread remains tied up for the entire duration of the graph execution.
4. **Saturation**: Once the thread pool is full, new incoming requests are queued. This manifests as "waiting" time before the agent even starts processing the request, drastically increasing the end-to-end (E2E) latency observed in metrics.

## Proposed Mitigations
- **Asynchronous Implementation**: Refactoring the agent nodes and the FastAPI endpoint to be `async` would allow the application to handle more concurrent requests using a single thread by yielding control during I/O-bound operations (like waiting for the LLM).
- **Thread Pool Tuning**: Increasing the maximum number of threads in the worker pool could provide a temporary buffer, though it doesn't solve the underlying scalability issue.
- **Horizontal Scaling**: Running multiple instances of the agent behind a load balancer.
