"""LangGraph agent: text-to-SQL with verify+revise loop.

Graph shape:

    START -> attach_schema -> generate_sql -> execute -> verify
                                                          |
                                              ok=true ----+----> END
                                                          |
                                              ok=false ---+----> revise -> execute -> verify (loop)

Loop is capped at MAX_ITERATIONS total generate/revise calls.

The execute node and the graph wiring are provided. `generate_sql_node` is
filled in as a worked example; you implement `verify`, `revise`, and the
conditional router following the same shape.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
import asyncio
from openai import InternalServerError
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from agent import prompts
from agent.execution import ExecutionResult, execute_sql
from agent.schema import render_schema

logger = logging.getLogger(__name__)

# Total generate + revise calls before the loop is forced to stop.
# 3-5 is a reasonable range; tune it as part of Phase 3.
MAX_ITERATIONS = 3

VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_MODEL = os.environ.get("VLLM_MODEL", "Qwen/Qwen3-30B-A3B-Instruct-2507")
# vLLM ignores the key, but a hosted OpenAI-compatible provider needs a real one.
# Lets you point the agent at e.g. OpenAI while iterating without a running vLLM.
LLM_API_KEY = os.environ.get("OPENAI_API_KEY", "not-needed")


@dataclass
class AgentState:
    """State threaded through the graph. Extend with fields you need."""

    question: str
    db_id: str
    schema: str = ""
    sql: str = ""
    execution: ExecutionResult | None = None
    verify_ok: bool = False
    verify_issue: str = ""
    iteration: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)


# Shared HTTP client with increased connection limits for high-concurrency async usage.
_shared_client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
    timeout=httpx.Timeout(120.0),
)


def llm() -> ChatOpenAI:
    """Chat client pointed at VLLM_BASE_URL (your local vLLM by default)."""
    return ChatOpenAI(
        model=VLLM_MODEL,
        base_url=VLLM_BASE_URL,
        api_key=LLM_API_KEY,
        temperature=0.0,
        http_async_client=_shared_client,
        max_tokens=1000
    )


async def ainvoke_with_retry(messages: list, max_retries: int = 3, initial_delay: float = 1.0) -> Any:
    """Invoke the LLM with exponential backoff for internal server errors and timeouts."""
    for attempt in range(max_retries):
        try:
            return await asyncio.wait_for(llm().ainvoke(messages), timeout=20.0)
        except (InternalServerError, asyncio.TimeoutError) as e:
            if attempt == max_retries - 1:
                raise
            delay = initial_delay * (2 ** attempt)
            error_type = "TimeoutError" if isinstance(e, asyncio.TimeoutError) else "InternalServerError"
            logger.warning("vLLM %s (attempt %d/%d), retrying in %.1fs: %s", 
                           error_type, attempt + 1, max_retries, delay, e)
            await asyncio.sleep(delay)
        except Exception:
            # For non-retriable errors, we might not want to retry or handle differently
            raise


# ---- Nodes ------------------------------------------------------------

async def _attach_schema(state: AgentState) -> dict:
    """Provided. Render the DB schema once at the start of the run."""
    return {"schema": render_schema(state.db_id)}


def _extract_sql(text: str) -> str:
    """Pull a SQL statement out of an LLM reply, stripping markdown fences/prose.

    Intentionally simple: take the first ```sql ... ``` block if there is one,
    otherwise the whole reply. You may need to harden this for your prompts.
    """
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return (fenced.group(1) if fenced else text).strip()


async def generate_sql_node(state: AgentState) -> dict:
    """Worked example - the other LLM nodes follow this same shape.

    Build messages from the prompts, call the shared llm(), extract the SQL,
    and return only the state fields you changed. `iteration` is bumped here
    (and in revise) so route_after_verify can enforce MAX_ITERATIONS.

    This node is wired and ready; fill in GENERATE_SQL_SYSTEM / GENERATE_SQL_USER
    in prompts.py to make it produce real queries.
    """
    response = await ainvoke_with_retry([
        ("system", prompts.GENERATE_SQL_SYSTEM),
        ("user", prompts.GENERATE_SQL_USER.format(
            schema=state.schema,
            question=state.question,
        )),
    ])
    sql = _extract_sql(response.content)
    return {
        "sql": sql,
        "iteration": state.iteration + 1,
        "history": state.history + [{"node": "generate_sql", "sql": sql}],
    }


async def execute_node(state: AgentState) -> dict:
    """Provided. Runs the SQL and stores the result."""
    return {"execution": await execute_sql(state.db_id, state.sql)}


async def verify_node(state: AgentState) -> dict:
    """Decide whether state.execution plausibly answers state.question."""
    response = await ainvoke_with_retry([
        ("system", prompts.VERIFY_SYSTEM),
        ("user", prompts.VERIFY_USER.format(
            schema=state.schema,
            question=state.question,
            sql=state.sql,
            execution=state.execution.render() if state.execution else "No execution yet",
        )),
    ])
    
    # Parse JSON defensively
    content = response.content
    try:
        # Try to find JSON in the response
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        # Fallback if parsing fails
        logger.exception("verify_node failed to parse verifier response: %r", content)
        data = {"ok": False, "issue": f"Failed to parse verifier response: {content}"}
        
    return {
        "verify_ok": data.get("ok", False),
        "verify_issue": data.get("issue", ""),
        "history": state.history + [{"node": "verify", "ok": data.get("ok"), "issue": data.get("issue")}],
    }


async def revise_node(state: AgentState) -> dict:
    """Produce a revised SQL query given state.verify_issue and the prior attempt."""
    response = await ainvoke_with_retry([
        ("system", prompts.REVISE_SYSTEM),
        ("user", prompts.REVISE_USER.format(
            schema=state.schema,
            question=state.question,
            old_sql=state.sql,
            execution=state.execution.render() if state.execution else "No execution yet",
            issue=state.verify_issue,
        )),
    ])
    sql = _extract_sql(response.content)
    return {
        "sql": sql,
        "iteration": state.iteration + 1,
        "history": state.history + [{"node": "revise", "sql": sql}],
    }


def route_after_verify(state: AgentState) -> str:
    """Conditional router: return "revise" to loop, "end" to terminate."""
    if state.verify_ok or state.iteration >= MAX_ITERATIONS:
        return "end"
    return "revise"


# ---- Graph wiring -----------------------------------------------------

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("attach_schema", _attach_schema)
    g.add_node("generate_sql", generate_sql_node)
    g.add_node("execute", execute_node)
    g.add_node("verify", verify_node)
    g.add_node("revise", revise_node)

    g.add_edge(START, "attach_schema")
    g.add_edge("attach_schema", "generate_sql")
    g.add_edge("generate_sql", "execute")
    g.add_edge("execute", "verify")
    g.add_conditional_edges(
        "verify",
        route_after_verify,
        {"revise": "revise", "end": END},
    )
    g.add_edge("revise", "execute")
    return g.compile()


graph = build_graph()
