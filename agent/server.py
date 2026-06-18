"""FastAPI wrapper exposing the agent over HTTP.

Run:
    uv run uvicorn agent.server:app --host 0.0.0.0 --port 8001

The /answer endpoint accepts {question, db, tags?} and returns the
agent's final SQL, the result rows, and per-iteration history.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator

load_dotenv()

from agent.graph import AgentState, graph  # noqa: E402
from agent.schema import warmup_schema_cache  # noqa: E402

logger = logging.getLogger(__name__)

# Warm up the schema cache on startup
warmup_schema_cache()

# Langfuse callback handler. If keys are set we initialize it; failures
# are NOT swallowed - a misconfigured Langfuse should not silently
# produce zero traces.
_lf_handler: Any = None
if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
    from langfuse.langchain import CallbackHandler

    _lf_handler = CallbackHandler()


app = FastAPI()
Instrumentator().instrument(app).expose(app)

# Simple in-memory cache for successful answers to avoid redundant LLM/DB calls.
# Key: (question, db_id), Value: AnswerResponse
_answer_cache: dict[tuple[str, str], AnswerResponse] = {}
MAX_CACHE_SIZE = 2048


class AnswerRequest(BaseModel):
    question: str
    db: str
    tags: dict[str, str] = {}


class AnswerResponse(BaseModel):
    sql: str
    rows: list[list[Any]] | None
    iterations: int
    ok: bool
    error: str | None = None
    history: list[dict[str, Any]] = []


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/answer", response_model=AnswerResponse)
async def answer(req: AnswerRequest) -> AnswerResponse:
    cache_key = (req.question, req.db)
    if cache_key in _answer_cache:
        logger.info("Cache hit for question=%r db=%s", req.question, req.db)
        return _answer_cache[cache_key]

    state = AgentState(question=req.question, db_id=req.db)
    config: dict[str, Any] = {
        "callbacks": [_lf_handler] if _lf_handler is not None else [],
        "metadata": req.tags,
    }
    try:
        from langfuse import propagate_attributes
        formatted_tags = [f"{k}:{v}" for k, v in req.tags.items()]
        with propagate_attributes(tags=formatted_tags):
            final = await graph.ainvoke(state, config=config)
    except Exception as e:  # noqa: BLE001
        logger.exception("graph.ainvoke failed for question=%r db=%s", req.question, req.db)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    sql = final.get("sql", "")
    iteration = final.get("iteration", 0)
    history = final.get("history", [])
    execution = final.get("execution")

    if execution is None:
        return AnswerResponse(
            sql=sql,
            rows=None,
            iterations=iteration,
            ok=False,
            error="agent produced no execution result",
            history=history,
        )
    if not execution.ok:
        return AnswerResponse(
            sql=sql,
            rows=None,
            iterations=iteration,
            ok=False,
            error=execution.error,
            history=history,
        )

    res = AnswerResponse(
        sql=sql,
        rows=[list(r) for r in (execution.rows or [])],
        iterations=iteration,
        ok=True,
        history=history,
    )

    # Cache successful results
    if len(_answer_cache) >= MAX_CACHE_SIZE:
        # Simple FIFO-ish eviction: clear the whole cache or just one.
        # Clearing one is better.
        _answer_cache.pop(next(iter(_answer_cache)))
    _answer_cache[cache_key] = res

    return res
